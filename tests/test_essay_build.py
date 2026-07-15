"""Tests for the essay builder (scripts/build_essay.py).

The converter and guard units always run. Tests that need the local writing
files (drafts/ is gitignored) skip cleanly in CI, where those inputs do not
exist; the essay is a manually built page, not a CI artifact.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_essay  # noqa: E402

HAVE_DRAFTS = build_essay.DRAFT.exists() and build_essay.NUMBERS.exists()

FIXTURE = """# A title

*A dek line.*

*Numbers as of the [FREEZE-DATE] analysis.*

---

Intro paragraph with a stat of 0.44 [PROVISIONAL: refreeze] inline.

## A section

- **First** item with *emphasis*.
- Second item with a [link](https://example.com).

<!--pair-->

**Left** column paragraph.

**Right** column paragraph.

<!--/pair-->

[FIGURE 1: something]

*[FOOTER: dropped]*
"""


# ------------------------------------------------------------------ inline md
def test_render_inline_bold_italic_link():
    out = build_essay.render_inline("**b** and *i* and [t](https://x.y/z)")
    assert "<strong>b</strong>" in out
    assert "<em>i</em>" in out
    assert '<a href="https://x.y/z">t</a>' in out


def test_render_inline_escapes_html():
    assert "&lt;script&gt;" in build_essay.render_inline("<script>")


def test_render_inline_rejects_unconverted():
    with pytest.raises(SystemExit):
        build_essay.render_inline("dangling ** bold ** with spaces stays broken **")


# --------------------------------------------------------------------- parser
def test_parse_draft_preview_strips_markers():
    title, dek, stamp, body = build_essay.parse_draft(FIXTURE, frozen=False,
                                                      freeze_date="2026-01-01")
    assert title == "A title"
    assert "[PROVISIONAL" not in json.dumps(body)
    assert "2026-01-01 (preview" in stamp
    kinds = [k for k, _ in body]
    assert kinds == ["p", "h2", "ul", "pair", "figure"]
    pair = next(b for k, b in body if k == "pair")
    assert len(pair) == 2


def test_parse_draft_frozen_rejects_markers():
    with pytest.raises(SystemExit):
        build_essay.parse_draft(FIXTURE, frozen=True, freeze_date="2026-01-01")


def test_parse_draft_rejects_unknown_blocks():
    bad = FIXTURE.replace("[FIGURE 1: something]", "> a blockquote")
    with pytest.raises(SystemExit):
        build_essay.parse_draft(bad, frozen=False, freeze_date="2026-01-01")


def test_parse_draft_rejects_unclosed_pair():
    bad = FIXTURE.replace("<!--/pair-->", "")
    with pytest.raises(SystemExit):
        build_essay.parse_draft(bad, frozen=False, freeze_date="2026-01-01")


# ---------------------------------------------------------------- number guard
def test_guard_accepts_json_backed_numbers():
    numbers = {"_provenance": {"d": "2026-07-12"}, "x": {"n": 346, "share": 0.589}}
    html = "<p>He has 346 commits and holds 59% as of 2026-07-12.</p>"
    assert build_essay.guard_numbers(html, numbers) == []


def test_guard_flags_untraceable_numbers():
    numbers = {"_provenance": {}, "x": {"n": 5}}
    html = "<p>A made-up 12,345 sneaks in.</p>"
    assert build_essay.guard_numbers(html, numbers) == ["12,345"]


def test_guard_ignores_style_and_svg():
    numbers = {"_provenance": {}, "x": {}}
    html = ("<style>.a{width:3.75rem;color:#736D65}</style>"
            "<svg><text>999</text></svg><p>prose</p>")
    assert build_essay.guard_numbers(html, numbers) == []


# ------------------------------------------------- full draft (local inputs)
needs_drafts = pytest.mark.skipif(not HAVE_DRAFTS, reason="drafts/ not present (CI)")


@needs_drafts
def test_full_draft_parses_and_builds():
    numbers = json.loads(build_essay.NUMBERS.read_text())
    html, title, dek = build_essay.build_html(numbers, frozen=False)
    assert title == "Two org shapes, one engine"
    assert html.count("<svg") == 4
    assert 'class="pair"' in html
    assert 'class="mn"' in html
    assert "<!--@INJECT:" not in html
    assert "[PROVISIONAL" not in html and "[VERIFY" not in html
    # self-contained: fonts inlined, no external subresources
    assert "data:font/woff2" in html


@needs_drafts
def test_sidenote_anchors_each_match_one_paragraph():
    # build_html exits if an anchor matches zero or several paragraphs;
    # a direct check keeps the failure message local when the draft is edited.
    # Notes attach to top-level paragraphs only (parse_draft's "p" blocks),
    # matching render_body's placement semantics.
    numbers = json.loads(build_essay.NUMBERS.read_text())
    _, _, _, body = build_essay.parse_draft(build_essay.DRAFT.read_text(),
                                            frozen=False, freeze_date="x")
    paragraphs = [b for k, b in body if k == "p"]
    for note in build_essay.sidenotes(numbers):
        hits = [p for p in paragraphs if note["anchor"] in p]
        assert len(hits) == 1, f"anchor {note['anchor']!r} matched {len(hits)}"
