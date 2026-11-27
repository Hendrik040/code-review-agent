# Block-level Jev routing: design

Date: 2026-11-27. Branch: `bench/model-tiers-pilot-local`.

## Intent

Route each PR to the reviewer tier (Haiku 5.5, Sonnet 5.5, Opus 5.5) so that
spend goes down **and** more bugs are caught. Step 10 of
`bugsinpy_bench/EXPERIMENT_LOG.md` found that the current router's depth score
is inversely predictive: bugs only Opus found had a median P(deep) of 0.24,
bugs Haiku found 0.54 (AUC 0.27). The depth question measures reach (diff
size), not how subtle the logic is. The `high_stakes` question worked.

## Goals

- Score whether richer Jev input ranks the "Opus needed" bugs above the bugs a
  cheaper model finds, measured on stored results with no new reviews.
- Compare two ways of describing the diff to Jev (A and B below) and keep the
  better one.
- Produce a cost against bugs-found frontier for the new router, next to the
  current router, all-Opus 5.5 and the step-7 combinations.

## Non-goals

- No change to `shared/routing.py`, the reviewer or the context builder. If a
  variant wins, porting it is a separate change.
- No new review sweeps.

## Anti-goals

- Tuning a rule to fit 14 bugs and calling it a result. The rule is declared
  before scoring (below), and the threshold sweep is reported as a curve, not
  as one picked point.

## Constraints

- Jev guidance: one narrow judgment per question; state holds observed facts
  with their original field names, not verdicts; arithmetic and aggregation in
  code. Same-state questions are batched into one call; per-block questions use
  Jev `items` (up to 500 per call, judged independently).
- Never print or commit keys. `TYPESAFE_API_KEY` and `ANTHROPIC_API_KEY` come
  from the git-ignored `.env`.
- BugsInPy has no clean PRs, so a "safe for Haiku" decision can never be shown
  to be right on it. Spend savings from that question are not measurable here.

## Approaches

| | How | Trade-off |
|---|---|---|
| A | Haiku extracts per-block facts; Jev judges each block | Follows Jev's facts-not-verdicts rule; easy to audit |
| B | As A, plus Haiku's own 1-10 complexity score per block in the state | One more signal, but Jev may echo it, and Haiku misjudged the subtle bugs |
| **C (picked)** | Run A and B on the same stored bugs and compare | Settles it with data; the extra cost is only Jev calls |

To isolate the effect of the score, **one** Haiku call per bug produces both the
facts and the score. Arm A sends Jev the facts with the score field removed;
arm B sends the same facts plus the score. The only difference between the
arms is the score.

## Design

### 1. Block extraction (Haiku 5.5, effort high)

Input: the same review diff as `router_inputs.py` (`git diff --unified=3
--no-color base..head`), plus the title. Haiku is told to describe, never judge
correctness. Output, one record per changed code block:

```
{ "block_id", "file", "kind": data_structure|function|method|class|config|test|call_site|import|other,
  "symbol", "lines_added", "lines_removed",
  "before": "<what the code did>", "after": "<what it does now>",
  "callers_or_users_touched": [...],
  "constructs": [regex, slicing, comparison, loop, recursion, exception, early_return,
                 mutable_default, async, thread_or_process, io, numeric, string_format, ...],
  "complexity_1_10": n }        // used by arm B only
```

Cached per diff SHA-256 under `bugsinpy_bench/router_inputs/blocks/`, so reruns
cost nothing. Run on all 100 BugsInPy bugs and the 10 Martian PRs.

### 2. Jev questions (same for both arms)

Per block, as `items`:

1. `precision_logic` (noul): a one-character or boundary mistake changes behavior (regex, slicing, comparisons, range bounds, format strings)
2. `state_tracking` (noul): state carried across iterations or calls (counters, stacks, depth, caches, flags, mutable defaults)
3. `error_path` (noul): exception handling, return codes, early returns, cleanup on failure
4. `contract_change` (noul): signature, return value or type, or a value's meaning that callers rely on
5. `value_domain` (noul): assumes an input type or range a caller could violate
6. `async_flow` (noul): callbacks, futures, threads, processes, async control flow
7. `verify_effort` (score): block alone / trace one or two related functions / several interacting cases or invariants

Per PR (one call, state = title + per-file line counts + all block records):

8. `no_behavior_change` (noul): every changed line is docs, comments, tests, type hints, log text or config values
9. `beyond_title` (noul): behavior changes the title does not describe
10. `tests_exercise_change` (noul): changed tests exercise the changed behavior and its edge cases
11. `high_stakes` (noul): unchanged from the current router

Exact question wording is written once in the script and committed with the
results.

### 3. Decision rule (declared before scoring)

Computed in code from Jev's probabilities:

- `block_risk` = max over blocks of max(Q1-Q5) and P(top level of Q7).
- Light (Haiku): P(Q8) >= 0.85 and P(Q11) < 0.5.
- Deep (Opus): P(Q11) >= 0.5, or `block_risk` >= T.
- Otherwise standard (Sonnet).
- Reported at T = 0.5, plus a sweep of T from 0 to 1 as a curve.

### 4. Evaluation

On stored per-bug results (`full_scores.json` for BugsInPy; per-arm judged
verdicts for Martian):

- **Ranking:** AUC of `block_risk` for Opus-needed bugs (Opus found, Haiku
  missed; 14 on BugsInPy) against Haiku-found bugs. Current router: 0.27.
  Same for arm A, arm B and Haiku's raw `complexity_1_10` alone.
- **Frontier:** found and cost at T = 0.5 and over the T sweep, against the
  current router (42, $14.15), all-Opus 5.5 (42, $16.33) and the step-7
  combinations.
- **Held out:** Martian's 10 PRs are not looked at while writing questions or
  the rule; report goldens matched and cost there separately.
- **Noise:** Jev answers have varied between passes. Route BugsInPy twice per
  arm and report both passes.

### 5. Outputs

- `bugsinpy_bench/scripts/block_summaries.py` and `route_blocks.py`
- `bugsinpy_bench/routing/blocks_routes.json`, `blocks_scores.json`
- A new step in `EXPERIMENT_LOG.md` with the cost of each part (Haiku from
  usage; Jev from response usage if reported, otherwise call counts).

## Estimated cost

Haiku at high effort over 110 diffs: about $0.20-0.50 (the medium-effort
summaries cost $0.02 for 30). Jev: about 4 calls per diff per arm (2 arms,
2 passes); Jev's price is not measured yet.

## Left to the builder

- Haiku prompt wording and how the API's effort setting is passed for Haiku 5.5
  (check the claude-api skill).
- Whether one Jev call can carry both `items` and PR-level questions, or needs two.
- Splitting very large diffs into chunks for Haiku.
