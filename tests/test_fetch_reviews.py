"""Unit tests for the review-aggregation logic (pure functions, no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from fetch_reviews import (  # noqa: E402
    REVIEWS_COLUMNS, aggregate, make_login_resolver,
)
from identity import IdentityResolver  # noqa: E402

_GITHUB_URL_RE = sys.modules["fetch_reviews"]._GITHUB_URL_RE


def _resolve_identity(login: str) -> str:
    """Toy canonical space: alice2 is a second login of Alice."""
    return {"alice": "Alice", "alice2": "Alice", "bob": "Bob", "carol": "Carol"}.get(
        login, login
    )


def test_aggregate_counts_and_approval_rate():
    events = [
        (1, "bob", "APPROVED"),
        (2, "bob", "CHANGES_REQUESTED"),
        (3, "bob", "COMMENTED"),
        (1, "carol", "APPROVED"),
    ]
    authors = {1: "alice", 2: "alice", 3: "carol"}
    df = aggregate(events, authors, _resolve_identity, "complete")
    bob = df[df["author_canonical"] == "Bob"].iloc[0]
    assert bob["review_count"] == 3
    assert bob["distinct_authors_reviewed"] == 2  # Alice and Carol
    assert bob["approval_rate"] == 1 / 3
    assert bob["reviewer_login"] == "bob"
    assert set(df["status"]) == {"complete"}
    assert list(df.columns) == REVIEWS_COLUMNS


def test_aggregate_excludes_self_bots_and_pending():
    events = [
        (1, "alice", "APPROVED"),            # login-level self-review
        (2, "alice2", "APPROVED"),           # canonical-level self-review (alice2 == Alice)
        (3, "dependabot[bot]", "APPROVED"),  # bot reviewer
        (4, "bob", "APPROVED"),              # review on a bot-authored PR
        (5, "bob", "PENDING"),               # unsubmitted draft review
        (99, "bob", "APPROVED"),             # PR not in the author map (deleted user)
    ]
    authors = {1: "alice", 2: "alice", 3: "carol", 4: "renovate[bot]", 5: "carol"}
    df = aggregate(events, authors, _resolve_identity, "complete")
    assert len(df) == 0


def test_aggregate_merges_logins_with_same_canonical():
    events = [
        (1, "alice", "APPROVED"),
        (2, "alice2", "COMMENTED"),
    ]
    authors = {1: "bob", 2: "carol"}
    df = aggregate(events, authors, _resolve_identity, "partial")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["author_canonical"] == "Alice"
    assert row["reviewer_login"] == "alice,alice2"
    assert row["review_count"] == 2
    assert row["distinct_authors_reviewed"] == 2
    assert row["status"] == "partial"


def test_aggregate_empty_has_schema_and_dtypes():
    df = aggregate([], {}, _resolve_identity, "partial")
    assert list(df.columns) == REVIEWS_COLUMNS
    assert df["review_count"].dtype == "int64"
    assert df["distinct_authors_reviewed"].dtype == "int64"
    assert df["approval_rate"].dtype == "float64"


def test_login_resolver_bridge_then_fallbacks():
    resolver = IdentityResolver.from_identity_counts({
        ("Alice Smith", "alice@example.com"): 10,
        ("Alice Smith", "123+alicehub@users.noreply.github.com"): 3,
        ("Bob Jones", "bob@example.com"): 5,
    })
    bridge = {
        "some-login": ["Alice Smith", "alice@example.com"],  # commits-API bridge
        "bobby": ["Bob Jones", ""],                          # profile-name only
        "stranger": None,                                    # nothing known
        # Bridged to an email the clone never saw: the noreply-login match must
        # still win over a fabricated singleton label.
        "alicehub": ["A. Smith", "stray@fork.example"],
        # Unseen everywhere but bridged: stable human-readable label.
        "outsider": ["Cody Yu", "cody@external.example"],
    }
    resolve = make_login_resolver(resolver, bridge)
    assert resolve("some-login") == "Alice Smith"     # via bridged git email
    assert resolve("alicehub") == "Alice Smith"       # stray email doesn't shadow login
    assert resolve("bobby") == "Bob Jones"            # via profile display name
    assert resolve("stranger") == "stranger"          # stays its own identity
    assert resolve("outsider") == "Cody Yu"           # fabricated but readable
    assert resolve("never-seen") == "never-seen"


def test_secondary_rate_limit_honors_retry_after(monkeypatch):
    from fetch_reviews import GitHubClient

    class FakeResponse:
        def __init__(self, status, headers=None):
            self.status_code = status
            self.headers = headers or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise AssertionError("raise_for_status called on limited response")

    responses = [
        FakeResponse(403, {"Retry-After": "3", "X-RateLimit-Remaining": "42"}),
        FakeResponse(200),
    ]
    slept = []
    client = GitHubClient(token=None)
    client.session = type("S", (), {"get": lambda self, *a, **k: responses.pop(0)})()
    monkeypatch.setattr("fetch_reviews.time.sleep", slept.append)
    resp = client.get("https://api.example/x")
    assert resp.status_code == 200
    assert slept == [4.0]  # Retry-After + 1, not an abort to status=partial


def test_github_url_regex():
    for url in (
        "https://github.com/hao-ai-lab/FastVideo.git",
        "https://github.com/hao-ai-lab/FastVideo",
        "git@github.com:hao-ai-lab/FastVideo.git",
    ):
        m = _GITHUB_URL_RE.search(url)
        assert m and m.group(1) == "hao-ai-lab/FastVideo", url
