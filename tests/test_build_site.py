"""Unit tests for the static-site generator (payload integrity + rendered page)."""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from build_site import build_payload, ownership_overlap, render_html  # noqa: E402

UTC = "UTC"

AUTHOR_KEYS = {
    "name", "rank", "tier", "impact", "signals", "flags", "rationale",
    "aux", "review", "top_files", "owned", "commits", "sx", "weekly", "github", "views",
}
SIGNAL_KEYS = {
    "ownership_concentration", "code_survival_tenure_normalized",
    "coupling_criticality", "review_leverage",
}
VIEW_KEYS = {"spectrum", "activity", "own", "surv", "coup", "rev", "tiers"}

# External *resource loads* must be absent. Plain <a href> navigation (GitHub
# profile links) is allowed; <link href> stylesheets are not.
EXTERNAL = re.compile(
    r'src="http|<link[^>]*href="http|url\(\s*["\']?http|@import|integrity='
    r"|fetch\(|XMLHttpRequest|sendBeacon"
)


def _frames():
    scored = pd.DataFrame(
        {
            "author_canonical": ["Alice", "Bob", "Carol"],
            "impact_score": [0.91, 0.55, 0.20],
            "ownership_concentration": [1.0, 0.5, 0.1],
            "code_survival_tenure_normalized": [0.9, 0.4, 0.2],
            "coupling_criticality": [0.8, 0.6, 0.3],
            "review_leverage": [0.95, 0.5, 0.5],
            "has_review_data": [True, False, False],
            "review_data_imputed": [False, True, False],
            "bus_factor_flag": [True, False, False],
            "tier": [1, 2, 3],
            "breadth_files": [40, 10, 2],
            "breadth_dirs": [6, 3, 1],
            "recency_days": [1, 30, 200],
            "consistency": [0.9, 0.5, 0.1],
            # </script> must never be able to break out of the inline data block
            "one_line_rationale": ["Leads ownership.", "Solid.", "x</script><b>y"],
        }
    )
    dates = pd.to_datetime(
        [
            "2025-01-06", "2025-01-07", "2025-02-03",  # Alice, 3 distinct commits
            "2025-01-08", "2025-01-20",                # Bob, 2 distinct commits
            "2025-01-09",                              # Bob merge (excluded)
            "2025-03-03",                              # Carol, 1 commit
        ],
        utc=True,
    )
    commits = pd.DataFrame(
        {
            "commit_hash": ["a1", "a2", "a3", "b1", "b2", "bm", "c1"],
            "author_canonical": ["Alice"] * 3 + ["Bob"] * 3 + ["Carol"],
            "author_email_raw": ["12345+alicehub@users.noreply.github.com"] * 3
            + ["x@example.com"] * 4,
            "date": dates,
            "file_path": ["src/a.py", "src/a.py", "src/b.py", "src/b.py",
                          "src/c.py", "src/m.py", "src/d.py"],
            "additions": [10, 5, 3, 8, 2, 1, 4],
            "deletions": [1, 0, 2, 1, 0, 0, 1],
            "is_merge": [False, False, False, False, False, True, False],
        }
    )
    reviews = pd.DataFrame(
        {
            "author_canonical": ["Alice"],
            "reviewer_login": ["alice-gh"],
            "review_count": [12],
            "distinct_authors_reviewed": [4],
            "approval_rate": [0.75],
            "status": ["complete"],
        }
    )
    ownership_file = pd.DataFrame(
        {
            "file_path": ["src/a.py", "src/b.py", "src/c.py"],
            "author_canonical": ["Alice", "Alice", "Bob"],
            "blame_lines": [90, 40, 20],
            "blame_share": [0.9, 0.4, 0.6],
            "is_blame_leader": [True, False, True],
            "is_major_owner": [True, True, True],
            "top_owner_proportion": [0.9, 0.5, 0.6],
            "minor_contributor_count": [1, 2, 0],
            "is_orphan_risk": [True, False, False],
        }
    )
    coupling = pd.DataFrame(
        {
            # src/c.py deliberately absent -> fillna(0) path
            "file_path": ["src/a.py", "src/b.py"],
            "centrality_score": [0.02, 0.05],
            "weighted_degree": [3.0, 5.0],
        }
    )
    return {
        "scored": scored,
        "commits_clean": commits,
        "reviews": reviews,
        "ownership_file": ownership_file,
        "coupling": coupling,
    }


def test_payload_authors_match_scored():
    payload = build_payload(_frames())
    assert len(payload["authors"]) == 3
    assert {a["name"] for a in payload["authors"]} == {"Alice", "Bob", "Carol"}
    ranks = [a["rank"] for a in payload["authors"]]
    assert ranks == [1, 2, 3]
    impacts = [a["impact"] for a in payload["authors"]]
    assert impacts == sorted(impacts, reverse=True)


def test_author_key_schema_exact():
    payload = build_payload(_frames())
    for a in payload["authors"]:
        assert set(a.keys()) == AUTHOR_KEYS
        assert set(a["signals"].keys()) == SIGNAL_KEYS
        assert 0.0 <= a["impact"] <= 1.0
        assert all(0.0 <= v <= 1.0 for v in a["signals"].values())


def test_owned_footprint_shape_and_counts():
    payload = build_payload(_frames())
    assert "files_shared" in payload
    by = {a["name"]: a for a in payload["authors"]}
    # fixture files each have a single major owner -> nothing shared
    assert payload["files_shared"] == []
    # Alice majors src/a.py (orphan) + src/b.py -> total 2, orphan 1
    assert by["Alice"]["owned"] == {"total": 2, "orphan": 1, "shared": []}
    # Bob majors src/c.py (not orphan)
    assert by["Bob"]["owned"] == {"total": 1, "orphan": 0, "shared": []}
    # Carol owns nothing major -> default footprint
    assert by["Carol"]["owned"] == {"total": 0, "orphan": 0, "shared": []}


def test_ownership_overlap_intersection():
    # f1 is co-owned by two majors (the shared surface); f2/f3 are sole-owned
    of = pd.DataFrame(
        {
            "file_path": ["f1", "f1", "f2", "f3"],
            "author_canonical": ["Alice", "Bob", "Alice", "Bob"],
            "blame_lines": [50, 40, 90, 30],
            "blame_share": [0.5, 0.4, 0.9, 0.7],
            "is_blame_leader": [True, False, True, True],
            "is_major_owner": [True, True, True, True],
            "top_owner_proportion": [0.5, 0.4, 0.9, 0.7],
            "minor_contributor_count": [1, 1, 0, 0],
            "is_orphan_risk": [False, False, True, True],
        }
    )
    files_shared, owned = ownership_overlap(of)
    assert files_shared == ["f1"]  # only the >=2-major file enters the dict
    assert owned["Alice"] == {"total": 2, "orphan": 1, "shared": [0]}
    assert owned["Bob"] == {"total": 2, "orphan": 1, "shared": [0]}
    # a pairwise intersection reproduces the co-owned count
    shared = set(owned["Alice"]["shared"]) & set(owned["Bob"]["shared"])
    assert len(shared) == 1


def test_template_is_repo_agnostic():
    # the engine claim: a data refresh or a different --repo must never ship
    # stale copy, so the template carries no target-repo literals
    template = (Path(__file__).parent.parent / "site" / "src"
                / "template.html").read_text(encoding="utf-8")
    for literal in ("FastVideo", "fastvideo", "hao-ai-lab", "Eighty-two"):
        assert literal not in template, f"hardcoded repo literal: {literal}"


def test_org_lens_shape_and_consistency():
    payload = build_payload(_frames())
    org = payload["org"]
    # curve: one point per scored contributor, monotone, ends at 1.0
    assert len(org["curve"]) == 3
    assert org["curve"] == sorted(org["curve"])
    assert org["curve"][-1] == 1.0
    # gini over ALL scored contributors (Carol's zero surviving lines included):
    # lines [130, 20, 0] -> 0.578
    assert org["gini"] == 0.578
    # hotspots require >=10 files per dir; the fixture's src/ has 3
    assert org["hotspots"] == []
    # departure risk: only Alice owns an orphan file (src/a.py, no second
    # contributor on record, centrality 0.02 of a 0.07 total)
    assert set(org["risk"]) == {"Alice"}
    a = org["risk"]["Alice"]
    assert a["files"] == 1
    assert a["no_second"] == 1
    assert a["nearest"] == []
    assert a["top"] == ["src/a.py"]
    assert a["cen_share"] == round(0.02 / 0.07, 4)


def test_org_risk_reconciles_with_compare_footprint():
    # one concept, one number: the sim's sole-owned count must equal the
    # compare view's owned.orphan for every author
    payload = build_payload(_frames())
    by = {a["name"]: a for a in payload["authors"]}
    for name, r in payload["org"]["risk"].items():
        assert r["files"] == by[name]["owned"]["orphan"]


def test_tier_counts_sum_to_authors():
    payload = build_payload(_frames())
    assert sum(t["count"] for t in payload["tiers"]) == 3
    assert [t["tier"] for t in payload["tiers"]] == [1, 2, 3]


def test_commit_counts_exclude_merges_and_sx_matches():
    payload = build_payload(_frames())
    by = {a["name"]: a for a in payload["authors"]}
    assert by["Alice"]["commits"] == 3
    assert by["Bob"]["commits"] == 2  # the merge commit does not count
    assert by["Carol"]["commits"] == 1
    for a in payload["authors"]:
        assert a["sx"] == round(float(np.log1p(a["commits"])), 4)
        assert sum(a["weekly"]) == a["commits"]  # weekly grid conserves totals


def test_weekly_grids_share_one_domain():
    payload = build_payload(_frames())
    lengths = {len(a["weekly"]) for a in payload["authors"]}
    assert len(lengths) == 1


def test_review_null_only_for_absent_reviewers():
    payload = build_payload(_frames())
    by = {a["name"]: a for a in payload["authors"]}
    assert by["Alice"]["review"] == {
        "count": 12, "distinct_authors": 4, "approval_rate": 0.75,
    }
    assert by["Bob"]["review"] is None
    assert by["Carol"]["review"] is None
    assert by["Bob"]["flags"]["review_imputed"] is True
    assert by["Alice"]["flags"]["bus_factor"] is True


def test_top_files_sorted_and_joined():
    payload = build_payload(_frames())
    by = {a["name"]: a for a in payload["authors"]}
    alice_files = by["Alice"]["top_files"]
    assert [f["path"] for f in alice_files] == ["src/b.py", "src/a.py"]  # by centrality
    assert alice_files[1]["orphan"] is True
    bob_files = by["Bob"]["top_files"]
    assert bob_files[0]["centrality"] == 0.0  # absent from coupling -> fillna(0)
    assert by["Carol"]["top_files"] == []


def test_field_labels_subset_and_ticks_bounded():
    payload = build_payload(_frames())
    names = {a["name"] for a in payload["authors"]}
    field = payload["field"]
    assert set(field["labeled"]) <= names
    assert len(field["labeled"]) <= 6
    xs = [t["x"] for t in field["x_ticks"]]
    assert xs == sorted(xs)
    assert all(0.0 <= x <= 1.0 for x in xs)
    tiers = {t["tier"] for t in payload["tiers"]}
    assert {t["t"] for t in field["tier_ticks"]} <= tiers
    assert all(0.0 <= t["x"] <= 1.0 for t in field["tier_ticks"])


def test_views_coords_normalized():
    payload = build_payload(_frames())
    for a in payload["authors"]:
        assert set(a["views"].keys()) == VIEW_KEYS
        for coords in a["views"].values():
            assert len(coords) == 2
            assert all(0.0 <= c <= 1.0 for c in coords)
        # activity view mirrors the scatter exactly
        assert a["views"]["activity"][1] == round(1 - a["impact"], 4)


def test_activity_x_proportional_to_sx():
    payload = build_payload(_frames())
    withc = [a for a in payload["authors"] if a["commits"] > 0]
    base = withc[0]
    for a in withc[1:]:
        if a["sx"] and base["sx"]:
            assert abs(
                a["views"]["activity"][0] / base["views"]["activity"][0]
                - a["sx"] / base["sx"]
            ) < 1e-2


def test_tier_layout_columns():
    payload = build_payload(_frames())
    by_tier = {}
    for a in payload["authors"]:
        by_tier.setdefault(a["tier"], set()).add(a["views"]["tiers"][0])
    xs = [next(iter(v)) for v in by_tier.values()]
    assert all(len(v) == 1 for v in by_tier.values())  # same tier -> same column
    assert len(set(xs)) == len(xs)                     # distinct tiers -> distinct x


def test_beeswarm_no_overlap_with_adversarial_ties():
    from build_site import FIELD_H, FIELD_M, FIELD_R, FIELD_W, beeswarm_layout

    pw = FIELD_W - FIELD_M["l"] - FIELD_M["r"]
    ph = FIELD_H - FIELD_M["t"] - FIELD_M["b"]
    # 60-way exact tie (the true-zero review block) plus scattered values
    x = np.array([0.366] * 60 + [0.1, 0.9, 0.5, 0.5001, 0.4999])
    out = beeswarm_layout(x, pw, ph)
    px = out[:, 0] * pw
    py = (out[:, 1] - 0.5) * ph
    n = len(x)
    for i in range(n):
        for j in range(i + 1, n):
            d = np.hypot(px[i] - px[j], py[i] - py[j])
            assert d >= 2 * FIELD_R - 0.05, f"overlap {i},{j}: {d:.2f}"
    # x fidelity: dither is bounded (2 columns max here -> half a pitch)
    assert np.max(np.abs(px - x * pw)) <= (2 * FIELD_R + 1.0)
    # everything stays inside the plot
    assert np.all(out >= 0.0) and np.all(out <= 1.0)


def test_github_logins_confirmed_only():
    payload = build_payload(_frames())
    by = {a["name"]: a for a in payload["authors"]}
    assert by["Alice"]["github"] == "alicehub"     # noreply email
    assert by["Bob"]["github"] is None             # no evidence -> no link
    assert by["Carol"]["github"] is None


def test_review_status_partial_when_flagged():
    frames = _frames()
    frames["reviews"] = frames["reviews"].assign(status="partial")
    assert build_payload(frames)["meta"]["review_status"] == "partial"
    payload = build_payload(_frames())
    assert payload["meta"]["review_status"] == "complete"


def test_rendered_page_is_self_contained_and_escaped():
    page = render_html(build_payload(_frames()))
    assert "@INJECT" not in page  # every marker replaced
    assert not EXTERNAL.search(page)
    # the raw close-tag from the hostile rationale must be escaped in the data blob
    blob = page.split("window.__DATA__ = ", 1)[1]
    blob = blob[: blob.index(";</script>")]
    assert "</script>" not in blob
    payload = json.loads(blob.replace("<\\/", "</"))
    assert payload["meta"]["n_authors"] == 3


def test_rendered_page_keeps_the_honest_framing():
    page = render_html(build_payload(_frames()))
    for sentence in [
        "within-tier order is not meaningful",
        "rejected baseline",
        "bus-factor",
        "no review data",
        "median-imputed",
        "Signals, not verdicts",
        "shown, not scored",
    ]:
        assert sentence in page, f"missing content-integrity sentence: {sentence}"


def test_rendered_page_social_meta():
    page = render_html(build_payload(_frames()))
    assert 'property="og:image"' in page
    assert 'name="twitter:card" content="summary_large_image"' in page
    # without SITE_URL the og:image falls back to a relative path
    assert 'content="og.png"' in page or 'content="http' in page


def test_rendered_page_field_and_links():
    page = render_html(build_payload(_frames()))
    assert 'role="radiogroup"' in page          # view switcher markup
    assert "aria-pressed" in page               # filter chips
    assert 'rel="noopener noreferrer"' in page or "noopener noreferrer" in page
    assert 'id="contrast"' not in page          # old scatter section removed
    assert "spectrum-strip" not in page         # old tick strip removed
    assert 'id="field"' in page
