"""Refresh every analyzed repo end-to-end: clone/update -> pipeline ->
validate (gate) -> deploy build -> history ledger.

Driven by repos.yml. Designed for the weekly CI workflow but runs locally the
same way. Per repo, the pipeline is forced (Makefile targets skip on existing
parquets; a refresh must not). validate.py failing aborts that repo BEFORE its
docs/ output is touched — stale-but-correct beats fresh-but-wrong. A partial
reviews fetch is tolerated (graceful degradation is the fetcher's contract);
a validation failure is not.

Usage: PAGES_URL=https://user.github.io/repo python scripts/refresh_all.py
       [--only slug] [--skip-clone]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PAGES_URL = os.environ.get("PAGES_URL", "https://sbui056.github.io/engineering-metrics")


def sh(cmd: list[str], env: dict | None = None) -> None:
    print(f"+ {' '.join(cmd)}", flush=True)
    merged = {**os.environ, **(env or {})}
    subprocess.run(cmd, check=True, env=merged, cwd=ROOT)


def site_url(slug: str) -> str:
    return f"{PAGES_URL}/{slug}" if slug else PAGES_URL


def siblings_for(repos: list[dict], me: dict) -> str:
    parts = [f"{r['name']}={site_url(r['slug'])}/" for r in repos if r is not me]
    return ",".join(parts)


def clone_or_update(repo: dict) -> Path:
    dest = ROOT / "target-repo" / repo["name"]
    if dest.exists():
        sh(["git", "-C", str(dest), "fetch", "--prune", "origin"])
        head = subprocess.run(
            ["git", "-C", str(dest), "symbolic-ref", "refs/remotes/origin/HEAD", "--short"],
            capture_output=True, text=True,
        ).stdout.strip() or "origin/HEAD"
        sh(["git", "-C", str(dest), "reset", "--hard", head])
    else:
        sh(["git", "clone", repo["clone"], str(dest)])
    return dest


def refresh(repo: dict, repos: list[dict], skip_clone: bool) -> None:
    print(f"\n=== {repo['name']} ({site_url(repo['slug'])}) ===", flush=True)
    dest = (ROOT / "target-repo" / repo["name"]) if skip_clone else clone_or_update(repo)
    env = {
        "REPO_PATH": str(dest),
        "DATA_DIR": str(ROOT / repo["data"]),
        "BOT_EXTRA": repo.get("bot_extra", ""),
        "EXCLUDE_EXTRA": repo.get("exclude_extra", ""),
    }
    py = sys.executable
    sh([py, "scripts/extract_commits.py", "--repo", str(dest)], env)
    sh([py, "scripts/fetch_reviews.py", "--repo", str(dest)], env)  # partial OK
    sh([py, "scripts/compute_coupling.py"], env)
    sh([py, "scripts/compute_ownership.py", "--repo", str(dest)], env)
    sh([py, "scripts/merge_and_score.py"], env)
    sh([py, "scripts/narrate.py"], env)
    sh([py, "scripts/validate.py"], env)  # the gate: raises -> repo aborted pre-deploy
    build_env = {**env, "SITE_URL": site_url(repo["slug"]),
                 "SIBLINGS": siblings_for(repos, repo)}
    sh([py, "scripts/build_site.py"], build_env)
    sh([py, "scripts/render_og.py"], build_env)
    out = ROOT / "docs" / repo["slug"] if repo["slug"] else ROOT / "docs"
    out.mkdir(parents=True, exist_ok=True)
    sh(["cp", "dist/index.html", str(out / "index.html")])
    sh(["cp", "dist/og.png", str(out / "og.png")])
    ledger_slug = repo["slug"] or repo["name"].lower()
    sh([py, "scripts/append_history.py", "--slug", ledger_slug,
        "--date", date.today().isoformat()], env)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="refresh a single slug ('' for the root repo)")
    ap.add_argument("--skip-clone", action="store_true",
                    help="use existing target-repo clones as-is")
    args = ap.parse_args()

    repos = yaml.safe_load((ROOT / "repos.yml").read_text())
    todo = [r for r in repos if args.only is None or r["slug"] == args.only]
    if not todo:
        sys.exit(f"no repo with slug {args.only!r} in repos.yml")
    for repo in todo:
        refresh(repo, repos, args.skip_clone)
    print("\nAll refreshed.", flush=True)


if __name__ == "__main__":
    main()
