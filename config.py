"""Shared configuration for the engineering-metrics pipeline.

This repo is the analysis *tool*; it scans an external target repository. Every
script that touches git resolves the target through `get_repo_path()` (CLI
`--repo`, then `REPO_PATH` env, then the default clone location) and runs git
commands against that path — never against the current working directory.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache"
DEFAULT_REPO_PATH = ROOT / "target-repo" / "FastVideo"

# Load a local .env if present (optional dependency).
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def get_repo_path(cli_value: str | None = None) -> Path:
    """Resolve the target repo path: CLI arg > REPO_PATH env > default clone."""
    value = cli_value or os.environ.get("REPO_PATH") or str(DEFAULT_REPO_PATH)
    return Path(value).expanduser().resolve()


def get_github_token() -> str | None:
    """GitHub token for the reviews track; None if unavailable (Track B degrades to partial).

    Order: GITHUB_TOKEN env (or .env), then the gh CLI's stored credential.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        import subprocess

        out = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def get_bot_extra() -> list[str]:
    """Extra bot/automation match patterns from the BOT_EXTRA env var (comma-separated).

    Lets a target repo's specific automation/co-author accounts be filtered without
    baking them into source (e.g. set in a local, untracked .env).
    """
    return [p.strip() for p in os.environ.get("BOT_EXTRA", "").split(",") if p.strip()]


def ensure_dirs() -> None:
    """Create the tool's output/cache directories if they don't exist yet."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
