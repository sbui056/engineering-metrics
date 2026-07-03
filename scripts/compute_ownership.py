"""Compute ownership and code-survival signals from git blame at HEAD.

Blames every tracked, non-excluded file with `git blame -w -M -C -C` (whitespace
ignored, moves/copies followed) and attributes each surviving line to a
canonical author. Produces two tables:

  data/ownership_file.parquet    (file grain)
    file_path, author_canonical, blame_lines, blame_share, is_blame_leader,
    is_major_owner, top_owner_proportion, minor_contributor_count, is_orphan_risk

  data/ownership_author.parquet  (author grain)
    author_canonical, ownership_concentration, code_survival_tenure_normalized,
    bus_factor_flag

Ownership: a major owner holds >= MAJOR_SHARE of a file's surviving lines and
clears an absolute floor (>= MAJOR_MIN_COMMITS commits to the file, or
>= MAJOR_MIN_LINES surviving lines). ownership_concentration is the
size-weighted blame share over files the author major-owns.

Survival: surviving lines older than RECENT_DAYS divided by lines added in
commits older than RECENT_DAYS (both attributed to the single commit author,
matching blame's attribution), clamped to [0,1], then normalized against an
exponential-decay baseline with HALF_LIFE_YEARS so young code isn't judged as
if it were old. Authors whose additions are all recent get NaN (no basis yet).

Usage: python scripts/compute_ownership.py --repo target-repo/FastVideo
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from extract_commits import is_bot, is_excluded, rename_target  # noqa: E402
from identity import build_from_repo  # noqa: E402

OWNERSHIP_FILE_COLUMNS = [
    "file_path", "author_canonical", "blame_lines", "blame_share",
    "is_blame_leader", "is_major_owner", "top_owner_proportion",
    "minor_contributor_count", "is_orphan_risk",
]
OWNERSHIP_AUTHOR_COLUMNS = [
    "author_canonical", "ownership_concentration",
    "code_survival_tenure_normalized", "bus_factor_flag",
]

MIN_FILE_LINES = 5        # files smaller than this are floored out
MAJOR_SHARE = 0.05        # ownership share to qualify as a major contributor
MAJOR_MIN_COMMITS = 2     # absolute floor: commits to the file ...
MAJOR_MIN_LINES = 25      # ... or surviving lines
RECENT_DAYS = 90          # additions younger than this are excluded from survival
HALF_LIFE_YEARS = 2.5     # decay baseline for tenure normalization
BLAME_WORKERS = 8


def list_tracked_files(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        capture_output=True, text=True, errors="replace", check=True,
    ).stdout
    return [p for p in out.split("\0") if p and not is_excluded(p)]


def is_binary_or_tiny(repo: Path, path: str) -> bool:
    """Cheap sniff: binary (null byte in first 8KB) or fewer than MIN_FILE_LINES lines.

    Single pass: sniff the head, count newlines from the same handle, and stop
    reading as soon as the line floor is cleared.
    """
    try:
        with open(repo / path, "rb") as fh:
            head = fh.read(8192)
            if b"\0" in head:
                return True
            lines = head.count(b"\n")
            last = head
            while lines < MIN_FILE_LINES:
                chunk = fh.read(65536)
                if not chunk:
                    if last and not last.endswith(b"\n"):
                        lines += 1  # final unterminated line still counts
                    break
                lines += chunk.count(b"\n")
                last = chunk
        return lines < MIN_FILE_LINES
    except OSError:
        return True


def parse_porcelain(text: str) -> list[tuple[str, str, int]]:
    """Parse `git blame --line-porcelain` output into (name, email, author_time) per line.

    Line-porcelain repeats full metadata for every line, so no sha cache is needed;
    a metadata block ends at the tab-prefixed content line.
    """
    lines_meta = []
    name = email = None
    atime = 0
    for line in text.splitlines():
        if line.startswith("\t"):
            lines_meta.append((name or "", email or "", atime))
            name = email = None
            atime = 0
        elif line.startswith("author "):
            name = line[7:]
        elif line.startswith("author-mail "):
            email = line[12:].strip("<>")
        elif line.startswith("author-time "):
            atime = int(line[12:])
    return lines_meta


def blame_file(repo: Path, path: str) -> list[tuple[str, str, int]]:
    res = subprocess.run(
        ["git", "-C", str(repo), "blame", "-w", "-M", "-C", "-C",
         "--line-porcelain", "HEAD", "--", path],
        capture_output=True, text=True, errors="replace",
    )
    if res.returncode != 0:
        return []
    return parse_porcelain(res.stdout)


def added_lines_by_single_author(repo: Path) -> pd.DataFrame:
    """Per-commit additions attributed to the single commit author (blame's model).

    Returns columns: name, email, date (UTC), additions — non-merge commits,
    excluded paths removed, binary '-' -> 0. commits_clean can't supply this
    because its additions are co-author-split.
    """
    RS, US = "\x1e", "\x1f"
    fmt = f"{RS}%an{US}%ae{US}%aI{US}"
    raw = subprocess.run(
        ["git", "-C", str(repo), "log", "--numstat", "-M", "--no-merges",
         f"--format={fmt}"],
        capture_output=True, text=True, errors="replace", check=True,
    ).stdout
    rows = []
    for chunk in raw.split(RS):
        if not chunk.strip():
            continue
        fields = chunk.split(US, 3)
        if len(fields) < 4:
            continue
        name, email, date_s, tail = fields
        if is_bot(name, email):
            continue
        adds = 0
        for line in tail.splitlines():
            cols = line.split("\t")
            if len(cols) != 3:
                continue
            a, _, path = cols
            if is_excluded(rename_target(path)):
                continue
            adds += 0 if a == "-" else int(a)
        if adds:
            rows.append({"name": name, "email": email, "date": date_s, "additions": adds})
    df = pd.DataFrame(rows, columns=["name", "email", "date", "additions"])
    df["date"] = pd.to_datetime(df["date"], utc=True, format="ISO8601")
    return df


def build_file_table(per_file_counts: dict, commits_to_file: dict) -> pd.DataFrame:
    """File-grain ownership rows from {file: Counter(author -> lines)}."""
    rows = []
    for path, counts in per_file_counts.items():
        total = sum(counts.values())
        if total == 0:
            continue
        shares = {a: n / total for a, n in counts.items()}
        top_share = max(shares.values())
        leader = max(shares, key=shares.get)
        majors = [
            a for a, s in shares.items()
            if s >= MAJOR_SHARE
            and (commits_to_file.get((path, a), 0) >= MAJOR_MIN_COMMITS
                 or counts[a] >= MAJOR_MIN_LINES)
        ]
        minor_count = sum(1 for s in shares.values() if s < MAJOR_SHARE)
        orphan = len(majors) == 1
        for a, n in counts.items():
            rows.append({
                "file_path": path,
                "author_canonical": a,
                "blame_lines": int(n),
                "blame_share": shares[a],
                "is_blame_leader": a == leader,
                "is_major_owner": a in majors,
                "top_owner_proportion": top_share,
                "minor_contributor_count": minor_count,
                "is_orphan_risk": orphan,
            })
    return pd.DataFrame(rows, columns=OWNERSHIP_FILE_COLUMNS)


def build_author_table(
    file_df: pd.DataFrame,
    surviving_old: Counter,
    added_df: pd.DataFrame,
    now: pd.Timestamp,
) -> pd.DataFrame:
    """Author-grain ownership concentration + tenure-normalized survival."""
    file_lines = file_df.groupby("file_path")["blame_lines"].sum()

    # Ownership concentration: size-weighted owned blame share.
    owned = file_df[file_df["is_major_owner"]].copy()
    owned["weighted"] = owned["blame_share"] * owned["file_path"].map(file_lines)
    concentration = owned.groupby("author_canonical")["weighted"].sum()

    # Bus-factor flag: major owner of at least one orphan-risk file.
    bus = (
        file_df[file_df["is_major_owner"] & file_df["is_orphan_risk"]]
        .groupby("author_canonical").size() > 0
    )

    # Survival denominator: additions older than RECENT_DAYS, single-author model.
    cutoff = now - pd.Timedelta(days=RECENT_DAYS)
    old = added_df[added_df["date"] < cutoff].copy()
    added_old = old.groupby("author_canonical")["additions"].sum()
    old["age_weighted"] = old["additions"] * (now - old["date"]).dt.days
    mean_age_days = old.groupby("author_canonical")["age_weighted"].sum() / added_old

    authors = sorted(set(file_df["author_canonical"]) | set(added_old.index))
    rows = []
    for a in authors:
        denom = added_old.get(a, 0)
        if denom > 0:
            rate = min(max(surviving_old.get(a, 0) / denom, 0.0), 1.0)
            expected = 0.5 ** ((mean_age_days[a] / 365.25) / HALF_LIFE_YEARS)
            survival = rate / expected
        else:
            survival = float("nan")  # all additions too recent to judge
        rows.append({
            "author_canonical": a,
            "ownership_concentration": float(concentration.get(a, 0.0)),
            "code_survival_tenure_normalized": survival,
            "bus_factor_flag": bool(bus.get(a, False)),
        })
    return pd.DataFrame(rows, columns=OWNERSHIP_AUTHOR_COLUMNS)


def main() -> None:
    ap = argparse.ArgumentParser(description="Compute ownership and survival from blame.")
    ap.add_argument("--repo", default=None, help="Target repo path (or REPO_PATH env).")
    ap.add_argument("--workers", type=int, default=BLAME_WORKERS)
    args = ap.parse_args()
    repo = config.get_repo_path(args.repo)
    config.ensure_dirs()

    resolver = build_from_repo(repo)
    files = [p for p in list_tracked_files(repo) if not is_binary_or_tiny(repo, p)]
    print(f"Blaming {len(files):,} files with -w -M -C -C ({args.workers} workers)...")

    now = pd.Timestamp.now(tz="UTC")
    cutoff_ts = (now - pd.Timedelta(days=RECENT_DAYS)).timestamp()
    per_file_counts: dict[str, Counter] = {}
    surviving_old: Counter = Counter()

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for path, meta in zip(files, ex.map(lambda p: blame_file(repo, p), files)):
            if not meta:
                continue
            counts: Counter = Counter()
            for name, email, atime in meta:
                if is_bot(name, email):
                    continue  # bot-authored lines don't count toward anyone
                canon = resolver.canonical(name, email)
                counts[canon] += 1
                if atime and atime < cutoff_ts:
                    surviving_old[canon] += 1
            if counts:
                per_file_counts[path] = counts
    print(f"  blame done in {time.time() - t0:.1f}s")

    commits = pd.read_parquet(config.DATA_DIR / "commits_clean.parquet")
    commits_to_file = (
        commits[~commits["is_merge"]]
        .groupby(["file_path", "author_canonical"])["commit_hash"].nunique().to_dict()
    )

    file_df = build_file_table(per_file_counts, commits_to_file)

    added = added_lines_by_single_author(repo)
    added["author_canonical"] = [
        resolver.canonical(n, e) for n, e in zip(added["name"], added["email"])
    ]
    author_df = build_author_table(file_df, surviving_old, added, now)

    f_out = config.DATA_DIR / "ownership_file.parquet"
    a_out = config.DATA_DIR / "ownership_author.parquet"
    file_df.to_parquet(f_out, index=False)
    author_df.to_parquet(a_out, index=False)

    n_orphan = int(file_df.drop_duplicates("file_path")["is_orphan_risk"].sum())
    surv = author_df["code_survival_tenure_normalized"].dropna()
    print(f"\nWrote {f_out}  ({len(file_df):,} rows, {file_df['file_path'].nunique():,} files)")
    print(f"Wrote {a_out}  ({len(author_df):,} authors)")
    print(f"  orphan-risk files: {n_orphan:,}   bus-factor-flagged authors: "
          f"{int(author_df['bus_factor_flag'].sum())}")
    print(f"  survival (normalized): min {surv.min():.3f}  median {surv.median():.3f}  "
          f"max {surv.max():.3f}  (NaN: {author_df['code_survival_tenure_normalized'].isna().sum()})")
    print("\nTop 10 by ownership concentration:")
    for _, r in author_df.nlargest(10, "ownership_concentration").iterrows():
        print(f"  {r.ownership_concentration:>12,.0f}  {r.author_canonical}")


if __name__ == "__main__":
    main()
