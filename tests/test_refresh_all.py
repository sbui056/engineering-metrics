"""Registry + orchestrator plumbing (no network, no pipeline runs)."""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from refresh_all import site_url, siblings_for  # noqa: E402


def _repos():
    return yaml.safe_load((ROOT / "repos.yml").read_text())


def test_repos_yml_schema():
    repos = _repos()
    assert len(repos) >= 2
    slugs = [r["slug"] for r in repos]
    assert len(set(slugs)) == len(slugs), "slugs must be unique"
    assert "" in slugs, "exactly one root deployment expected"
    for r in repos:
        for key in ("slug", "name", "clone", "data"):
            assert key in r, f"{r.get('name')} missing {key}"
        assert r["clone"].startswith("https://")


def test_site_url_and_siblings():
    repos = _repos()
    root = next(r for r in repos if r["slug"] == "")
    other = next(r for r in repos if r["slug"] != "")
    assert site_url("").rstrip("/") == site_url(other["slug"]).rsplit("/", 1)[0]
    sibs = siblings_for(repos, root)
    assert other["name"] in sibs and other["slug"] in sibs
    assert root["name"] not in sibs  # never links itself
