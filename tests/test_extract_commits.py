"""Unit tests for the commit-extraction helpers (pure functions, no git needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from extract_commits import (  # noqa: E402
    chain_renames, is_bot, is_excluded, parse_coauthors, rename_target, split_int,
)


def test_split_int_conserves_total():
    assert split_int(1, 5) == [1, 0, 0, 0, 0]
    assert split_int(10, 3) == [4, 3, 3]
    assert sum(split_int(7, 4)) == 7
    assert split_int(0, 3) == [0, 0, 0]


def test_rename_target_simple_and_brace():
    assert rename_target("old.py => new.py") == "new.py"
    assert rename_target("src/{old => new}/file.py") == "src/new/file.py"
    assert rename_target("unchanged/path.py") == "unchanged/path.py"


def test_is_excluded():
    assert is_excluded("node_modules/foo/bar.js")
    assert is_excluded("a/dist/b.js")
    assert is_excluded("uv.lock")
    assert is_excluded("web/app.min.js")
    assert not is_excluded("src/model/attention.py")


def test_is_bot():
    assert is_bot("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com")
    assert is_bot("github-actions", "github-actions[bot]@users.noreply.github.com")
    assert is_bot("GitHub", "noreply@github.com".replace("noreply", "web-flow"))
    assert not is_bot("William Lin", "wlsaidhi@gmail.com")


def test_chain_renames_follows_multi_hop():
    # Newest first: b.py -> c.py happened after a.py -> b.py, so a.py chains to c.py.
    pairs = [("b.py", "c.py"), ("a.py", "b.py")]
    m = chain_renames(pairs)
    assert m == {"b.py": "c.py", "a.py": "c.py"}
    # A rename cycle collapses to a harmless no-op for the round-tripped path.
    m = chain_renames([("b.py", "a.py"), ("a.py", "b.py")])
    assert m == {"b.py": "a.py"}
    assert chain_renames([]) == {}


def test_parse_coauthors():
    body = (
        "Fix attention kernel\n\n"
        "Co-authored-by: Wei Zhou <wzhou322@gatech.edu>\n"
        "Co-authored-by: Kevin Lin <42618777+kevin314@users.noreply.github.com>\n"
    )
    assert parse_coauthors(body) == [
        ("Wei Zhou", "wzhou322@gatech.edu"),
        ("Kevin Lin", "42618777+kevin314@users.noreply.github.com"),
    ]
    assert parse_coauthors("no trailers here") == []
