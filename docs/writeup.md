# Who actually holds this codebase up?

**Ranking FastVideo's contributors by impact instead of activity — results, the baselines we
rejected, and what the numbers can and cannot say.**

This is the results writeup. The mechanics — signal definitions, data contract, scoring math —
live in [methodology.md](methodology.md); this document covers what came out the other end and why
the design choices were made the way they were.

## The question and the data

Impact here means the degree to which an engineer's work is **depended on, trusted, and hard to
replace** — not how much of it there is. The target is
[hao-ai-lab/FastVideo](https://github.com/hao-ai-lab/FastVideo): 824 non-merge commits by 82
contributors between March 2024 and June 2026, 1,618 files at HEAD, and 1,107 pull requests'
worth of review activity.

Four signals feed the headline score, each answering a different form of "would this be hard to
replace": **ownership concentration** (surviving-blame share of files the engineer major-owns),
**code survival** (how much of what they wrote is still there, tenure-normalized), **coupling
criticality** (PageRank centrality of the files they own in the co-change graph), and **review
leverage** (reviews given, weighted by distinct authors reviewed for). Each is
percentile-normalized and they are combined with equal 0.25 weights.

## Results

The leaderboard groups 82 contributors into 49 tiers. Tier 1 is a tie: **William Lin** (0.940)
and **alexzms** (0.9395) sit within the indistinguishability epsilon, which is itself the point of
tiers — a 0.0005 gap at N=82 is noise, and the dashboard refuses to pretend otherwise.

William Lin is the clearest possible case of the definition: blame leader on 469 of 1,618 files,
the top percentile on all four signals, and 491 reviews given across 51 distinct authors — nearly
every other contributor has passed through his review queue. alexzms matches him on a fraction of
the volume (53 commits to his 316), which is the score working as intended: what alexzms owns is
central, what he wrote survived, and the score doesn't care that there's less of it.

The rest of the top tiers — Jinzhe Pan, Kevin Lin, Junda Su, Wei Zhou, XOR-op — each clear a high
bar on at least three of the four signals. Every one of the top ten carries the bus-factor flag,
which is discussed below.

## The rejected baselines, measured

Commit count and lines-of-code were rejected up front as headline signals. Having built the
alternative, we can now say precisely what rejecting them bought us. Spearman correlation between
the impact ranking and the baselines is **0.785 against commit count** and **0.601 against LOC**:
correlated, as they should be — someone who never commits can't own anything — but the
disagreements land exactly where a naive ranking does damage.

**LOC crowns a JSON file.** Yongqi Chen is #1 by lines of code, at 3.47 million. Of those, 3.44
million are three generated mask-strategy asset files (`assets/mask_strategy_*.json`), rewritten
wholesale across a handful of commits. His actual Python footprint is ~21k lines. Impact rank:
#17 — still a solid contributor, but a LOC leaderboard would have put a data file at the top of
the org chart.

**Commit count can't see rewrites.** Zhang Peiyuan is #2 by both commits (132) and LOC. His
ownership, coupling, and review percentiles are all in the top three — but his survival percentile
is 0.28, because most of what he wrote early has since been rewritten, and he lands at impact #8.
This one cuts both ways, and honesty requires saying so: survival-at-HEAD structurally undercounts
foundational work that others later refactored, so part of that 0.28 is real churn and part is the
known bias of blame-based attribution. The score is defensible here, not oracular — which is why
he's presented as tier 7 with the evidence attached, not as "worse than #7."

**Both baselines are blind to reviews.** Wenxuan Tan ranks 20th by LOC (8.4k lines) and ties for
5th by commits, but reaches impact #9 largely on review leverage: 127 reviews across 18 distinct
authors. That's trust the repository visibly runs on, and it does not appear in a diff stat.

**Quiet ownership beats loud activity.** Shao Duan has 16 commits — 15th by commit count — but is
blame leader on 154 files with the second-highest survival on the board, and lands at impact #10.
He's also a true-zero reviewer, and the score carries that honestly (see imputation below) rather
than hiding it.

At the long tail the contrast is starker: commit count ties every one-commit contributor at rank
45, while the impact score spreads them from #24 to #79 depending on whether that one commit
survived and how load-bearing the code it touched is. A baseline that cannot distinguish a
surviving core-pipeline patch from a reverted typo fix is not measuring anything.

## Design decisions worth defending

**Equal weights, on purpose.** The 0.25/0.25/0.25/0.25 weighting is a transparent choice, not a
calibrated one. With no ground truth at N=82 there is nothing to fit against, and unit-weighted
composites are notoriously hard to beat in exactly this setting (Dawes 1979, "The robust beauty of
improper linear models"). Publishing tuned-looking weights would imply a precision that doesn't
exist.

**Percentiles, not z-scores.** Repository activity is heavy-tailed; z-scores would let William
Lin's outlier volume compress everyone else's signal to near zero. Percentile-of-rank is robust to
outliers by construction, which is also why no winsorizing is needed.

**Missing data imputes to the middle, never the floor.** The review fetch for this run is complete
(all 1,107 PRs), so the 59 contributors absent from the review table are *true zeros*, and they
rank at the zero-block's tie-averaged midrank (0.366 on this data) — below all 23 observed
reviewers, but not scored as if giving no reviews were the worst possible fact about them. Under a
partial fetch, absence would instead be unknowable and median-imputed with a visible badge. Either
way the invariant holds: a data-availability gap cannot masquerade as "worst engineer."

**Tiers, not a bootstrap.** Ranks separated by less than half the median adjacent-score gap share
a tier. This is cheap, requires no ill-defined resampling of blame at HEAD, and directly prevents
the most common misread of a leaderboard: treating #4 vs #5 as a finding.

**Known redundancy, kept anyway.** Ownership concentration and owned-coupling-criticality both
scale with blame share, so ownership effectively carries more than its nominal 25% and the four
signals are really about three independent dimensions. That is the deliberate cost of choosing
*owned*-criticality (how critical is what you own) over *touched*-criticality (how critical is
what you've brushed against), which would have been noisier and closer to an activity metric.

**Bus factor is scored positively and flagged loudly.** High ownership concentration reads two
ways: hard to replace, and dangerous to lose. On FastVideo the risk side is not hypothetical —
1,030 of 1,618 files have a single major owner, and 38 of 82 contributors (all of the top ten)
carry the orphan-risk flag. The same number that tops the leaderboard is a succession-planning
problem, and the dashboard shows both readings side by side rather than netting them out.

## What this cannot see

Every signal is a proxy, and the failure modes are documented rather than waved away:

- Blame attributes only lines surviving at HEAD. Even with whitespace-ignoring, move-following
  copy detection (`-w -M -C -C`), refactored-away foundations are undercounted — the Zhang Peiyuan
  case above is partly this.
- Coupling has a cold-start blind spot: a load-bearing file that rarely changes scores low, and
  high centrality sometimes measures entanglement, a design smell, rather than importance.
- Review leverage measures reach, not depth; a one-line "LGTM" counts the same as a substantive
  review.
- Nothing here sees mentoring, design work, incident response, unblocking others, or anything that
  happens off-repo.
- All of it is gameable (Goodhart's law). Publish this formula as a target and it will erode:
  territorial code hoarding pumps ownership, split PRs pump review counts, rubber stamps pump
  reach. It is an instrument for understanding a codebase, not a compensation formula.

The dashboard accordingly reports **signals, not verdicts**, over a fixed data window — an ordered
leaderboard with the uncertainty made visible, the evidence behind every score one click away, and
the caveats rendered on the page rather than buried in a doc. Commit count appears on it exactly
once — plotted against the impact score as a labeled contrast chart — and lines-of-code not at
all, except in the caveats explaining why.
