"""Engineering Impact Dashboard — Streamlit app over data/scored.parquet.

Reports signals, not performance verdicts, over a fixed data window. The
leaderboard binds to the scored.parquet schema; every signal is shown with the
flags that keep it honest (bus-factor risk, imputed review data), and the
methodology section renders the caveats verbatim rather than hiding them.

Run: streamlit run dashboard.py
"""
from __future__ import annotations

from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import config

# Validated reference palette (dataviz skill): blue = the one sequential hue,
# secondary ink for direct labels; status colors are reserved for status only.
BLUE = "#2a78d6"
INK_SECONDARY = "#52514e"

SIGNAL_LABELS = {
    "ownership_concentration": "Ownership concentration",
    "code_survival_tenure_normalized": "Code survival (tenure-norm.)",
    "coupling_criticality": "Coupling criticality (owned)",
    "review_leverage": "Review leverage",
}


@st.cache_data
def load_parquet(name: str, mtime: float) -> pd.DataFrame:
    """mtime is part of the cache key so a pipeline rerun invalidates the cache."""
    return pd.read_parquet(config.DATA_DIR / f"{name}.parquet")


def load(name: str) -> pd.DataFrame:
    path = config.DATA_DIR / f"{name}.parquet"
    if not path.exists():
        st.error(f"Missing {path}. Run `make all` first.")
        st.stop()
    return load_parquet(name, path.stat().st_mtime)


def flags_text(row: pd.Series) -> str:
    flags = []
    if row["bus_factor_flag"]:
        flags.append("⚠️ bus-factor")
    if row["review_data_imputed"]:
        flags.append("◌ no review data")
    return "  ".join(flags)


def signal_bars(row: pd.Series) -> alt.Chart:
    d = pd.DataFrame({
        "signal": [SIGNAL_LABELS[k] for k in SIGNAL_LABELS],
        "percentile": [float(row[k]) for k in SIGNAL_LABELS],
        "note": [
            "median-imputed" if k == "review_leverage" and row["review_data_imputed"]
            else "" for k in SIGNAL_LABELS
        ],
    })
    bars = alt.Chart(d).mark_bar(
        color=BLUE, height=14, cornerRadiusEnd=4,
    ).encode(
        x=alt.X("percentile:Q", scale=alt.Scale(domain=[0, 1]),
                axis=alt.Axis(format=".0%", title="percentile within repo",
                              tickCount=5)),
        y=alt.Y("signal:N", sort=list(SIGNAL_LABELS.values()), title=None),
        tooltip=[alt.Tooltip("signal:N"),
                 alt.Tooltip("percentile:Q", format=".1%"),
                 alt.Tooltip("note:N", title="caveat")],
    )
    labels = alt.Chart(d).mark_text(
        align="left", dx=4, color=INK_SECONDARY, fontSize=12,
    ).encode(
        x="percentile:Q",
        y=alt.Y("signal:N", sort=list(SIGNAL_LABELS.values())),
        text=alt.Text("percentile:Q", format=".0%"),
    )
    return (bars + labels).properties(height=140)


def activity_vs_impact(scored: pd.DataFrame, commits: pd.DataFrame) -> alt.Chart:
    counts = (
        commits[~commits["is_merge"]]
        .groupby("author_canonical")["commit_hash"].nunique()
        .rename("commit_count").reset_index()
    )
    d = scored.merge(counts, on="author_canonical", how="left").fillna(
        {"commit_count": 0}
    )
    points = alt.Chart(d).mark_circle(size=90, color=BLUE, opacity=0.75).encode(
        x=alt.X("commit_count:Q", scale=alt.Scale(type="symlog"),
                axis=alt.Axis(title="commits (rejected baseline, log scale)",
                              values=[1, 3, 10, 30, 100, 300])),
        y=alt.Y("impact_score:Q", scale=alt.Scale(domain=[0, 1]),
                title="impact score"),
        tooltip=[
            alt.Tooltip("author_canonical:N", title="author"),
            alt.Tooltip("commit_count:Q", title="commits"),
            alt.Tooltip("impact_score:Q", format=".3f"),
            alt.Tooltip("tier:Q"),
        ],
    )
    # Direct-label only the divergent cases: high impact per commit or many
    # commits with modest impact — the selective-label rule, not every point.
    d = d.assign(rank_gap=(
        d["commit_count"].rank(ascending=False) - d["impact_score"].rank(ascending=False)
    ))
    label_set = pd.concat([d.nlargest(3, "rank_gap"), d.nsmallest(3, "rank_gap")])
    labels = alt.Chart(label_set).mark_text(
        align="left", dx=8, dy=-6, fontSize=11, color=INK_SECONDARY,
    ).encode(x="commit_count:Q", y="impact_score:Q", text="author_canonical:N")
    return (points + labels).properties(height=340)


def main() -> None:
    st.set_page_config(page_title="Engineering Impact — FastVideo",
                       page_icon="📐", layout="wide")

    scored = load("scored")
    commits = load("commits_clean")
    reviews = load("reviews")
    ownership_file = load("ownership_file")
    coupling = load("coupling")

    window_start = commits["date"].min().date()
    window_end = commits["date"].max().date()
    review_status = ("complete" if (not reviews.empty
                     and (reviews["status"] == "complete").all()) else "partial")

    st.title("Engineering Impact Dashboard")
    st.markdown(
        "**Impact = the degree to which an engineer's work is depended on, "
        "trusted, and hard to replace.** Scored as the equal-weight mean of "
        "four percentile-normalized signals: ownership concentration, code "
        "survival, coupling criticality of owned files, and review leverage. "
        "Raw commit count and lines-of-code are *rejected baselines* — shown "
        "only as a contrast below, never scored."
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Contributors scored", len(scored))
    c2.metric("Data window", f"{window_start} → {window_end}")
    c3.metric("Review data", review_status,
              help="complete: absence of reviews is a true zero. "
                   "partial: missing reviewers are median-imputed and badged.")
    c4.metric("Rank tiers", int(scored["tier"].max()),
              help="Contributors within an indistinguishable score epsilon "
                   "share a tier; within-tier order is not meaningful.")

    # ---------------- Leaderboard ----------------
    st.header("Leaderboard")
    st.caption(
        "Signals, not verdicts. ⚠️ bus-factor = sole major owner of at least "
        "one file — the same concentration that makes someone hard to replace "
        "is an orphan risk, so it is scored positively **and** flagged. "
        "◌ no review data = review signal median-imputed, not observed."
    )
    table = scored.copy()
    table.insert(0, "rank", np.arange(1, len(table) + 1))
    table["flags"] = table.apply(flags_text, axis=1)
    show_all = st.toggle("Show all shown-not-scored columns", value=False)
    cols = ["rank", "tier", "author_canonical", "impact_score",
            "ownership_concentration", "code_survival_tenure_normalized",
            "coupling_criticality", "review_leverage", "flags",
            "one_line_rationale"]
    if show_all:
        cols[9:9] = ["breadth_files", "breadth_dirs", "recency_days", "consistency"]
    st.dataframe(
        table[cols],
        hide_index=True,
        height=560,
        column_config={
            "rank": st.column_config.NumberColumn("#", width="small"),
            "tier": st.column_config.NumberColumn(
                "tier", width="small",
                help="Same tier = statistically indistinguishable scores."),
            "author_canonical": st.column_config.TextColumn("author"),
            "impact_score": st.column_config.ProgressColumn(
                "impact", format="%.3f", min_value=0.0, max_value=1.0),
            "ownership_concentration": st.column_config.ProgressColumn(
                "ownership", format="%.2f", min_value=0.0, max_value=1.0),
            "code_survival_tenure_normalized": st.column_config.ProgressColumn(
                "survival", format="%.2f", min_value=0.0, max_value=1.0),
            "coupling_criticality": st.column_config.ProgressColumn(
                "coupling", format="%.2f", min_value=0.0, max_value=1.0),
            "review_leverage": st.column_config.ProgressColumn(
                "review", format="%.2f", min_value=0.0, max_value=1.0),
            "breadth_files": st.column_config.NumberColumn(
                "files†", help="Shown, not scored."),
            "breadth_dirs": st.column_config.NumberColumn(
                "dirs†", help="Shown, not scored."),
            "recency_days": st.column_config.NumberColumn(
                "recency (d)†", help="Days since last commit at window end. "
                "Shown, not scored."),
            "consistency": st.column_config.NumberColumn(
                "consistency†", format="%.2f",
                help="Active weeks over the author's own active span. "
                "Shown, not scored."),
            "flags": st.column_config.TextColumn("flags"),
            "one_line_rationale": st.column_config.TextColumn(
                "rationale", width="large"),
        },
    )
    st.caption("† shown-not-scored: computed and displayed, deliberately "
               "excluded from the headline score to keep it explainable.")

    # ---------------- Author detail ----------------
    st.header("Author detail")
    author = st.selectbox("Contributor", scored["author_canonical"])
    row = scored.set_index("author_canonical").loc[author]

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Impact score", f"{row['impact_score']:.3f}")
    rank = int((scored["author_canonical"] == author).idxmax()) + 1
    d2.metric("Rank / tier", f"#{rank} · tier {int(row['tier'])}")
    d3.metric("Last commit", f"{int(row['recency_days'])} d before window end")
    d4.metric("Breadth", f"{int(row['breadth_files'])} files · "
                         f"{int(row['breadth_dirs'])} dirs")
    st.markdown(f"*{row['one_line_rationale']}*")

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Signal percentiles")
        st.altair_chart(signal_bars(row), use_container_width=True)
        rev = reviews[reviews["author_canonical"] == author]
        if len(rev):
            r = rev.iloc[0]
            st.caption(
                f"Reviews given: **{int(r['review_count'])}** across "
                f"**{int(r['distinct_authors_reviewed'])}** distinct authors · "
                f"approval rate {r['approval_rate']:.0%} (context, not scored)")
        else:
            st.caption("No PR reviews on record for this contributor.")
    with right:
        st.subheader("Highest-centrality owned files")
        owned = (
            ownership_file[ownership_file["author_canonical"] == author]
            .merge(coupling[["file_path", "centrality_score"]],
                   on="file_path", how="left")
            .fillna({"centrality_score": 0.0})
            .sort_values("centrality_score", ascending=False)
            .head(10)
        )
        st.dataframe(
            owned[["file_path", "blame_share", "centrality_score", "is_orphan_risk"]],
            hide_index=True,
            column_config={
                "file_path": st.column_config.TextColumn("file", width="large"),
                "blame_share": st.column_config.NumberColumn(
                    "blame share", format="percent"),
                "centrality_score": st.column_config.NumberColumn(
                    "centrality", format="%.4f"),
                "is_orphan_risk": st.column_config.CheckboxColumn("single-owner"),
            },
        )

    # ---------------- Rejected-baseline contrast ----------------
    st.header("Activity is not impact")
    st.markdown(
        "Commit count (x, log scale) against the impact score (y). If raw "
        "activity were a good proxy, this would be a straight line; the "
        "labeled outliers are why commit count stays a rejected baseline."
    )
    st.altair_chart(activity_vs_impact(scored, commits), use_container_width=True)

    # ---------------- Methodology ----------------
    st.header("Methodology & caveats")
    st.markdown(
        """
**Formula.** `impact = 0.25·pct(ownership) + 0.25·pct(survival) +
0.25·pct(coupling) + 0.25·pct(review leverage)`, each percentile-normalized
over this repo's contributors. Equal weights are a deliberate, transparent
choice, not a calibrated one — with no ground truth at this sample size,
unit weights are hard to beat (Dawes 1979).

**The four signals.**
- *Ownership concentration* — size-weighted blame-share over files where the
  author is a major owner (Bird's ≥5% + absolute-floor rule).
- *Code survival* — surviving lines vs. lines added, tenure-normalized against
  an exponential-decay baseline; recent additions excluded (too young to judge).
- *Coupling criticality* — PageRank centrality of files in the co-change
  graph, weighted by the author's blame share: the criticality of what they
  **own**, not what they touched.
- *Review leverage* — distinct authors reviewed × log(1+reviews given).

**Limits — read before quoting a number.**
- Blame only sees lines that survived to HEAD: it favors code that hasn't
  been rewritten and undercounts foundational-but-refactored work.
- Coupling has a cold-start blind spot (a load-bearing but stable file scores
  low) and can reward entanglement, which is sometimes a design smell.
- Ownership concentration is dual-use: "hard to replace" **and** "bus-factor
  risk". It is scored positively but always flagged, never silently rewarded.
- Signal redundancy: owned-criticality and ownership concentration both scale
  with blame share, so ownership carries more than its nominal 25% — the four
  signals are really ~three independent dimensions. Conscious trade-off.
- Review leverage measures reach, not depth: a one-line LGTM counts like a
  substantive review.
- Every signal is a gameable proxy (Goodhart): publishing this formula as a
  target would erode it — territorial hoarding, split PRs, rubber stamps.
- Not measured at all: mentoring, design, incident response, unblocking
  others, and any off-repo work.
- Raw commit count and lines-of-code remain rejected baselines, shown above
  only as a contrast, never scored.
        """
    )


if __name__ == "__main__":
    main()
