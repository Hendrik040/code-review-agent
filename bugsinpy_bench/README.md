# BugsInPy bench

A Python-focused code-review benchmark built on
[BugsInPy](https://github.com/soarsmu/BugsInPy)'s 501 curated bugs
across 17 well-known Python projects. The headline number is **the
recall of our agent SDK reviewer on real-world Python bugs**, derived
from a deterministic file:line oracle (the maintainer's actual fix
patch).

## Why this exists

Martian's [public CodeReview Bench](https://codereview.withmartian.com)
is the closest reference for "is this code-review tool good?" — but
their N=10 Python slice (Sentry only) is too small for a credible
comparison. BugsInPy gives us ~500 bugs with ground-truth fix patches.
The fix patches give us a free, deterministic oracle (exact buggy
file:line ranges); we don't need an LLM-judge.

## How a "PR" is constructed

BugsInPy stores `(buggy_commit_id, fixed_commit_id, bug_patch.txt)` per
bug — but no PR. We construct a reviewable `base..head` pair two ways
(see `scripts/prepare_dataset.py`):

- **`source = "blame"`** (the preferred path) — `git blame` the buggy
  lines (the lines REMOVED by the fix) at `fixed_commit^`. The
  resulting commit is the bug-introducing commit. We materialize the
  upstream repo at `introducing_commit` and the reviewer diffs
  `introducing_commit^ .. introducing_commit` — the actual historical
  PR-shaped change a human reviewer saw at the time the bug was
  introduced.
- **`source = "synthetic_revert"`** (fallback) — when blame doesn't
  converge cleanly (>3 distinct commits across the buggy lines), or
  when the introducing commit is too large to be reviewable (>8 files
  or >400 changed lines), or when blame times out on huge files. We
  apply `bug_patch.txt` in REVERSE on top of `fixed_commit` and use
  that synthetic head commit. The diff the reviewer sees is exactly the
  bug being introduced.

Both sources yield the same `(repo, base_ref, head_ref)` interface that
the agent SDK reviewer already consumes.

## Filters

A bug enters the run set only if:

- The maintainer's fix touches ≤3 files and ≤30 lines (small focused
  fix; rules out bugs whose fix is a sweeping refactor we can't
  meaningfully oracle on).
- The introducing commit (when `source = "blame"`) touches ≤8 files
  and ≤400 lines (so the agent reviews a realistic PR-sized diff,
  not a 1000-line refactor).
- Both `fixed_commit` and `introducing_commit` exist in the upstream
  repo's history at the time we run prepare (some projects rewrite
  history).

The complete filter accounting per bug — pass / synthetic / skip — lives in
`dataset/prepared.json` next to each entry.

## Methodology caveats (for chart context)

1. **BugsInPy bugs are test-detectable.** Every entry includes a
   failing test that demonstrates the bug. This biases the corpus
   toward bugs caught at runtime (logic errors, off-by-one, edge
   cases) and AWAY from bugs that need static-only review (missing
   security headers, dead code, style issues, undocumented APIs).
   Style-focused or security-focused tools may underperform here for
   reasons unrelated to their general quality.
2. **Synthetic-revert entries strip noise.** A real PR has both the
   bug-introducing change AND many unrelated changes. Synthetic-revert
   entries contain only the bug-introducing lines, which makes them
   *easier* for any reviewer than a real PR. For honesty, we always
   report blame and synthetic recall separately so the cohort split is
   visible.
3. **Effort fixed at xhigh.** Single configuration in v1; effort
   ablation is future work.
4. **Single SDK reported.** Agent SDK at xhigh effort. Our Client SDK
   reviewer (also xhigh) is comparable but not run here; its number
   would be a secondary chart.

## Running

```bash
# 1. Vendor BugsInPy (once per machine).
git clone https://github.com/soarsmu/BugsInPy bugsinpy_bench/dataset/bugsinpy
cd bugsinpy_bench/dataset/bugsinpy
git checkout 11c5f1eea954a42132cfd06bf257766a7963e0fd  # pinned SHA
cd ../../..

# 2. Build prepared.json (clones each upstream once, runs blame, applies filters).
uv run python bugsinpy_bench/scripts/prepare_dataset.py

# 3. Sweep all entries via Daytona (Agent SDK xhigh).
SANDBOX_BACKEND=daytona uv run python bugsinpy_bench/scripts/run_bench.py \
    --prepared bugsinpy_bench/dataset/prepared.json

# 4. Score the suite.
uv run python bugsinpy_bench/scripts/score.py bugsinpy_bench/results/suite_001.md

# 5. Plot.
uv run python bugsinpy_bench/scripts/plot.py bugsinpy_bench/results/scores_001.json
```

## Headline result (filled in after sweep)

> _Pending the full sweep — recall and cost numbers go here._

