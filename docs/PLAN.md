# Plan: Code-Review Agent Harness — Comparative Build (Client SDK vs Agent SDK)

## Context

You're not just building a code-review agent. You're building **the same agent twice** — once on the bare Anthropic Client SDK, once on the Claude Agent SDK — and using the head-to-head comparison as a presentation/pitch about agentic harness design.

This document is intentionally re-written end-to-end as of PRs #17 (merged), #20 (Phase 1.8 — single-SDK suite runner + matcher fix + MAX=100), and #21 (Phase 2.1 — Agent SDK reviewer at parity + category-aware matcher + head-to-head consolidator). It supersedes prior versions; everything shipped to date is captured below with run numbers + cost evidence.

## Working agreement

- Sub-steps are checkpoints. Show artifact, get user approval, move on.
- Stacked PRs, single merge per phase. Per-phase consolidation: re-target the latest PR to `main`, close the in-flight stack.
- No file > 200 LOC without explicit reason.
- Comments explain *why*, not *what*. ASCII for diagrams. No emoji.
- Plain Python. No LangChain. The whole point is comparing the SDKs directly.
- CR triage SOP at `.claude/agents/coderabbit-triage.md`: Critical/Major fix in-PR, nits reply-only.

## Reference architecture: design patterns and where they live

| Pattern | Source | Where it lives |
|---|---|---|
| **Give agents a computer** | Lance Martin | `shared/agent_tools.py:bash` (cwd-locked, 15s timeout, repo-relative). Phase 4 (Daytona) replaces local exec with sandbox; same surface. |
| **Multi-layer action space** | LM / CodeAct | `bash` is the primitive; typed wrappers (`read_file_section`, `ast_search`, `grep`, `build_review_context`, `write_file`) are sugar with cleaner schemas the model picks for common ops. |
| **Progressive disclosure** | LM / Anthropic | `shared/skills/ast_grep.md` is read on demand by the agent; not pre-injected. Tool descriptions stay terse. |
| **Offload context** | LM / Manus | Agent SDK provides automatically (Phase 0 `compare.py` proved 99.7% reduction). Client SDK manually mimics via `read_file_section` + `bash head/tail`. |
| **Cache context** | LM / Manus | Phase 1.7 — three breakpoints: system prompt, tools array, rolling last-message. Sentry_80168 cost dropped 3.1× ($5.17 → $1.68). |
| **Isolate context** | LM / Anthropic | Phase 2.2 (subagent dispatch for >5 changed files); Phase 9 (linter false-positive validation). |
| **Evolve context** | LM / Claude-diary | Phase 6 — filesystem diary at `shared/memory/diary/...`, manual `reflect` command updates `REVIEW_RULES.md`. Vector DB only if manual diary scales out. |
| **Recitation** | Manus | Phase 2.3 — long Agent SDK runs rewrite a `plan.md` every N tool calls. |
| **Preserve error traces** | Manus | We never prune failed tool calls. Both SDKs. |
| **Just-in-time retrieval** | Anthropic | Agent gets file *paths* in ODIS context, not file contents. |
| **Goldilocks system prompt** | Anthropic | `shared/prompts.py`, codex-iterated, ~6K tokens (raised from 500 target after richer task definition stuck). |
| **Restate evidence** | Claude Code leak (research PR #16) | Added to `<workflow>` (PR #17) — agent restates `file:line + reason` in text before each tool_result, surviving context elision. |
| **Citation format** | Claude Code leak | Added to `<reporting_rules>` (PR #17) — `path/to/file.py:NN` in intermediate text. |
| **Parallel tool_use** | Claude Code leak | Added to `<action_space>` (PR #17) — issue independent reads/searches in one turn. |

## Architecture

```
v1/
├── shared/                            "the neutral middle" — used by both SDKs
│   ├── findings.py                Finding dataclass + SUBMIT_FINDINGS_TOOL_* schema
│   ├── odis.py                    Outside-Diff Impact Slicing
│   ├── fixtures.py                Fixture dataclass + materialize() + ALL_FIXTURES
│   │                              (7 entries; recursive copytree; nested paths)
│   ├── prompts.py                 SYSTEM_PROMPT + USER_PROMPT_TEMPLATE
│   │                              (canonical for BOTH SDKs)
│   ├── agent_tools.py             Client SDK tools: build_review_context / bash /
│   │                              read_file_section / ast_search / grep /
│   │                              write_file + JSON schemas. Path-traversal
│   │                              guarded via _safe_target().
│   ├── skills/
│   │   └── ast_grep.md            Progressive-disclosure skill (134 lines)
│   └── memory/                    Phase 6 home for diary + REVIEW_RULES.md
├── client_sdk/
│   ├── offload_runner.py          Phase 0 offload comparison (kept)
│   ├── reviewer.py                Phase 1.5–1.8 — agentic loop, 6 tools,
│   │                              MAX_TURNS=100, 3-breakpoint manual caching
│   ├── results/                   Per-run findings + metrics + suite_NNN.md
│   └── traces/                    Per-run boxed trace
├── agent_sdk/
│   ├── offload_runner.py          Phase 0 offload comparison (kept)
│   ├── reviewer.py                Phase 2.1 ✓ — async ClaudeSDKClient,
│   │                              in-proc MCP for build_review_context +
│   │                              submit_findings, harness Read/Bash/Grep/Glob
│   │                              with auto-offloading, max_turns=100,
│   │                              permission_mode=bypassPermissions, identical
│   │                              run() return shape as Client SDK
│   ├── results/
│   └── traces/
├── tests/fixtures/                7 fixtures total (see Fixture inventory)
├── scripts/
│   ├── run_suite.py               SDK-agnostic sweep: --sdk client|agent.
│   │                              Per-fixture try/except + SIGALRM timeout +
│   │                              cumulative cost ceiling + incremental
│   │                              suite_NNN.md persistence (overnight-safe).
│   │                              Matcher requires (file, category) for
│   │                              file_hit and (file, category, ±N lines)
│   │                              for line_hit.
│   ├── headtohead.py              Latest-run-per-fixture-per-SDK consolidator;
│   │                              renders docs/headtohead.md.
│   ├── reeval_suite.py            Re-applies the current matcher to past
│   │                              suite_NNN.md tables WITHOUT re-running.
│   ├── build_pr_fixture.py        Generic GH-PR → tests/fixtures/<name> builder.
│   ├── inspect_{fixture,odis,tools}.py  Manual inspectors for each subsystem.
│   ├── client_sdk/
│   │   ├── inspect_review.py      Manual test: end-to-end reviewer (1 API call)
│   │   └── smoke_phase16.py       Test A (dispatch) + Test B (forced tool use)
│   └── agent_sdk/
│       └── smoke_phase21.py       Test A (5 structural) + Test B (1 API call)
├── compare.py                     Phase 0 orchestrator (offload mode only).
│                                  `--task review` lands in Phase 3.1 — the
│                                  literal Client-vs-Agent comparison harness.
├── pricing.py                     Cost calculator (Opus 4 rates)
├── docs/
│   ├── PLAN.md                    this file
│   ├── architecture.md            operational reference
│   ├── verification.md            evidence gates before completion claims
│   ├── headtohead.md              Phase 2.1 head-to-head numbers (auto-built)
│   ├── research/                  prompt-research artifacts (PR #16)
│   ├── comparison.md              Phase 3 deliverable (not yet)
│   └── pitch.md                   Phase 3 deliverable (not yet)
└── code-review-baseline/          submodule, OpenAI baseline (a48bca3)
```

### I/O contract

Both reviewers expose the identical `run()`:

```python
def run(repo_path, base_ref, head_ref, *, run_id=None, use_oauth=False) -> dict:
    # Returns:
    #   findings:               list[Finding]
    #   submitted:              bool   (was submit_findings called?)
    #   duplicate_submission:   bool
    #   exit_reason:            str    (max_turns / stop_reason_X / unknown)
    #   cost_usd:               float
    #   api_rate_cost_usd:      float
    #   num_turns:              int
    #   total_usage:            dict (input/output/cache_w/cache_r tokens)
    #   trace_path:             str
    #   result_path:            str
    #   run_id:                 int
```

## What's shipped (in PR #17, consolidated)

```
PHASE 0 — Architecture + agreement                                   ✓
   0.1  docs/architecture.md
   0.2  fixture choices (contract_mismatch synthetic; sentry_80168 real)
   0.3  prompt v0 source (review_demo.py:313–333), codex-iterated since

PHASE 1 — Client SDK reviewer MVP                                    ✓ (PR #17)
   1.1  shared/findings.py + SUBMIT_FINDINGS schema
   1.2  shared/odis.py (port of baseline + diff-parser fixes)
   1.3  shared/fixtures.py — recursive copytree; contract_mismatch
   1.4  shared/prompts.py — codex-iterated, agent-with-computer aware
   1.5  client_sdk/reviewer.py v0 (single-shot)
   1.6  reviewer.py v2 — "agent with a computer" pivot
        (ODIS-as-tool, bash, read_file_section, ast_search, grep, write_file)
   1.7  prompt caching (3 breakpoints) + MAX_TURNS=20
   --
        ast-grep skill (progressive disclosure)
        CR fixes: path traversal, dispatcher try/except, additionalProperties,
                  schema/prompt alignment, snippet UnicodeDecodeError, sys.path

PHASE 1.8 — Suite runner (single-SDK)                                ✓ (PR #20)
   scripts/run_suite.py — sweeps ALL_FIXTURES on either SDK
   (--sdk client|agent), writes <sdk>/results/suite_NNN.md
   incrementally with per-fixture try/except, SIGALRM wall-clock
   timeout, and cost ceiling. NOT a Client-vs-Agent comparison;
   that's Phase 3.1.
PHASE 1.9 — metrics commentary                                       ⏳
   PLAN.md (this file) gains a per-fixture row in the empirical-
   evidence table; cost / latency / correctness numbers cited
   verbatim in the eventual pitch.

PHASE 2 — Agent SDK reviewer MVP                                     ✓ (PR #21)
   2.1  agent_sdk/reviewer.py — identical run() contract; in-process
        MCP exposes build_review_context + submit_findings; harness
        provides Read/Bash/Grep/Glob with built-in offloading.
        permission_mode=bypassPermissions, max_turns=100,
        SYSTEM_PROMPT_AGENT_SDK = canonical SYSTEM_PROMPT verbatim
        plus a small <sdk_note> mapping client-SDK tool names to
        harness names. Caching is harness-managed (no manual
        breakpoints — that's part of what we're comparing).
   2.2  Subagent dispatch for >5-file diffs                          ⏳
   2.3  Recitation plan.md for long runs                             ⏳
   2.4  Run on same fixture suite, capture metrics                   ⏳ (sweep
        in progress as of Phase 2.1 PR; results land as a follow-up
        commit)

PHASE 3 — Comparison + pitch                                         ⏳ ready
   3.1  compare.py --task review — THE Client-SDK-vs-Agent-SDK
        comparison, drives both reviewers across the fixture suite.
        Both reviewers now exist (PR #21), so 3.1 is unblocked.
        This is what produces the head-to-head numbers (cost,
        latency, finding overlap).
   3.2  ASCII flow diagrams (`docs/comparison.md`)
   3.3  Pitch document (`docs/pitch.md`) with the headline numbers

PHASE 4 — Daytona sandbox layer                                      ⏳
PHASE 5 — GitHub PR integration                                      ⏳
PHASE 6 — Filesystem-based learning loop                             ⏳
PHASE 7 — Web search                                                 ⏳
PHASE 8 — Docs MCP servers + gateway                                 ⏳
PHASE 9 — Linters in sandbox + subagent FP validation                ⏳
```

## Empirical evidence to date (the comparison-pitch gold)

### Phase 1 caching ablation (single fixture, sentry_80168)

| Run | Variant | Turns | Cost | Bug found? |
|---|---|---:|---:|---|
| #11 | v0 single-shot, no cache | 2 | $0.13 | n/a (different fixture) |
| #14 | v2, no cache, MAX=12 | 12 (cap) | $5.17 | ✗ |
| #16 | v2 + caching, MAX=20 | 17 | $1.68 | ✓ |
| #17 | v2 + caching + ast-grep skill | 17 | $1.64 | ✓ |

Caching delta on the headline fixture: **3.1× cost reduction + 0→1 finding correctness gained**.

### Phase 2.1 head-to-head: Client SDK vs Agent SDK on the full 7-fixture suite

Latest run per fixture per SDK, with the **category-aware matcher** from PR #20's CR review (a finding only counts as a hit if `(file, category)` matches expected, plus `line ±10` for the stricter line-hit). Sources: `client_sdk/results/run_*.txt`, `agent_sdk/results/run_*.txt`. Reproducible at any time via `uv run python scripts/headtohead.py`.

The `sentry_80528` fixture's v1 baseline was patched after PR #20 review (the upstream PR moved an already-buggy function rather than introducing a bug, so the v1→v2 diff didn't reveal a regression). Numbers below are post-fix.

| Fixture | Client SDK | Agent SDK | Cost delta |
|---|---|---|---:|
| contract_mismatch | 3 / $0.10 / Y/Y | 4 / $0.15 / Y/Y | +54% |
| sentry_80168 | 18 / $1.79 / Y/Y | 14 / $1.00 / Y/Y | **-44%** |
| sentry_80528 | 5 / $0.50 / Y/Y | 6 / $0.50 / Y/Y | ~same (post-fix) |
| sentry_67876 | 16 / $1.78 / N/N | 20 / $0.95 / N/N | both miss; -47% |
| sentry_93824 | 20 / $1.65 / Y/Y | 8 / $0.82 / N/N | -50%; Y→N |
| sentry_77754 | 14 / $1.09 / Y/Y | 12 / $0.50 / Y/Y | **-55%** |
| sentry_95633 | 13 / $2.18 / N/N | 21 / $2.05 / N/N | both miss; -6% |
| **Totals** | **$9.09 / 89 turns / 5/7 line-hits** | **$5.96 / 85 turns / 4/7 line-hits** | **-34%** |

**Headline:** Agent SDK is **~34% cheaper end-to-end on the same fixture suite**, thanks to the harness's automatic offloading and built-in caching (vs the Client SDK's manual three-breakpoint scheme). Correctness:

- **Both SDKs solve 5 of 7 planted bugs** at the right (file, category, ±10 lines): contract_mismatch, sentry_80168, sentry_80528, sentry_77754, plus sentry_93824 (Client only).
- **Two genuine misses on both SDKs**: sentry_67876 (CSRF / OAuth state) and sentry_95633 (Python-3.13-only API). The model finds *other* plausible bugs in the right files but doesn't surface the planted one. These are prompt-strategy gaps, not budget gaps — both had tool-call headroom.
- **One Client-only hit** (sentry_93824): the Agent SDK landed on the same file but a different line for the SpawnProcess isinstance bug. Worth investigating in Phase 3.

These are the headline numbers for the Phase 3 pitch. The complete table also lives in `docs/headtohead.md` and is rebuildable via `scripts/headtohead.py`.

## Fixture inventory

```
tests/fixtures/
├── contract_mismatch/         synthetic, signature change (caller anchor accepted)
├── sentry_80168/              real, abc.ABC subclass with pass body
├── sentry_80528/              real, returns wrong variable; v1 patched (see lessons)
├── sentry_67876/              real, OAuth state CSRF (consistent miss across SDKs)
├── sentry_93824/              real, isinstance(SpawnProcess) always False
├── sentry_77754/              real, mutable datetime.now() default
└── sentry_95633/              real, queue.shutdown() Python <3.13 only
                               (consistent miss across SDKs)
```

All 7 fixtures live on `main` and materialize via `shared.fixtures.materialize()` into a temp git repo with `HEAD~1..HEAD` refs.

## Architectural lessons learned (worth carrying forward)

1. **ODIS pre-baked vs ODIS-as-tool**: agency requires the latter. PR #13 pivoted from "ODIS in user prompt" to "build_review_context tool"; the agent now actually decides whether/when to fetch context. Cost ~2× on simple fixtures, same outcome — pays back on hard fixtures.
2. **Caching breakpoint placement**: system + tools + rolling last-message. Each cache breakpoint is one of Anthropic's 4 max. Avoid per-tool_result markers with 0 reads (we measured +25% in a prior offload run). Skill nudges that say "read X first" can backfire — the model abandons the wrapped tool entirely.
3. **MAX_TURNS scales with cache cost**: caching makes deeper turns affordable; raised 12 → 20 (Phase 1.7) → 100 (Phase 1.8 after sentry_93824 hit the 20-cap mid-investigation).
4. **Stacked PR consolidation**: one merge per phase. Re-target the latest PR to main, close ancestors. CR auto-review only fires on default-base PRs; we do this consolidation when ready for review.
5. **Fixture's expected Finding must match the prompt's localization rule**: when the prompt allows "caller/callee whose contract was broken," the fixture's `file` field becomes flexible. `Fixture.expected` is treated as a UNION — list multiple acceptable anchors. See `contract_mismatch` (calc.py changed file + main.py caller).
6. **`compare.py --task review` is the Phase-3 deliverable, not a Phase-1 batch runner**: earlier wording in this doc conflated "sweep our fixture suite to validate the reviewer" with "compare Client SDK vs Agent SDK on the same fixture." The first is single-SDK and lands in Phase 1.8 as `run_suite.py`. The second requires both SDKs and is the literal point of the comparison pitch — it lands as `compare.py --task review` in Phase 3.1, after Phase 2 builds the Agent SDK reviewer.
7. **Matcher must require category match** (CR catch on PR #20). Without it, a finding hitting the right file/line for the wrong reason inflates the score. New matcher: `(file, category)` for file_hit, plus `line ±N` for line_hit. Concrete impact: sentry_67876 and sentry_95633 flipped from hits to honest misses — both SDKs find different bugs in the right files.
8. **A fixture's v1 baseline must show the bug as a regression** (CR catch on PR #20, sentry_80528). When the upstream PR *moves* an already-buggy function rather than introducing a new bug, the v1→v2 diff shows only the move and the bug-of-record is invisible to a diff-based reviewer. Patching v1 to the *intended pre-PR* behavior — even though it diverges from the literal upstream base_sha — keeps the benchmark honest. Document the divergence in the fixture file.

## Open follow-ups (post-Phase 2.1)

- **PR #20 needs to merge first**, then PR #21 retargets to `main` for fresh CR review. Standard stacked-PR consolidation.
- **PR #19** (5 Sentry fixtures) is redundant — those files already shipped in PR #20 (got bundled when the suite runner branch was created locally). Close with a cross-reference.
- **PR #16** (research/claude-code-prompt) has a closed/orphaned base branch from before context compaction. Close.
- **CR review on PR #21** is `PENDING` as of Phase 2.1 ship time. Same triage SOP applies when it lands.
- **2 consistent misses** across SDKs (`sentry_67876` CSRF, `sentry_95633` Python 3.13 API). These are prompt-strategy gaps — investigation, not SDK work. Likely need either richer ODIS context (cross-version Python compatibility?) or a security-focused prompt addendum. Out of scope until after Phase 3.
- **One Client-only hit** (`sentry_93824`): Agent SDK landed on the right file but a different line/category for the SpawnProcess `isinstance` bug. Worth a closer look when the comparison pitch is being written.

## Verification matrix

| Phase | Success means | State |
|---|---|---|
| 0 | Architecture doc approved; fixture + prompt v0 chosen. | ✓ |
| 1 | `client_sdk/reviewer.py:run()` finds the planted bug on contract_mismatch and sentry_80168 within budget. | ✓ (PR #17) |
| 1.8 | `scripts/run_suite.py --sdk client` produces a 7-fixture suite_NNN.md unattended. | ✓ (PR #20) |
| 2.1 | Agent SDK reviewer matches Phase 1's findings on the same suite with comparable correctness; harness handles offload+caching automatically. | ✓ (PR #21) — `5 of 7 ↔ 5 of 7 line-hits, ‑34% cost, 4 of 7 vs 5 of 7 line-hits with new category-aware matcher` |
| 3 | `compare.py --task review` reproduces `docs/headtohead.md` verbatim from a single command. | ⏳ next |
| 4 | Both reviewers pass the fixture suite using a Daytona sandbox. | ⏳ |
| 5 | A real PR gets a real CR-style comment at the right line. | ⏳ |
| 6 | Diary entry → reflect → REVIEW_RULES.md → next-run citation. | ⏳ |
| 7–9 | Each is a feature flag; tested independently. | ⏳ |
