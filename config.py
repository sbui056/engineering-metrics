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
    """GitHub token for the reviews track; None if unset (Track B degrades to partial)."""
    return os.environ.get("GITHUB_TOKEN")


def ensure_dirs() -> None:
    """Create the tool's output/cache directories if they don't exist yet."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
