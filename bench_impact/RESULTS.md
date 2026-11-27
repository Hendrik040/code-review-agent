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
