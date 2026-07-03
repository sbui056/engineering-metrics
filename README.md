# Engineering Impact Dashboard

Ranks the contributors of a real open-source repository by **impact rather than activity** — the degree to which an engineer's work is depended on, trusted, and hard to replace — explicitly rejecting raw commit count and lines-of-code as the headline signal. The approach derives four independent, percentile-normalized signals from git history and GitHub reviews — **ownership concentration** (surviving-blame share of the files you're the major owner of), **code survival** (durability of your contributions, tenure-normalized), **co-change coupling criticality** (PageRank centrality of the files you own in the commit co-change graph), and **review leverage** (reviews given, weighted by distinct authors reviewed for) — and combines them with equal weights into a single, one-sentence-explainable score. A Streamlit dashboard presents an ordered leaderboard grouped into uncertainty tiers (so small-sample ranks aren't overclaimed), per-contributor drill-downs showing the evidence behind each score, and a persistent "signals, not verdicts" caveat layer that is honest about bus-factor risk, what the metrics can't see, and how they can be gamed.

## How it works

The full signal definitions, data contract, and scoring are documented in
[docs/methodology.md](docs/methodology.md). The results on the target repository — the
leaderboard, a measured contrast against the rejected commit-count and lines-of-code baselines,
and the defense of the main design decisions — are in [docs/writeup.md](docs/writeup.md).

## Running

This repo is the analysis tool; it scans an external target repository. Point it at a local clone
and run the pipeline:

```
pip install -r requirements.txt
REPO_PATH=/path/to/target-repo make all
streamlit run dashboard.py
```

Outputs are written to `data/`; the dashboard reads `data/scored.parquet`.

The reviews step calls the GitHub API. It authenticates with `GITHUB_TOKEN` (environment or a
local `.env`), falling back to the `gh` CLI's stored credential; with no token it degrades to a
partial fetch and the pipeline marks the review signal as imputed rather than failing. API
responses are cached under `.cache/` so reruns only refetch PRs that changed.