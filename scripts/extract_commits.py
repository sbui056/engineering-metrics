"""Extract and clean commit history into data/commits_clean.parquet.

Parses full `git log --numstat` history of the target repo and applies the
project's global rules: bot filtering, identity canonicalization (via
identity.py), excluded generated/vendored paths, first-parent merge handling,
binary -> 0, and Co-authored-by credit split equally among the committer and
each co-author.

Usage: python scripts/extract_commits.py --repo target-repo/FastVideo
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from identity import build_from_repo  # noqa: E402

RS, US = "\x1e", "\x1f"  # record / field separators unlikely to appear in git data

# Bot and CI accounts (substring match, case-insensitive, on name and email).
# Target-specific automation/co-author accounts are added via the BOT_EXTRA env var.
BOT_PATTERNS = (
    "[bot]", "dependabot", "renovate", "greenkeeper", "semantic-release",
    "github-actions", "actions-user", "web-flow",
)
_ALL_BOT_PATTERNS = tuple(BOT_PATTERNS) + tuple(p.lower() for p in config.get_bot_extra())

# Excluded generated/vendored locations.
EXCLUDED_DIR_SEGMENTS = {"dist", "build", "vendor", "node_modules", ".git", "__pycache__"}
LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock",
    "Cargo.lock", "Gemfile.lock", "composer.lock", "go.sum", "Pipfile.lock",
}
_COAUTHOR_RE = re.compile(r"^\s*Co-authored-by:\s*(.*?)\s*<([^>]+)>\s*$", re.I | re.M)


def is_bot(name: str, email: str) -> bool:
    blob = f"{name} {email}".lower()
    return any(p in blob for p in _ALL_BOT_PATTERNS)


def is_excluded(path: str) -> bool:
    parts = path.split("/")
    if any(seg in EXCLUDED_DIR_SEGMENTS for seg in parts):
        return True
    if parts[-1] in LOCKFILES:
        return True
    if parts[-1].endswith((".min.js", ".min.css")):
        return True
    return False


def rename_target(path: str) -> str:
    """Return the new path from a numstat rename entry ('old => new' or 'a/{b => c}/d')."""
    if "=>" not in path:
        return path
    if "{" in path and "}" in path:
        pre, rest = path.split("{", 1)
        mid, post = rest.split("}", 1)
        _, new = (s.strip() for s in mid.split("=>"))
        return (pre + new + post).replace("//", "/")
    return path.split("=>", 1)[1].strip()


def split_int(total: int, k: int) -> list[int]:
    """Split an int total into k parts summing exactly to total (remainder to the front)."""
    base, rem = divmod(total, k)
    return [base + (1 if i < rem else 0) for i in range(k)]


def parse_coauthors(body: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in _COAUTHOR_RE.finditer(body)]


def run_git_log(repo: Path) -> str:
    fmt = f"{RS}%H{US}%aI{US}%an{US}%ae{US}%P{US}%B{US}"
    return subprocess.run(
        ["git", "-C", str(repo), "log", "--numstat", "-M",
         "--diff-merges=first-parent", f"--format={fmt}"],
        capture_output=True, text=True, errors="replace", check=True,
    ).stdout


def extract(repo: Path):
    resolver = build_from_repo(repo)
    raw = run_git_log(repo)

    rows = []
    total_commits = bot_commits = merge_commits = 0
    raw_ids: set[tuple[str, str]] = set()
    canon_ids: set[str] = set()

    for chunk in raw.split(RS):
        if not chunk.strip():
            continue
        fields = chunk.split(US, 6)
        if len(fields) < 7:
            continue
        commit_hash, date_s, name, email, parents, body, tail = fields
        total_commits += 1
        is_merge = len(parents.split()) > 1
        if is_merge:
            merge_commits += 1

        # Credited authors = commit author + Co-authored-by trailers, humans only.
        credited = [(name, email)] + parse_coauthors(body)
        if is_bot(name, email):
            bot_commits += 1
        humans = [(n, e) for (n, e) in credited if not is_bot(n, e)]
        if not humans:
            continue
        # Collapse to distinct canonical contributors: someone credited as both
        # author and co-author counts once. Keep the first raw email per person.
        contributors: list[tuple[str, str]] = []  # (author_canonical, raw_email)
        canon_seen: set[str] = set()
        for (n, e) in humans:
            raw_ids.add((n, e))
            c = resolver.canonical(n, e)
            if c not in canon_seen:
                canon_seen.add(c)
                canon_ids.add(c)
                contributors.append((c, e))

        # Parse this commit's numstat file entries.
        files = []
        for line in tail.splitlines():
            if not line.strip():
                continue
            cols = line.split("\t")
            if len(cols) != 3:
                continue
            a, d, path = cols
            path = rename_target(path)
            if is_excluded(path):
                continue
            adds = 0 if a == "-" else int(a)
            dels = 0 if d == "-" else int(d)
            files.append((path, adds, dels))

        k = len(contributors)
        date = pd.to_datetime(date_s, utc=True)
        for path, adds, dels in files:
            add_split = split_int(adds, k)
            del_split = split_int(dels, k)
            for i, (c, e) in enumerate(contributors):
                rows.append({
                    "commit_hash": commit_hash,
                    "author_canonical": c,
                    "author_email_raw": e,
                    "date": date,
                    "file_path": path,
                    "additions": add_split[i],
                    "deletions": del_split[i],
                    "is_merge": is_merge,
                })

    df = pd.DataFrame(rows, columns=[
        "commit_hash", "author_canonical", "author_email_raw", "date",
        "file_path", "additions", "deletions", "is_merge",
    ])
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.astype({"additions": "int64", "deletions": "int64", "is_merge": "bool"})
    stats = {
        "total_commits": total_commits,
        "bot_commits_filtered": bot_commits,
        "merge_commits": merge_commits,
        "raw_author_identities": len(raw_ids),
        "canonical_authors": len(canon_ids),
    }
    return df, stats


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract cleaned commit history.")
    ap.add_argument("--repo", default=None, help="Target repo path (or REPO_PATH env).")
    args = ap.parse_args()
    repo = config.get_repo_path(args.repo)
    config.ensure_dirs()

    df, stats = extract(repo)
    out = config.DATA_DIR / "commits_clean.parquet"
    df.to_parquet(out, index=False)

    print(f"Wrote {out}  ({len(df):,} rows)")
    print(f"  commits parsed:            {stats['total_commits']:,}")
    print(f"  merge commits handled:     {stats['merge_commits']:,}")
    print(f"  bot commits filtered:      {stats['bot_commits_filtered']:,}")
    print(f"  raw author identities:     {stats['raw_author_identities']:,}")
    print(f"  canonical authors:         {stats['canonical_authors']:,}")


if __name__ == "__main__":
    main()
