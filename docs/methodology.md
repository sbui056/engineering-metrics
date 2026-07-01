# Methodology

## Impact, not activity

Impact is defined as the degree to which an engineer's work is depended on, trusted, and hard to
replace. Raw commit count and lines-of-code are not used as impact signals; they appear only as a
contrast baseline.

## The four signals

The headline `impact_score` is built from four signals, each produced by a dedicated step:

1. **Ownership concentration** — surviving-blame share of the files an engineer is the major owner
   of. Produced by `scripts/compute_ownership.py`.
2. **Code survival** — durability of an engineer's contributions, tenure-normalized. Produced by
   `scripts/compute_ownership.py`.
3. **Co-change coupling criticality** — how central the files an engineer owns are in the graph of
   files that change together. File centrality is produced by `scripts/compute_coupling.py`; the
   per-author roll-up is computed in the merge step.
4. **Review leverage** — code reviews given, weighted by the number of distinct authors reviewed
   for. Produced by `scripts/fetch_reviews.py`.

Ownership concentration is dual-use: high concentration means both "hard to replace" and
"bus-factor risk." It contributes positively to the score and is always shown alongside a
bus-factor / orphan-risk flag.

Breadth (files and directories touched), recency, and consistency are computed and displayed but
are not part of the headline score, keeping the score explainable in one sentence.

## How the tool runs

This repository is the analysis tool, not the repository being analyzed. Every step that reads git
takes the target repository path via `--repo` (or the `REPO_PATH` environment variable, resolved by
`config.py`) and runs git against that external clone. Outputs are written to `data/`. The pipeline
is driven by the `Makefile` in dependency order.

## Data contract

Each step reads and writes a fixed schema.

`commits_clean.parquet` — one row per (commit, file):
`commit_hash, author_canonical, author_email_raw, date (UTC), file_path, additions, deletions, is_merge`.

`ownership_file.parquet` (file grain):
`file_path, author_canonical, blame_lines, blame_share, is_blame_leader, is_major_owner,
top_owner_proportion, minor_contributor_count, is_orphan_risk`.

`ownership_author.parquet` (author grain):
`author_canonical, ownership_concentration, code_survival_tenure_normalized, bus_factor_flag`.

`reviews.parquet` (keyed on `author_canonical`):
`author_canonical, reviewer_login, review_count, distinct_authors_reviewed, approval_rate, status`.

`coupling.parquet` (file grain):
`file_path, centrality_score, weighted_degree`.

`scored.parquet` (the table the dashboard reads):
`author_canonical, impact_score, ownership_concentration, code_survival_tenure_normalized,
coupling_criticality, review_leverage, has_review_data, review_data_imputed, bus_factor_flag,
tier, breadth_files, breadth_dirs, recency_days, consistency, one_line_rationale`.

## Signal computation

**Identity resolution** (`scripts/identity.py`). All author identities — git authors, committers,
co-authors, and GitHub reviewers — are canonicalized through one shared resolver so every table
joins in the same space. Resolution honors a `.mailmap` if present, then unions identities that
share a GitHub noreply login, a normalized email, a git name equal to a known login, or an exact
full name; a conservative fuzzy match on multi-token names is the last resort. The resolver is
conservative: it prefers to leave two identities separate rather than risk merging distinct people,
and it prints a merge report so every collapse can be inspected.

**Commit extraction.** Full history is parsed with `git log --numstat -M`. Bot and CI accounts are
filtered. Generated and vendored paths (lockfiles, `dist/`, `build/`, `vendor/`, `node_modules/`)
are excluded. Merge commits are detected by parent count, measured against the first parent only,
flagged, and excluded from churn, ownership, and coupling. `Co-authored-by` trailers are credited,
with a commit's additions and deletions split equally among the committer and each co-author.
Binary files (numstat `-`) map to 0.

**Ownership and survival.** `git blame -w -M -C -C` at HEAD attributes each surviving line, ignoring
whitespace and following moves and copies. A major owner of a file holds at least 5% ownership above
an absolute floor. `ownership_concentration` is an engineer's blame-share over the files they major-
own, weighted by file size, with files under ~5 lines floored out. `code_survival_tenure_normalized`
is surviving blame lines divided by the lines that author originally added (attributed to the single
commit author, matching blame), excluding additions from the last ~90 days, normalized by tenure,
and clamped to [0, 1].

**Co-change coupling.** The graph is built from non-merge commits: each file pair in a commit
touching *n* files contributes an inverse-size weight of `1/(n-1)`, and commits touching more than
a fixed number of files are dropped. Edges are pruned to pairs whose co-change lift exceeds 1 with a
minimum support of 2. File criticality is PageRank on the resulting weighted graph.

## Scoring

Each signal is percentile-normalized (robust to the heavy-tailed distribution of repository
activity), and the four percentiles are combined with equal weight:

```
impact_score = 0.25 * pct(ownership_concentration)
             + 0.25 * pct(code_survival_tenure_normalized)
             + 0.25 * pct(coupling_criticality)
             + 0.25 * pct(review_leverage)
```

`coupling_criticality` is owned-criticality, computed in the merge step by joining file centrality to
per-file blame share on `file_path`, multiplying, and summing per author. `review_leverage` is
`distinct_authors_reviewed * log1p(review_count)`. An engineer with no review data has that signal
imputed to the median (50th percentile) and flagged, so a data gap does not read as a worst-case
score. Contributors are grouped into tiers so that ranks separated by less than a meaningful margin
are not presented as distinct.

## Limitations

- Blame attributes only lines that survive to HEAD, so it favors code that has not been rewritten and
  undercounts foundational work that was later refactored away.
- Coupling has a cold-start blind spot: a load-bearing but rarely-changed file scores low. High
  centrality can also reflect entanglement rather than importance.
- Ownership concentration measures both value and bus-factor risk; it is flagged, not hidden.
- Review leverage measures reach (distinct authors reviewed), not the depth of each review.
- Ownership and owned-criticality both depend on blame share and are therefore correlated.
- The signals do not capture mentoring, design, incident response, unblocking others, or off-repo
  work. The dashboard reports signals, not performance verdicts, over a fixed data window.
