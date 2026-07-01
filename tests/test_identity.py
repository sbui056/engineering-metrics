"""Unit tests for the identity resolver — the riskiest, most load-bearing logic."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from identity import IdentityResolver, noreply_login, parse_mailmap  # noqa: E402


def _resolve(counts):
    return IdentityResolver.from_identity_counts(counts)


def test_merge_by_shared_email():
    r = _resolve({("Zhang Peiyuan", "a@x.com"): 73, ("Peiyuan Zhang", "a@x.com"): 17})
    assert r.canonical("Zhang Peiyuan", "a@x.com") == r.canonical("Peiyuan Zhang", "a@x.com")
    # Highest-count name wins the label.
    assert r.canonical("Peiyuan Zhang", "a@x.com") == "Zhang Peiyuan"


def test_merge_by_noreply_login_across_different_emails():
    r = _resolve({
        ("Yongqi Chen", "144848849+BrianChen1129@users.noreply.github.com"): 61,
        ("Brian Chen", "144848849+BrianChen1129@users.noreply.github.com"): 5,
    })
    assert r.canonical("Brian Chen", "144848849+BrianChen1129@users.noreply.github.com") == "Yongqi Chen"


def test_merge_name_equals_login():
    # Top-contributor split: real name + noreply, and handle-as-name + personal email.
    r = _resolve({
        ("William Lin", "SolitaryThinker@users.noreply.github.com"): 240,
        ("SolitaryThinker", "wlsaidhi@gmail.com"): 5,
    })
    assert r.canonical("SolitaryThinker", "wlsaidhi@gmail.com") == "William Lin"


def test_merge_by_exact_full_name_across_emails():
    r = _resolve({("Kaiqin Kong", "k1kong@ucsd.edu"): 13, ("Kaiqin Kong", "hiyori@gmail.com"): 6})
    assert r.canonical("Kaiqin Kong", "k1kong@ucsd.edu") == r.canonical("Kaiqin Kong", "hiyori@gmail.com")


def test_distinct_people_do_not_merge():
    r = _resolve({("Alice Smith", "alice@a.com"): 10, ("Bob Jones", "bob@b.com"): 10})
    assert r.canonical("Alice Smith", "alice@a.com") != r.canonical("Bob Jones", "bob@b.com")


def test_single_first_name_does_not_merge():
    # Two different people who both go by "Alex" must NOT merge on first name alone.
    r = _resolve({("Alex", "alex1@a.com"): 5, ("Alex", "alex2@b.com"): 5})
    assert r.canonical("Alex", "alex1@a.com") != r.canonical("Alex", "alex2@b.com")


def test_unseen_identity_fallback_is_stable():
    r = _resolve({("Alice Smith", "alice@a.com"): 10})
    assert r.canonical("New Person", "new@z.com") == "New Person"


def test_noreply_login_parsing():
    assert noreply_login("144848849+BrianChen1129@users.noreply.github.com") == "brianchen1129"
    assert noreply_login("SolitaryThinker@users.noreply.github.com") == "solitarythinker"
    assert noreply_login("plain@gmail.com") is None


def test_mailmap_parsing(tmp_path):
    (tmp_path / ".mailmap").write_text(
        "Canonical Name <canon@x.com> Old Name <old@y.com>\n", encoding="utf-8"
    )
    mm = parse_mailmap(tmp_path)
    assert mm[("old name", "old@y.com")] == ("Canonical Name", "canon@x.com")
