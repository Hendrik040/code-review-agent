# Impact selection: before vs after, per model and with Jev triage

Date: 2026-11-27. Branch `bench/impact-selection-exp` = `bench/model-tiers-pilot-local`
(the model-tiers sweep code) with only `build_review_context` replaced by the new
context builder from PR #33 (Jev picks which callers/callees enter the context).

## Setup

- **Before** = the model-tiers sweeps (Haiku 5.5 medium, Sonnet 5.5 high, Opus 5.5 high
  on all 100 BugsInPy bugs and Martian's 10 PRs), copied into `baseline/`.
- **After** = the same, except the entries whose context changes under the new builder
  (`affected.json`: 16 of 100 bugs, 6 of 10 PRs) take this branch's reruns. Every other
  entry gets a byte-identical context, so its stored result is reused.
- **Same harness as the sweeps.** Empty `CLAUDE_CONFIG_DIR`; Claude Code 2.1.332 for
  Opus 5.5 and the SDK's bundled CLI for Sonnet/Haiku. `sentry-greptile#1` was rerun for
  Sonnet on 2.1.332 (`_tail`), as in the sweeps. Local sandbox, no learnings layer,
  judge `claude-sonnet-4-5-20250929`.
- **Triage** takes, per bug, the tier Jev routed it to in the sweeps (light = Haiku,
  standard = Sonnet, deep = Opus). The routes are unchanged.
- **Opus 5.5 ran the 16 affected bugs twice** to measure run-to-run noise.
- **Scores:** `score_impact.py` → `impact_scores.json`.

## BugsInPy

"Context errors" = reviews whose `build_review_context` call returned the Agent SDK's
"exceeds maximum allowed tokens" error instead of a context.

| Setup | Found, 100 bugs | Cost | Found, 16 affected | Context errors (affected) |
|---|---|---|---|---|
| Haiku 5.5 medium, before → after | 35 → 35 | $0.52 → $0.50 | 6 → 6 | 10 → 0 |
| Sonnet 5.5 high, before → after | 35 → 33 | $5.60 → $5.79 | 9 → 7 | 10 → 0 |
| Opus 5.5 high, before → after | 42 → 42 | $16.33 → $16.46 | 9 → 9 (repeat run: 7) | 10 → 0 |
| Jev triage, before → after | 42 → 41 | $14.15 → $14.27 | 9 → 8 | 10 → 0 |

## Martian (10 PRs, micro F1)

| Model | F1 before → after | Recall | Context errors (10 PRs) |
|---|---|---|---|
| Haiku 5.5 medium | 0.319 → 0.311 | 0.226 → 0.226 | 6 → 2 |
| Sonnet 5.5 high | 0.510 → 0.412 | 0.419 → 0.323 | 6 → 3 |
| Opus 5.5 high | 0.359 → 0.399 | 0.290 → 0.355 | 6 → 3 |

The errors left after the change are PRs whose diff alone is too large
(`sentry-greptile` #1, #3 and #5: 50 MB, 12 MB and 253 KB). By design the diff is never
cut.

## Reading

1. **Delivery is fixed.** Before, 10 of the 16 affected bugs got an error instead of a
   context on every model, including Opus on the newer CLI. After, none did. On Martian
   the errors fall from 6 to 2-3, and the rest are oversized diffs.
2. **Bugs found did not measurably change.** Every difference is within noise: the same
   Opus configuration found 9 and then 7 of the 16 affected bugs on two runs. Without a
   context, the agent fell back on its own tools (grep, file reads) and did about as well.
3. **Cost is flat**, within ±4% on the affected bugs.
4. **Martian moves in both directions** (Opus up, Sonnet down) on 6 changed PRs. That is
   too few to read.

Spend: $12.47 in reviews (including a discarded first attempt that ran without the
isolated CLI config), plus the judge calls.

## Follow-up: why bugs were lost, and a prompt fix

**Trace reading.** In the 6 bugs that were found before and missed after, the new
context held the evidence every time (rebuilt at the reviewed commits: for thefuck#7
Jev kept `replace_argument` and `for_app` out of 670 name matches). The reviewers saw
it and dismissed it (thefuck#7: Sonnet called the bug "speculative", Opus listed it
under "limits, neither worth flagging") or reported a different issue in the same code.
With a working context they make fewer tool calls (Opus 61 → 39 on the 10 bugs that
used to overflow) and submit fewer findings. The system prompt asks for that: "If the
returned context contains enough evidence, submit findings without further
investigation" and "Prefer no finding over a speculative finding". When the context
was an error, neither applied.

**Prompt fix.** `REVIEW_PROMPT_VARIANT=verify` (shared/prompts.py; off by default)
replaces the first sentence with "the context is a trimmed selection; do not drop a
suspected bug only because the context does not prove it; confirm or reject it with
the smallest code read", and adds to the second that a mismatch you can point to in the
code is not speculative and should be reported, at low severity if narrow.

**Test** (`run_prompt_fix.sh`, `score_prompt_fix.py` → `prompt_fix_scores.json`): the 10
bugs whose context overflowed, Sonnet 5.5 high and Opus 5.5 high, three setups on this
branch, two fresh runs each. Old = `IMPACT_SELECT=off` (the one-shot context, which
overflows on all 10), new = `jev`, verify = `jev` + the prompt variant. Earlier runs of
the same setups are pooled in. Every trace was checked for the intended prompt and for
context errors only in the old setup.

| Bugs found of 10 | Old context | New context | New + prompt fix |
|---|---|---|---|
| Sonnet 5.5 high | 4, 2 (earlier 5) → mean 3.7 | 2, 3 (earlier 2) → 2.3 | 3, 3 → 3.0 |
| Opus 5.5 high | 2, 3 (earlier 5) → 3.3 | 1, 3 (earlier 5, 3) → 3.0 | 4, 5 → 4.5 |

| Fresh runs, both reps | Old | New | Verify |
|---|---|---|---|
| Sonnet: cost / tool calls / findings (judged real) | $1.33 / 118 / 18 (16) | $1.28 / 73 / 14 (14) | $1.31 / 79 / 20 (20) |
| Opus: cost / tool calls / findings (judged real) | $3.42 / 126 / 28 (28) | $3.36 / 85 / 24 (23) | $3.55 / 84 / 30 (30) |

**Reading.**
1. **The noise is as large as the effects.** The same setup ranges 2-5 of 10 for Opus
   (old) and 1-5 (new). With 2-4 runs per cell, no difference here is significant.
2. **Verify is the best Opus setup in this sample (mean 4.5)** and lifts Sonnet back
   toward the old context. It did not make the agent investigate more (tool calls are
   unchanged from new); it made it report more: 30 vs 24 findings for Opus, 20 vs 14 for
   Sonnet, with the judge rating every verify finding a real bug.
3. **thefuck#7, the clearest dismissal, is recovered:** 4 of 4 verify runs found it
   across both models, against 1 of 7 with the new context.
4. **Sonnet still loses thefuck#20 and #26** with or without the prompt change (old
   context 2/3 and 1/3, new and verify 0 of 5). Those look like a real cost of the
   trimmed context for Sonnet, not fixed by the prompt.
5. **Overfitting caveat:** the prompt change was written after reading these traces and
   is scored on the same 10 bugs. It needs a run on the other 90 bugs (and Martian)
   before it is adopted.

Spend for the follow-up: $14.25 in reviews (rep 1 $7.38, rep 2 $6.87), plus judge calls.
Total for this experiment: $26.72 in reviews of the $30 approved.

## Full benchmark with the prompt fix

`run_verify_full.sh` (+ `resume_verify_full.sh`, `score_verify_full.py` →
`verify_full_scores.json`): Jev impact selection + `REVIEW_PROMPT_VARIANT=verify` on all
of BugsInPy and Martian, Sonnet 5.5 high and Opus 5.5 high, one run. The 90 bugs not in
the 10-bug test ran here; the other 10 use the promptfix verify runs (r1, with r2 as a
second estimate). The first pass stopped when the API account ran out of credit (every
call after that crashed at $0 and the judge failed too); the crashed entries were rerun
with a key from a funded organization and every sweep was re-judged. Sonnet's resume hit
its $4 cap, so 8 bugs have no verify review; all setups are compared on the same 92.
All runs used Claude Code 2.1.332 (earlier Sonnet sweeps used the SDK's bundled CLI).

| | Old context | New context | New + prompt fix |
|---|---|---|---|
| Opus, bugs found of 100 | 42 | 42 | 42 (second estimate 43) |
| Sonnet, bugs found of 92 | 32 | 30 | 30 (30) |
| Opus, Martian F1 (recall / precision) | 0.359 (0.29 / 0.47) | 0.399 (0.36 / 0.46) | 0.420 (0.39 / 0.46) |
| Sonnet, Martian F1 | 0.510 (0.42 / 0.65) | 0.412 (0.32 / 0.57) | 0.385 (0.32 / 0.48) |
| Context errors, BugsInPy / Martian | 10 / 6 | 0 / 3 | 0 / 2 |

**Reading.**
1. **The prompt fix does no harm.** On the 84 bugs (78 for Sonnet) whose context did
   not change, Opus goes 33 → 34 and Sonnet 24 → 24, with a few bugs swapped each way.
   Findings rise about 10% (Opus 103 → 112, Sonnet 65 → 73) and the judge rates the
   same share as real (94% / 95%).
2. **It does not produce an overall gain.** Over the whole benchmark the three setups
   are within one bug of each other for Opus and two for Sonnet. The 10-bug win
   (Opus 4.5 vs 3.0) does not carry over to a visible difference in 100.
3. **Martian splits by model again:** Opus improves step by step (F1 0.36 → 0.40 → 0.42),
   Sonnet drops (0.51 → 0.41 → 0.39, mostly precision). With 31 golden comments, one
   comment is 3 points of recall, so neither direction is established.
4. **Sonnet cost rose** about 20% with the prompt fix on BugsInPy ($5.12 → $6.34 on 92
   bugs); part of that may be the newer CLI. Opus cost is flat.

**Where this leaves the context builder:** it is a reliability fix (no more context
errors, flat cost) with no measurable effect on bugs found, with or without the prompt
change. On this benchmark the agent compensates for a missing context with its own
tools, so a better context cannot show up as more bugs found. Testing an accuracy
claim needs cases where exploring is not enough.

Spend for this run: $23.86 in reviews (approved $25), plus judge calls.
