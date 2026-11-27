# Pilot: Haiku 5.5 and Sonnet 5.5 on 30 BugsInPy bugs

Run on 2026-11-26 on a local machine. Reviews, judging and summaries all ran the same day.
Branch: `bench/model-tiers-pilot-local`. A separate run of the same plan pushed its own results to `bench/model-tiers-pilot` while these sweeps ran (its traces reuse run numbers 385-446); the two are independent samples.

## Setup

- **Harness commit:** branched from the tip of `bench/bugsinpy` (`8ec32c2`), not from
  `a21503a`. The May sweeps record `harness_git_rev: a21503a`, and that commit is reachable,
  but it contains no `bugsinpy_bench/` files at all: the benchmark scripts were run
  uncommitted and committed afterwards in `33b100c`. Between `a21503a` and the tip, the
  differences in the requested folders are:
  - `agent_sdk/reviewer.py`: a per-run `effort` parameter (10 lines), which the bench needs.
  - `shared/fixtures.py`: upstream-commit setup for BugsInPy (`materialize_upstream`, +141 lines).
  - `bugsinpy_bench/scripts/`: all nine scripts are new.
  Between `33b100c` (the first commit holding the bench) and the tip there are no
  differences in `agent_sdk/`, `shared/` or `bugsinpy_bench/scripts/`.
- **Only harness change:** `agent_sdk/reviewer.py` reads `MODEL` from `REVIEW_MODEL`,
  defaulting to `claude-opus-4-7`. `meta.json` records the model per sweep. The bench calls
  the reviewer with `use_oauth=False`; every trace records `use_oauth: False`.
- **Added script:** `bugsinpy_bench/scripts/router_inputs.py` writes the diffs and summaries
  for step 8. It is not used by the review runs.
- **Environment:** Python 3.11.13 (uv first picked 3.15, which has no prebuilt Pillow).
  `claude-agent-sdk` 0.1.72 and `anthropic` 0.97.0, the same versions as the May
  environment. The Agent SDK ran its bundled Claude CLI (2.1.126). `SANDBOX_BACKEND`
  unset, so each bug is checked out in a local temporary folder. May ran on Daytona.
- **API key:** `ANTHROPIC_API_KEY` was not set in the shell; it was present in the repo's
  `.env`, which the harness loads. A models-list request succeeded and listed
  `claude-haiku-5-5`, `claude-sonnet-5-5` and `claude-sonnet-4-5-20250929`.
- **CLI config isolated:** the Agent SDK passes no `--setting-sources`, so the CLI loaded
  the machine owner's personal Claude Code setup (plugins, skills, MCP servers). The first
  request of a review was then 124,574 tokens (Sonnet) against 47,635 in the May Opus 4.7
  run of the same bug (PySnooper#3, run_236). All sweeps therefore ran with
  `CLAUDE_CONFIG_DIR` set to an empty folder. This is an environment setting, not a code
  change. With it the first request was 35,002 tokens (Haiku) and 34,508 (Sonnet). The
  remaining gap to May's 47,635 was not investigated; it may be tokenizer differences
  between models or May's own CLI setup.
- **Cost basis:** costs are the harness-reported `total_cost_usd`. For the smoke runs they
  match a recomputation from token usage at list prices to the microdollar (Haiku 5.5:
  $0.10 / $0.50 per MTok, cache write $0.125, cache read $0.01; Sonnet 5.5: $2 / $10,
  cache write $2.50, cache read $0.10). The stored Opus 4.7 costs are May's
  harness-reported figures.
- **Settings as in May:** same prompts, tools, tool limits (`MAX_TURNS` 100), line
  tolerance 10, bug timeout 1800 s, judge model `claude-sonnet-4-5-20250929`, and
  `judge.py` / `score.py` unchanged. Judge spend was measured by a wrapper around the
  unchanged `judge.py`.

### Smoke test (PySnooper#3, one entry, `--max-cost 1`)

| Run | Config | Found | Cost | Turns | First request (tokens) | Result |
|---|---|---|---:|---:|---:|---|
| Haiku 5.5 medium | personal CLI config | yes | $0.0229 | 4 | 124,997 | pass |
| Sonnet 5.5 high | personal CLI config | yes | $0.3995 | 4 | 124,578 | pass |
| Haiku 5.5 medium | isolated config | yes | $0.0091 | 4 | 35,002 | pass |
| Sonnet 5.5 high | isolated config | yes | $0.1484 | 4 | 34,508 | pass |

Every run ended normally, submitted through `submit_findings`, recorded a cost, showed the
right model in its trace and had no API errors. The smoke folders are not committed.

## Spend against the $30 cap

| Item | Cost |
|---|---:|
| Smoke tests (4 runs) | $0.5799 |
| Sonnet 5.5 high sweep (30 bugs) | $1.5077 |
| Haiku 5.5 medium sweep (30 bugs) | $0.1404 |
| Judging, Sonnet sweep (24 calls) | $0.1333 |
| Judging, Haiku sweep (22 calls) | $0.1299 |
| Haiku summaries (55 calls + 1 test call) | $0.0201 |
| **Total** | **$2.5113** |

Neither sweep reached its cap ($20 and $4); both reviewed all 30 bugs.

## Target recall by group

Bugs whose finding the judge matched to the maintainer's fix, out of bugs reviewed.
Opus 4.7 columns are the stored May sweeps.

| Group (n=10) | Haiku 5.5 medium | Sonnet 5.5 high | Opus 4.7 low | Opus 4.7 high | Opus 4.7 max |
|---|---:|---:|---:|---:|---:|
| Found at low | 9/10 | 9/10 | 10/10 | 10/10 | 10/10 |
| Missed at low, found at high/max | 6/10 | 5/10 | 0/10 | 7/10 | 9/10 |
| Never found | 1/10 | 3/10 | 0/10 | 0/10 | 0/10 |
| **All 30** | **16/30** | **17/30** | **10/30** | **17/30** | **19/30** |
Whole-sweep scores for the 30 bugs:

| Sweep | Target recall | Broad recall | Strict precision | Plausible precision | Findings |
|---|---:|---:|---:|---:|---:|
| Haiku 5.5 medium | 0.533 | 0.700 | 0.586 | 0.931 | 29 |
| Sonnet 5.5 high | 0.567 | 0.800 | 0.600 | 1.000 | 30 |

## Per bug

Cost in USD per bug. Opus 4.7 figures are from the stored May sweeps (Daytona, May CLI setup).

| Bug | Group | Haiku found | Haiku $ | Haiku turns | Sonnet found | Sonnet $ | Sonnet turns | Opus low | Opus low $ | Opus high | Opus high $ | Opus max | Opus max $ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cookiecutter#4 | Found at low | no | 0.0041 | 5 | yes | 0.0414 | 4 | yes | 0.2511 | yes | 0.5218 | yes | 0.5885 |
| keras#13 | Found at low | yes | 0.0025 | 3 | yes | 0.0378 | 4 | yes | 0.1526 | yes | 0.2106 | yes | 0.3040 |
| luigi#2 | Found at low | yes | 0.0030 | 5 | yes | 0.0343 | 4 | yes | 0.1454 | yes | 0.2534 | yes | 0.3602 |
| matplotlib#25 | Found at low | yes | 0.0040 | 3 | yes | 0.0672 | 7 | yes | 0.2301 | yes | 0.3831 | yes | 0.7297 |
| pandas#104 | Found at low | yes | 0.0042 | 4 | yes | 0.0505 | 4 | yes | 0.2868 | yes | 0.4003 | yes | 0.6095 |
| PySnooper#3 | Found at low | yes | 0.0104 | 6 | yes | 0.0328 | 4 | yes | 0.2915 | yes | 0.6728 | yes | 1.2236 |
| scrapy#4 | Found at low | yes | 0.0054 | 5 | yes | 0.0625 | 4 | yes | 0.2117 | yes | 0.4205 | yes | 0.5587 |
| thefuck#9 | Found at low | yes | 0.0042 | 3 | yes | 0.0400 | 3 | yes | 0.1804 | yes | 0.5329 | yes | 0.6643 |
| tornado#13 | Found at low | yes | 0.0043 | 4 | no | 0.0624 | 7 | yes | 0.2316 | yes | 0.3883 | yes | 0.6826 |
| tqdm#4 | Found at low | yes | 0.0034 | 5 | yes | 0.0399 | 4 | yes | 0.1893 | yes | 0.2179 | yes | 0.4007 |
| keras#3 | Missed at low, found at high/max | no | 0.0076 | 4 | no | 0.0645 | 3 | no | 0.2481 | no | 0.9669 | yes | 3.0617 |
| keras#32 | Missed at low, found at high/max | yes | 0.0055 | 5 | no | 0.0673 | 5 | no | 0.3800 | no | 0.4670 | yes | 1.4462 |
| luigi#5 | Missed at low, found at high/max | yes | 0.0083 | 12 | yes | 0.0822 | 7 | no | 0.3399 | yes | 0.6394 | no | 1.4582 |
| matplotlib#23 | Missed at low, found at high/max | yes | 0.0051 | 4 | no | 0.0589 | 4 | no | 0.1930 | yes | 1.9365 | yes | 2.5807 |
| pandas#26 | Missed at low, found at high/max | yes | 0.0049 | 7 | yes | 0.0503 | 6 | no | 0.2591 | yes | 0.5555 | yes | 1.3312 |
| pandas#30 | Missed at low, found at high/max | yes | 0.0049 | 8 | yes | 0.0350 | 4 | no | 0.1321 | no | 0.3489 | yes | 2.2350 |
| sanic#1 | Missed at low, found at high/max | no | 0.0075 | 6 | no | 0.1179 | 6 | no | 0.4660 | yes | 1.1906 | yes | 0.9546 |
| scrapy#37 | Missed at low, found at high/max | yes | 0.0040 | 7 | yes | 0.0433 | 4 | no | 0.1332 | yes | 0.3441 | yes | 0.5707 |
| thefuck#1 | Missed at low, found at high/max | no | 0.0028 | 3 | no | 0.0304 | 3 | no | 0.1643 | yes | 0.3770 | yes | 1.0845 |
| tqdm#2 | Missed at low, found at high/max | no | 0.0047 | 5 | yes | 0.0437 | 5 | no | 0.1559 | yes | 1.3657 | yes | 1.1149 |
| ansible#3 | Never found | no | 0.0050 | 7 | no | 0.0502 | 5 | no | 0.1431 | no | 0.2772 | no | 1.2297 |
| black#1 | Never found | no | 0.0025 | 3 | no | 0.0284 | 3 | no | 0.1309 | no | 0.2038 | no | 0.2435 |
| fastapi#8 | Never found | no | 0.0030 | 5 | yes | 0.0506 | 6 | no | 0.1264 | no | 0.2111 | no | 0.4596 |
| keras#4 | Never found | no | 0.0049 | 7 | no | 0.0517 | 5 | no | 0.1563 | no | 0.7689 | no | 0.6894 |
| luigi#4 | Never found | no | 0.0025 | 5 | no | 0.0418 | 6 | no | 0.1339 | no | 0.2152 | no | 1.0815 |
| matplotlib#6 | Never found | no | 0.0036 | 3 | no | 0.0342 | 3 | no | 0.1784 | no | 0.5233 | no | 1.2240 |
| pandas#6 | Never found | no | 0.0044 | 4 | no | 0.0353 | 3 | no | 0.1546 | no | 0.3544 | no | 1.1839 |
| scrapy#2 | Never found | yes | 0.0053 | 5 | yes | 0.0569 | 4 | no | 0.2081 | no | 0.4490 | no | 0.6799 |
| thefuck#7 | Never found | no | 0.0039 | 6 | yes | 0.0502 | 6 | no | 0.1890 | no | 0.3929 | no | 0.9350 |
| tornado#4 | Never found | no | 0.0045 | 5 | no | 0.0462 | 5 | no | 0.1851 | no | 0.7788 | no | 0.9843 |
## Errors, timeouts and skipped bugs

None. All 60 sweep runs ended through `submit_findings`; no timeouts, no crashes, no
skipped bugs, and the judge returned no errors.

## Files

- `bugsinpy_bench/dataset/prepared_pilot30.json`: the 30 entries from `prepared_100.json`.
- `bugsinpy_bench/results/sweep_2026-11-26_sonnet55_high_pilot30/` and
  `sweep_2026-11-26_haiku55_medium_pilot30/`: suite, meta, per-bug runs, judged.json, scores.json.
- `agent_sdk/traces/run_389.txt` to `run_418.txt` (Sonnet) and `run_419.txt` to
  `run_448.txt` (Haiku).
- `bugsinpy_bench/router_inputs/`: `<project>_<bug>.diff` (the reviewer's
  `git diff --unified=3` of base..head), `<project>_<bug>.summary.json` (Haiku 5.5, one call
  per changed non-test Python file, merged per bug) and `_summary_cost.json`.

## Jev triage, scored from these results (added after the pilot)

Each bug was routed with `shared/routing.py` exactly as committed on
`claude/jev-model-routing` (`3e69e01`): Jev scores how deep a review the diff
needs and whether it is high-stakes, and the cheapest tier whose chance of
needing a deeper one is at most 0.15 is chosen. The commit subject stands in
for the PR title. No reviews were rerun: each bug takes the stored result and
cost of the tier it was routed to (light = Haiku 5.5 medium, standard =
Sonnet 5.5 high, deep = the May Opus 4.7 sweep). Jev's own cost was not measured.

Script: `bugsinpy_bench/scripts/route_and_score.py`. Output:
`bugsinpy_bench/routing/routes_pilot30.json` and `triage_scores.json`.
The Sonnet and Haiku results of the other pilot run (`bench/model-tiers-pilot`,
`332fe11`) are scored as "cloud".

**Routes (second pass, committed):** 0 light, 6 standard, 24 deep. Standard:
fastapi#8, luigi#2, matplotlib#6, pandas#30, thefuck#1, thefuck#7.
black#1 went deep on a 0.90 high-stakes score.

**Routing is not fully repeatable.** A first pass with the same code and inputs
(`routes_pilot30_pass1.json`) also sent luigi#4 and thefuck#9 to standard
(8 standard, 22 deep). Both sat at P(needs deep) 0.13 on the first pass and
0.17 on the second, either side of the 0.15 threshold.

| Setup | Found, this run | Cost, this run | Found, cloud run | Cost, cloud run |
|---|---:|---:|---:|---:|
| All Opus 4.7 max (no triage) | 19/30 | $30.67 | 19/30 | $30.67 |
| All Opus 4.7 high (no triage) | 17/30 | $16.37 | 17/30 | $16.37 |
| Jev triage, deep = Opus 4.7 max | 20/30 | $24.61 | 21/30 | $24.62 |
| Jev triage, deep = Opus 4.7 high | 19/30 | $14.50 | 20/30 | $14.51 |
| All Sonnet 5.5 high | 17/30 | $1.51 | 21/30 | $1.67 |
| All Haiku 5.5 medium | 16/30 | $0.14 | 18/30 | $0.17 |

With the first-pass routes, triage costs $22.94 (deep = max) and $13.83
(deep = high) with the same found counts.

The 30 bugs were chosen by the May Opus 4.7 outcomes, so the Opus columns are
fixed by construction. The extra bugs triage finds come from the "never found"
group, where Sonnet found thefuck#7 and fastapi#8.

## Opus 5.5 high on the same 30 bugs (2026-11-27)

`claude-opus-5-5` at high effort, sweep `sweep_2026-11-27_opus55_high_pilot30`,
traces `run_452.txt` to `run_481.txt`. Same settings, isolated CLI config, judge and
scoring as the pilot sweeps.

**One harness change.** The Agent SDK's bundled Claude Code CLI (2.1.126) is rejected
for Opus 5.5 (`claude_code_version_too_old`: 2.1.280 or newer required), and the SDK
always prefers its bundled CLI. `agent_sdk/reviewer.py` now passes
`cli_path=os.environ.get("REVIEW_CLI_PATH") or None`; unset, nothing changes. This
sweep used Claude Code 2.1.332. A Sonnet 5.5 smoke run on 2.1.332 had a first
request of 33,633 tokens against 34,508 on 2.1.126, with the same findings and
$0.1558 against $0.1484. The Opus 5.5 cost matches list prices recomputed from
usage ($4 / $20, cache write $5, cache read $0.20 per MTok).

**Result:** 22/30 found (found at low 10/10, found at high/max 8/10, never found
4/10) for $4.77, all runs ending through `submit_findings`. Missed: ansible#3,
black#1, keras#3, keras#4, luigi#4, matplotlib#6, sanic#1, tornado#4.

| Setup | Found, this run | Cost, this run | Found, cloud run | Cost, cloud run |
|---|---:|---:|---:|---:|
| All Opus 5.5 high (no triage) | 22/30 | $4.77 | 22/30 | $4.77 |
| Jev triage, deep = Opus 5.5 high | 21/30 | $4.14 | 22/30 | $4.16 |
| All Opus 4.7 max (no triage) | 19/30 | $30.67 | 19/30 | $30.67 |

On the 6 standard-routed bugs, Opus 5.5 found 5 for $0.86 and Sonnet 5.5 found 4
(this run) or 5 (cloud run) for about $0.24.

**Spend for this step:** smoke tests $0.50 (Sonnet and Opus 5.5 on the newer CLI,
plus one direct CLI check), sweep $4.77, judging $0.17. Total $5.44.
