# Plan: Code-Review Agent Harness — Comparative Build (Client SDK vs Agent SDK)

## Context

You're not just building a code-review agent. You're building **the same agent twice** — once on the bare Anthropic Client SDK, once on the Claude Agent SDK — and using the head-to-head comparison as a presentation/pitch about agentic harness design.

This document is intentionally re-written end-to-end as of the consolidated PR #17 (Phase 1.7 caching + sentry_80168 fixture + agent-with-computer pivot + CR fixes + ast-grep skill). It supersedes prior versions; everything shipped to date is captured below with run numbers + cost evidence.

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
├── shared/
│   ├── findings.py            Finding dataclass + SUBMIT_FINDINGS_TOOL_* schema
│   ├── odis.py                Outside-Diff Impact Slicing (PR #17 has the
│   │                          changed_lines() fixes + UnicodeDecodeError fix)
│   ├── fixtures.py            Fixture dataclass + materialize() (recursive
│   │                          copytree, supports nested paths)
│   ├── prompts.py             SYSTEM_PROMPT + USER_PROMPT_TEMPLATE
│   │                          (codex-iterated, agent-with-computer aware)
│   ├── agent_tools.py         build_review_context / bash / read_file_section /
│   │                          ast_search / grep / write_file + tool schemas.
│   │                          Path-traversal guarded via _safe_target().
│   ├── skills/
│   │   └── ast_grep.md        Progressive-disclosure skill (134 lines)
│   └── memory/                Phase 6 home for diary entries + REVIEW_RULES.md
├── client_sdk/
│   ├── offload_runner.py      Phase 0 offload comparison (kept)
│   ├── reviewer.py            Phase 1.5+1.6+1.7 — agentic loop, 6 tools,
│   │                          MAX_TURNS=20, 3-breakpoint caching
│   ├── results/               Per-run findings + metrics
│   └── traces/                Per-run boxed trace
├── agent_sdk/
│   ├── offload_runner.py      Phase 0 (kept)
│   └── reviewer.py            Phase 2.1 — NOT YET BUILT
├── tests/fixtures/
│   ├── contract_mismatch/     Synthetic, hand-built (Phase 1.3)
│   ├── sentry_80168/          Real PR — abc.ABC subclass with `pass` body
│   └── (5 more in flight via subagent — sentry_80528, 67876, 93824, 77754, 95633)
├── scripts/
│   ├── build_pr_fixture.py    Generic GH-PR → fixture builder
│   ├── inspect_fixture.py     Manual test: see fixture contents
│   ├── inspect_odis.py        Manual test: see ODIS output
│   ├── inspect_tools.py       Manual test: each agent tool standalone
│   └── client_sdk/
│       ├── inspect_review.py  Manual test: end-to-end reviewer (1 API call)
│       └── smoke_phase16.py   Test A (dispatch) + Test B (forced tool use)
├── compare.py                 Phase 0 orchestrator (offload mode only).
│                              Phase 1.8 will add --task review.
├── pricing.py                 Cost calculator (Opus 4 rates)
├── docs/
│   ├── PLAN.md                this file
│   ├── architecture.md        operational reference
│   ├── verification.md        evidence gates before completion claims
│   ├── research/              prompt-research artifacts (PR #16)
│   ├── comparison.md          Phase 3 deliverable (not yet)
│   └── pitch.md               Phase 3 deliverable (not yet)
└── code-review-baseline/      submodule, OpenAI baseline (a48bca3)
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

PHASE 1.8 — wire compare.py with --task review                       ⏳ next
PHASE 1.9 — capture metrics on full fixture suite                    ⏳

PHASE 2 — Agent SDK reviewer MVP                                     ⏳
   2.1  agent_sdk/reviewer.py — same I/O contract, MCP tools, harness
        provides Read/Bash/Grep/Glob, we add build_review_context +
        submit_findings via @tool decorator
   2.2  Subagent dispatch for >5-file diffs
   2.3  Recitation plan.md for long runs
   2.4  Run on same fixture suite, capture metrics

PHASE 3 — Comparison + pitch                                         ⏳
   3.1  Fixture suite expansion (mostly done — see fixture inventory)
   3.2  compare.py table extension (already extended for offload runs)
   3.3  ASCII flow diagrams (`docs/comparison.md`)
   3.4  Pitch document (`docs/pitch.md`) with the headline numbers

PHASE 4 — Daytona sandbox layer                                      ⏳
PHASE 5 — GitHub PR integration                                      ⏳
PHASE 6 — Filesystem-based learning loop                             ⏳
PHASE 7 — Web search                                                 ⏳
PHASE 8 — Docs MCP servers + gateway                                 ⏳
PHASE 9 — Linters in sandbox + subagent FP validation                ⏳
```

## Empirical evidence to date (the comparison-pitch gold)

| Run | Fixture | Variant | Turns | Cost | Tool calls (key) | Bug found? |
|---|---|---|---:|---:|---|---|
| #11 | contract_mismatch | v0 single-shot, no cache | 2 | $0.13 | submit_findings | ✓ |
| #13 | contract_mismatch | v2 agent-with-computer | 3 | $0.25 | build_review_context + submit | ✓ |
| #14 | sentry_80168 | v2, no cache, MAX=12 | 12 (cap) | $5.17 | 12 tools, no submit | ✗ |
| #16 | sentry_80168 | v2 + caching, MAX=20 | 17 | $1.68 | 22 tools incl. ast_search | ✓ |
| #17 | sentry_80168 | v2 + caching + skill | 17 | $1.64 | 16 tools, all-bash | ✓ |

Caching delta on the headline fixture: **3.1× cost reduction + 0→1 finding correctness gained**. That's the headline graphic for the Phase 3 pitch.

## Fixture inventory

```
tests/fixtures/
├── contract_mismatch/         synthetic, planted signature change
├── sentry_80168/              real, abc.ABC subclass with pass body
├── sentry_80528/              real, function mutates local config         (in flight)
├── sentry_67876/              real, OAuth state CSRF risk                  (in flight)
├── sentry_93824/              real, isinstance(SpawnProcess) always False  (in flight)
├── sentry_77754/              real, mutable datetime.now() default         (in flight)
└── sentry_95633/              real, queue.shutdown() Python <3.13          (in flight)
```

The five "in flight" entries are being built by a subagent on branch `phase-1/sentry-fixtures-batch` (target: stack on PR #17).

## Architectural lessons learned (worth carrying forward)

1. **ODIS pre-baked vs ODIS-as-tool**: agency requires the latter. PR #13 pivoted from "ODIS in user prompt" to "build_review_context tool"; the agent now actually decides whether/when to fetch context. Cost ~2× on simple fixtures, same outcome — pays back on hard fixtures.
2. **Caching breakpoint placement**: system + tools + rolling last-message. Each cache breakpoint is one of Anthropic's 4 max. Avoid per-tool_result markers with 0 reads (we measured +25% in a prior offload run). Skill nudges that say "read X first" can backfire — the model abandons the wrapped tool entirely.
3. **MAX_TURNS scales with cache cost**: caching makes deeper turns affordable; raised from 12 to 20.
4. **Stacked PR consolidation**: one merge per phase. Re-target the latest PR to main, close ancestors. CR auto-review only fires on default-base PRs; we do this consolidation when ready for review.
5. **Fixture's expected Finding must match the prompt's localization rule**: when the prompt allows "caller/callee whose contract was broken," the fixture's `file` field becomes flexible. We may need a "matches any of these locations" matcher for future fixtures.

## Open background work

- Subagent `ae1d22d...` building 5 more Sentry fixtures (target: PR stacked on #17).
- CR auto-review on PR #17 in progress (51 files, takes 5-10 min). After it lands, dispatch fresh CR-triage subagent with longer poll window.

## Verification matrix

| Phase | Success means |
|---|---|
| 0 | Architecture doc approved; fixture + prompt v0 chosen. |
| 1 | `client_sdk/reviewer.py:run()` finds the planted bug on contract_mismatch and sentry_80168 within budget. |
| 2 | Agent SDK reviewer matches Phase 1's findings with comparable cost; harness handles offload+caching automatically. |
| 3 | Pitch numbers reproduce verbatim from `compare.py --task review`. |
| 4 | Both reviewers pass the fixture suite using a Daytona sandbox. |
| 5 | A real PR gets a real CR-style comment at the right line. |
| 6 | Diary entry → reflect → REVIEW_RULES.md → next-run citation. |
| 7-9 | Each is a feature flag; tested independently. |
