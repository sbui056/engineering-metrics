# Two org shapes, one engine

The same pipeline, pointed at two repositories, detects two entirely different organizational
realities. That contrast — not either leaderboard alone — is the strongest evidence that the
signals measure something real about how codebases depend on people.

|                                   | **FastVideo** (hao-ai-lab) | **ComfyUI** (Comfy-Org) |
|-----------------------------------|---------------------------:|------------------------:|
| Contributors scored               | 82                         | 311                     |
| Files at HEAD (after exclusions)  | 1,618                      | 904                     |
| Commits ↔ impact (Spearman ρ)     | 0.78                       | **0.44**                |
| Surviving-code Gini (all scored)  | 0.87                       | **0.99**                |
| People holding half the code      | four                       | **one**                 |
| Top-10 share of surviving code    | 83%                        | 97%                     |
| Rank tiers                        | 49                         | 206                     |


## The distributed lab

FastVideo reads like what it is: an academic lab's project. Ownership is concentrated but
shared — four people hold half the surviving code, and the two top contributors are
near-indistinguishable (both tier 1, scores 0.940 apart by less than the tier epsilon). Commit
count correlates with impact at ρ=0.78: activity and importance mostly travel together, and the
interesting stories are the exceptions (a 53-commit contributor at rank 2; the most prolific
committer genuinely being the most depended-on).

The departure question is real but bounded: the top contributor is sole major owner of 312
files (~7% of the co-change graph's centrality), yet 107 files are co-owned with the #8
contributor — knowledge has second homes.

## The solo cliff

ComfyUI's numbers are extreme in the way its community reputation suggests. One person holds
59% of all surviving code (Gini 0.99); commit count correlates with impact at only **ρ=0.44** —
on this repo, raw activity tells you less than half the story about who the codebase depends
on, which is the engine's core thesis rendered in a single number.

The departure question stops being a thought experiment and becomes the org chart: the
maintainer is sole major owner of 191 files carrying ~20% of the co-change graph's centrality,
and 102 of those files have never been touched by anyone else.

The leaderboard also surfaces the method's honest edge: a contributor whose **single commit**
— a test-infrastructure drop whose 768 lines survived three years as the foundation everyone
builds on — ranks in the top 6% of 311 people. While review data was still partial, imputation
placed them as high as #3; completing the fetch settled them at #19. That trajectory is the
honesty machinery working in the open: imputed signals are disclosed, and better data moves
ranks rather than being smoothed away. On a repo where ρ=0.44, outliers like this are not noise
in the method — they are the finding.

## What transfers, what doesn't

- **The signals transfer.** Nothing was retuned between repos: the same major-owner floor,
  survival window, coupling cap, and tier epsilon produced sensible readings of both shapes.
- **The copy transfers because it is computed.** Every claim on both pages — the correlation,
  the "N people hold half" headline, the curated comparison pair, even whether the tall column
  in the spectrum is "the zero-review block" — is derived from the target repo's data at build
  time.
- **The hygiene had to be earned.** ComfyUI's history carries 40% of its added lines in
  deleted, machine-built `web/` bundles, an AI agent credited via Co-authored-by trailers, and
  a docs bot — all of which would have distorted ownership had the engine not filtered them.
  Per-repo knobs (`BOT_EXTRA`, `EXCLUDE_EXTRA`) plus stronger defaults came out of this run.

## The same caveats, twice

Both pages carry the same limits, and they matter differently per shape: on FastVideo,
review leverage is a real differentiator among the core; on ComfyUI — where the maintainer
lands most work by direct push — 126 of 311 contributors have ever given a review, and the
185-person zero-review block is literally visible as the tallest column in the spectrum. Blame still only sees surviving lines; concentration still reads as both mastery
and fragility. Signals, not verdicts — on any repo.
