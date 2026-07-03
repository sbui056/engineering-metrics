"""Fetch PR reviews from GitHub into data/reviews.parquet (Track B).

Pulls every PR and its submitted reviews for the target repo via the GitHub
REST API, bridges each GitHub login to a git identity (commits API first, then
noreply-login / profile-name fallbacks), and canonicalizes through identity.py
so reviewers land in the same author space as commits.

Per the global rules: bot reviewers are dropped, reviews on bot-authored PRs
are dropped, and self-reviews (same login OR same canonical identity) never
count. Review "reach" is what's measured: review_count plus the number of
distinct canonical PR authors reviewed for. approval_rate is displayed
context, never scored.

API responses are cached under .cache/github/<owner>_<repo>/ keyed by the
PR's updated_at, so reruns only refetch PRs that changed. If the fetch is cut
short (rate limit, network), whatever was gathered is still written with
status="partial" instead of failing the pipeline.

Usage: python scripts/fetch_reviews.py --repo target-repo/FastVideo
       (GITHUB_TOKEN from the environment or .env; unauthenticated works but
        is limited to 60 requests/hour and will usually end partial)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from extract_commits import is_bot  # noqa: E402
from identity import IdentityResolver, build_from_repo  # noqa: E402

API = "https://api.github.com"
REVIEWS_COLUMNS = [
    "author_canonical", "reviewer_login", "review_count",
    "distinct_authors_reviewed", "approval_rate", "status",
]
_GITHUB_URL_RE = re.compile(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$")


class RateLimitExceeded(Exception):
    """Raised when the API rate limit would force an impractically long wait."""


class GitHubClient:
    """Thin requests wrapper: auth header, pagination, short rate-limit waits."""

    def __init__(self, token: str | None, max_wait_s: int = 180):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.max_wait_s = max_wait_s
        self.request_count = 0

    def get(self, url: str, params: dict | None = None) -> requests.Response:
        while True:
            resp = self.session.get(url, params=params, timeout=30)
            self.request_count += 1
            if resp.status_code in (403, 429):
                wait = None
                if resp.headers.get("X-RateLimit-Remaining") == "0":
                    reset = int(resp.headers.get("X-RateLimit-Reset", "0"))
                    wait = max(0.0, reset - time.time()) + 2
                elif "Retry-After" in resp.headers:
                    # Secondary/abuse limit: Remaining is nonzero but GitHub
                    # still asks for a pause — honor it instead of aborting.
                    wait = float(resp.headers["Retry-After"]) + 1
                if wait is not None:
                    if wait > self.max_wait_s:
                        raise RateLimitExceeded(
                            f"rate limit exhausted; resets in {wait:.0f}s"
                        )
                    time.sleep(wait)
                    continue
            resp.raise_for_status()
            return resp

    def paginate(self, path: str, params: dict | None = None):
        url = f"{API}{path}"
        params = dict(params or {}, per_page=100)
        while url:
            resp = self.get(url, params=params)
            yield from resp.json()
            url = resp.links.get("next", {}).get("url")
            params = None  # the `next` link already carries the query string


def detect_github_repo(repo_path: Path) -> str:
    """owner/name from the target clone's origin remote."""
    url = subprocess.run(
        ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    m = _GITHUB_URL_RE.search(url)
    if not m:
        raise SystemExit(f"Cannot parse a GitHub owner/repo from remote: {url!r}")
    return m.group(1)


def fetch_pulls(client: GitHubClient, gh_repo: str) -> list[dict]:
    """All PRs (open + closed), trimmed to the fields the pipeline needs."""
    pulls = []
    for pr in client.paginate(f"/repos/{gh_repo}/pulls", {"state": "all"}):
        user = pr.get("user") or {}  # deleted accounts come back without a user
        if not user.get("login"):
            continue
        pulls.append({
            "number": pr["number"],
            "author_login": user["login"],
            "updated_at": pr.get("updated_at") or "",
        })
    return pulls


def fetch_pr_reviews(
    client: GitHubClient, gh_repo: str, pr: dict, cache_dir: Path, refresh: bool
) -> tuple[list[dict], bool]:
    """Submitted reviews for one PR as [{login, state}], cached by updated_at."""
    cache_file = cache_dir / f"pr_{pr['number']}.json"
    if not refresh and cache_file.exists():
        cached = json.loads(cache_file.read_text())
        if cached.get("updated_at") == pr["updated_at"]:
            return cached["reviews"], True
    reviews = [
        {"login": r["user"]["login"], "state": r.get("state") or ""}
        for r in client.paginate(f"/repos/{gh_repo}/pulls/{pr['number']}/reviews")
        if r.get("user") and r["user"].get("login")
    ]
    cache_file.write_text(json.dumps({"updated_at": pr["updated_at"], "reviews": reviews}))
    return reviews, False


def bridge_logins(
    client: GitHubClient, gh_repo: str, logins: set[str], cache_file: Path
) -> dict[str, list[str] | None]:
    """login -> [git name, git email] via the commits API, else profile name.

    Cached across runs; a login with no commits and no profile name maps to None.
    """
    bridge: dict[str, list[str] | None] = {}
    if cache_file.exists():
        bridge = json.loads(cache_file.read_text())
    todo = sorted(l for l in logins if l not in bridge)
    for i, login in enumerate(tqdm(todo, desc="bridging logins", unit="login",
                                   disable=not todo)):
        ident: list[str] | None = None
        try:
            commits = client.get(
                f"{API}/repos/{gh_repo}/commits",
                params={"author": login, "per_page": 1},
            ).json()
            if commits:
                author = (commits[0].get("commit") or {}).get("author") or {}
                if author.get("email"):
                    ident = [author.get("name") or "", author["email"]]
            if ident is None:
                profile = client.get(f"{API}/users/{login}").json()
                if profile.get("name"):
                    ident = [profile["name"], ""]
        except requests.HTTPError:
            ident = None  # e.g. 404/422 for odd accounts; fall through to login-only
        bridge[login] = ident
        if i % 20 == 19:  # checkpoint so an aborted run keeps most of its work
            cache_file.write_text(json.dumps(bridge))
    if todo:
        cache_file.write_text(json.dumps(bridge))
    return bridge


def make_login_resolver(resolver: IdentityResolver, bridge: dict[str, list[str] | None]):
    """Return login -> author_canonical using bridge data, then resolver fallbacks."""

    def resolve(login: str) -> str:
        ident = bridge.get(login)
        if ident and ident[1]:  # bridged to a real git email: strongest signal
            c = resolver.lookup(ident[0], ident[1])
            if c:  # only when it lands on a KNOWN author — a stray email the
                return c  # clone never saw must not shadow the login match below
        c = resolver.lookup_login(login)  # committed via a noreply email
        if c:
            return c
        if ident and ident[0]:  # profile display name matches a git author name
            c = resolver.lookup_name(ident[0])
            if c:
                return c
        if ident and ident[1]:  # unseen everywhere: stable human-readable label
            return resolver.canonical(ident[0], ident[1])
        return login  # never committed: the login is its own identity

    return resolve


def aggregate(
    review_events: list[tuple[int, str, str]],
    pr_authors: dict[int, str],
    resolve,
    status: str,
) -> pd.DataFrame:
    """Roll (pr_number, reviewer_login, state) events up to one row per reviewer.

    Pure so it can be unit-tested: drops PENDING drafts, bot reviewers, reviews
    on bot-authored PRs, and self-reviews (login- or canonical-level). Logins
    that resolve to the same canonical author merge into one row.
    """
    per: dict[str, dict] = {}
    for number, login, state in review_events:
        state = (state or "").upper()
        if state == "PENDING":
            continue
        if is_bot(login, ""):
            continue
        author_login = pr_authors.get(number)
        if author_login is None or is_bot(author_login, ""):
            continue
        if login == author_login:
            continue
        reviewer_c = resolve(login)
        author_c = resolve(author_login)
        if reviewer_c == author_c:
            continue  # same human under two logins
        d = per.setdefault(
            reviewer_c, {"logins": set(), "count": 0, "approved": 0, "authors": set()}
        )
        d["logins"].add(login)
        d["count"] += 1
        d["approved"] += state == "APPROVED"
        d["authors"].add(author_c)

    rows = [
        {
            "author_canonical": canon,
            "reviewer_login": ",".join(sorted(d["logins"])),
            "review_count": d["count"],
            "distinct_authors_reviewed": len(d["authors"]),
            "approval_rate": d["approved"] / d["count"] if d["count"] else 0.0,
            "status": status,
        }
        for canon, d in per.items()
    ]
    df = pd.DataFrame(rows, columns=REVIEWS_COLUMNS)
    df = df.astype({
        "review_count": "int64",
        "distinct_authors_reviewed": "int64",
        "approval_rate": "float64",
    })
    return df.sort_values(
        ["review_count", "author_canonical"], ascending=[False, True]
    ).reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch PR reviews into reviews.parquet.")
    ap.add_argument("--repo", default=None, help="Target repo path (or REPO_PATH env).")
    ap.add_argument("--github-repo", default=None,
                    help="owner/name override (default: parsed from origin remote).")
    ap.add_argument("--refresh", action="store_true",
                    help="Ignore the per-PR review cache and refetch everything.")
    args = ap.parse_args()

    repo = config.get_repo_path(args.repo)
    config.ensure_dirs()
    gh_repo = args.github_repo or detect_github_repo(repo)
    token = config.get_github_token()
    if not token:
        print("WARNING: no GITHUB_TOKEN set; unauthenticated requests are limited "
              "to 60/hour and this will likely end with status=partial.")

    cache_dir = config.CACHE_DIR / "github" / gh_repo.replace("/", "_")
    cache_dir.mkdir(parents=True, exist_ok=True)
    client = GitHubClient(token)
    resolver = build_from_repo(repo)

    review_events: list[tuple[int, str, str]] = []
    pr_authors: dict[int, str] = {}
    status = "complete"
    cache_hits = 0
    try:
        pulls = fetch_pulls(client, gh_repo)
        for pr in tqdm(pulls, desc=f"reviews for {gh_repo}", unit="PR"):
            pr_authors[pr["number"]] = pr["author_login"]
            reviews, hit = fetch_pr_reviews(client, gh_repo, pr, cache_dir, args.refresh)
            cache_hits += hit
            review_events.extend(
                (pr["number"], r["login"], r["state"]) for r in reviews
            )
        logins = {l for _, l, _ in review_events} | set(pr_authors.values())
        logins = {l for l in logins if not is_bot(l, "")}
        bridge = bridge_logins(client, gh_repo, logins, cache_dir / "login_bridge.json")
    except (RateLimitExceeded, requests.RequestException) as exc:
        print(f"WARNING: fetch cut short ({exc}); writing partial data.")
        status = "partial"
        bridge = {}
        bridge_file = cache_dir / "login_bridge.json"
        if bridge_file.exists():  # reuse whatever bridging a prior run cached
            bridge = json.loads(bridge_file.read_text())

    resolve = make_login_resolver(resolver, bridge)
    df = aggregate(review_events, pr_authors, resolve, status)
    out = config.DATA_DIR / "reviews.parquet"
    df.to_parquet(out, index=False)

    known_authors = set(resolver.to_frame()["author_canonical"])
    unmatched = int((~df["author_canonical"].isin(known_authors)).sum())
    print(f"Wrote {out}  ({len(df):,} reviewers, status={status})")
    print(f"  PRs scanned:               {len(pr_authors):,}  ({cache_hits:,} from cache)")
    print(f"  review events kept:        {int(df['review_count'].sum()):,}")
    print(f"  API requests this run:     {client.request_count:,}")
    print(f"  reviewers with no commit identity (login kept as-is): {unmatched:,}")


if __name__ == "__main__":
    main()
