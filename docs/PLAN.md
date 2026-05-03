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

PHASE 2 — Agent SDK reviewer + tool/effort parity                    ✓ (PRs #21, #22)
   2.1  agent_sdk/reviewer.py — identical run() contract; in-process
        MCP exposes build_review_context + submit_findings; harness
        provides Read/Bash/Grep/Glob with built-in offloading.
        permission_mode=bypassPermissions, max_turns=100,
        SYSTEM_PROMPT_AGENT_SDK = canonical SYSTEM_PROMPT verbatim
        plus a small <sdk_note> mapping client-SDK tool names to
        harness names. Caching is harness-managed (no manual
        breakpoints — that's part of what we're comparing).      ✓ PR #21
   2.2  Tool-surface parity (ast_search + write_file added as MCP
        tools on Agent SDK; Glob dropped to match Client SDK) +
        `effort="xhigh"` pinned on both + MAX_TOKENS=16000.       ✓ PR #22
        Full sweep run; head-to-head doc updated. Reveals that
        xhigh hurts Client SDK and helps Agent SDK on the same
        fixture (sentry_93824) — asymmetric harness×effort
        interaction is now lesson #9.
   2.3  Effort-frontier sweep — the headline pitch graphic         ⏳
        Sweep all 7 fixtures on both SDKs at every effort level the
        Anthropic API exposes for Opus 4.7: low, medium, high, xhigh,
        max. That's 7 × 5 × 2 = 70 runs. Cost estimate: ~$80-150
        depending on how aggressive max is.

        Output: a 2×2 grid of charts (cost-vs-accuracy frontier),
        one panel per (billing model, SDK) cell:
          - Top-left:  API rate × Client SDK
          - Top-right: API rate × Agent SDK
          - Bot-left:  Max plan × Client SDK
                       (n/a — Client SDK doesn't run on Max)
          - Bot-right: Max plan × Agent SDK (harness-reported)
        Plus a single overlay chart with all four lines for the
        deck headline.

        The numeric axes per fixture run: cost, latency, num_turns,
        file_hit / line_hit, exit_reason. The aggregate axis: total
        cost vs total hits/7 per (SDK, effort) point. Five points
        per line × four lines = 20 data points on the headline
        graph. That's the pitch's load-bearing visual.

        We expect (hypotheses to test):
          - At low effort, Agent SDK might be hugely cheaper for
            modest accuracy loss — the "routine review" sweet spot.
          - The Client-vs-Agent gap shrinks at xhigh and max where
            the harness's compaction prevents over-exploration.
          - On Max plan billing, Agent SDK dominates accuracy-per-$.
          - On API billing, Client SDK dominates at low effort but
            crosses over somewhere in the medium/high band.

   2.4  Harness-stress fixtures — exercise what code review can't    ⏳
        The standard 7 fixtures are single-PR, scope-bounded, no
        session reuse — the worst case for showing off harness
        features. Add 3 fixtures shaped to the harness's strengths:

        2.4a  `sentry_bigdiff` — a real Sentry PR with 50+ changed
              files. Forces the harness's auto-offloading on `Read`
              to do real work; on Client SDK the model has to
              narrow manually with bash head/tail. Hypothesis:
              Agent SDK costs much less per-token because it
              doesn't pull whole files into context.

        2.4b  `multi_step_refactor` — a real cross-file refactor
              that requires reading the diff, understanding cross-
              file impact, AND verifying tests. Hypothesis: at
              MAX_TURNS=100, Client SDK exhausts the budget while
              Agent SDK's automatic compaction keeps context lean
              past turn ~50. We should see Client SDK hit
              exit=max_turns where Agent SDK still finishes.

        2.4c  `review_then_rereview` — a "review the PR, then
              re-review after the author pushes a fix" two-call
              session. Agent SDK uses session resume / continue
              to keep the original ODIS context warm; Client SDK
              has to rebuild from scratch. Hypothesis: Agent SDK
              is dramatically cheaper on the second call because
              the prior session's caches are still warm.

   2.5  Subagent dispatch demo — the harness's `Agent` tool         ⏳
        For very-large fixtures (e.g. the Phase 2.4a 50-file
        fixture), spawn one subagent per file cluster so each
        runs with its own clean context.

        - Agent SDK: built-in via the `Agent` tool + `agents=`
          option in ClaudeAgentOptions. ~30 LOC of glue.
        - Client SDK: we implement subagent dispatch from scratch
          (separate API conversations, context isolation, result
          aggregation). Estimated ~200-300 LOC.

        The implementation gap IS the demo. Run both on a 50-file
        fixture and measure:
          - Engineering effort (LOC, time-to-implement)
          - Cost on the same fixture
          - Accuracy (does subagent-isolated review find more or
            fewer planted bugs than monolithic review?)

        Output: pitch slide titled "Subagent dispatch on huge PRs"
        with a code-diff (Agent SDK 30 LOC vs Client SDK 250 LOC)
        and a results table.

   2.6  Recitation plan.md for long runs                             ⏳
        Manus pattern — long Agent SDK sessions write a `plan.md`
        every N tool calls to combat drift. Useful for the
        multi_step_refactor fixture from Phase 2.4b. Demonstrates
        another pattern the harness supports natively (via skills
        and CLAUDE.md auto-load).

PHASE 3 — Comparison + pitch                                         ⏳ ready
   3.1  compare.py --task review — THE Client-SDK-vs-Agent-SDK
        comparison, drives both reviewers across the fixture suite.
        Both reviewers now exist (PR #21), so 3.1 is unblocked.
        This is what produces the head-to-head numbers (cost,
        latency, finding overlap).
   3.2  ASCII flow diagrams (`docs/comparison.md`)
   3.3  Pitch document (`docs/pitch.md`) with the headline numbers
        and the four-panel effort-frontier grid from Phase 2.3

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

### Phase 2.1 head-to-head: at `effort="high"` (the implicit default)

First apples-to-apples sweep, both SDKs at the model's implicit `high` effort default.

| Fixture | Client SDK | Agent SDK | Cost delta |
|---|---|---|---:|
| contract_mismatch | 3 / $0.10 / Y/Y | 4 / $0.15 / Y/Y | +54% |
| sentry_80168 | 18 / $1.79 / Y/Y | 14 / $1.00 / Y/Y | **-44%** |
| sentry_80528 | 5 / $0.50 / Y/Y | 6 / $0.50 / Y/Y | ~same (post-fix) |
| sentry_67876 | 16 / $1.78 / N/N | 20 / $0.95 / N/N | both miss; -47% |
| sentry_93824 | 20 / $1.65 / Y/Y | 8 / $0.82 / N/N | -50%; Y→N |
| sentry_77754 | 14 / $1.09 / Y/Y | 12 / $0.50 / Y/Y | **-55%** |
| sentry_95633 | 13 / $2.18 / N/N | 21 / $2.05 / N/N | both miss; -6% |
| **Totals** | **$9.09 / 89 turns / 5/7** | **$5.96 / 85 turns / 4/7** | **-34%** |

At `high`: Agent SDK ~34% cheaper end-to-end; Client SDK has one more line-hit (`sentry_93824`). Two consistent misses on both (`sentry_67876` CSRF, `sentry_95633` Python 3.13).

### Phase 2.2 head-to-head: same suite at `effort="xhigh"` (Anthropic's recommended for coding/agentic)

Tool surface now identical between SDKs (Phase 2.2 added `ast_search` + `write_file` as MCP tools on the Agent SDK side, dropped `Glob`). `effort="xhigh"` pinned on both. `MAX_TOKENS=16000` on Client SDK; harness-managed on Agent SDK.

| Fixture | Client SDK | Agent SDK | Δ vs. `high` (Client) | Δ vs. `high` (Agent) |
|---|---|---|---|---|
| contract_mismatch | 3 / $0.11 / Y/Y | 4 / $0.20 / Y/Y | same | same |
| sentry_80168 | 16 / $1.76 / Y/Y | 19 / $1.30 / Y/Y | same | same |
| sentry_80528 | 5 / $0.46 / Y/Y | 7 / $0.39 / Y/Y | same | same |
| sentry_67876 | 42 / $6.03 / N/N | 23 / $1.62 / N/N | still miss; **3.4× cost** | still miss; +70% cost |
| sentry_93824 | 39 / $3.57 / **N/N** | 10 / $1.22 / **Y/Y** | **REGRESSED Y→N** | **CURED N→Y** |
| sentry_77754 | 18 / $1.44 / Y/Y | 10 / $0.54 / Y/Y | same | same |
| sentry_95633 | 29 / $4.56 / N/N | 25 / $4.50 / N/N | same N | same N |
| **Totals** | **$17.93 / 152 turns / 4/7** | **$9.76 / 98 turns / 5/7** | **+97% cost / -1 hit** | **+64% cost / +1 hit** |

**Cost delta at xhigh:** Agent SDK total $9.76 vs Client SDK $17.93 — **-45.5%**.

### The actual pitch story (much sharper than "Agent SDK is cheaper")

| Effort | Client SDK | Agent SDK | Winner |
|---|---|---|---|
| `high` (default) | 5/7 hits, $9.09 | 4/7 hits, $5.96 | Client wins on accuracy; Agent wins on cost |
| `xhigh` (Anthropic recommendation for coding) | 4/7, $17.93 | 5/7, $9.76 | **Agent wins on both** |

Four findings worth carrying into Phase 3:

1. **`xhigh` is not a free upgrade on the Client SDK.** Cost roughly doubled AND it lost a planted-bug hit (`sentry_93824` Y/Y → N/N — model over-explored, submitted a different bug from the same file). The Anthropic-docs heuristic "raise effort instead of prompting around it" is not unconditional — extra reasoning depth can backfire when the model has too much freedom to over-explore on hard fixtures.
2. **The harness's interaction with effort is asymmetric.** Same fixture (`sentry_93824`), same effort lift, opposite outcome — Client SDK regressed while Agent SDK was cured. Plausible explanation: the harness compacts/scopes turns differently than the bare loop does, so the same effort signal produces different exploration behavior. This is the most interesting open question for Phase 3.
3. **Two consistent misses survive across both SDKs and both effort levels** (`sentry_67876` CSRF / OAuth-state, `sentry_95633` Python-3.13-only API). Knowledge-frame gaps (security pattern recognition; cross-version Python awareness), not depth-of-reasoning gaps. xhigh + 42 Client turns / $6 didn't move them. Need a prompt addendum or a small RAG corpus to close.
4. **Practical recommendation for this benchmark:** `effort="high"` on Client SDK, `effort="xhigh"` on Agent SDK. Best 5/7 on each side at the lowest cost: Client SDK $9.09, Agent SDK $9.76. Each SDK has its own sweet spot — don't pick a single effort number for both.

These are the headline numbers for the Phase 3 pitch. The current head-to-head also lives in `docs/headtohead.md` and is rebuildable via `scripts/headtohead.py`.

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
9. **`effort` interacts asymmetrically with the harness** (Phase 2.2 sweep). Same effort knob (`high` → `xhigh`), same fixture (`sentry_93824`), opposite outcomes between SDKs: Client SDK regressed Y/Y → N/N (over-explored, submitted a different bug), Agent SDK cured N/N → Y/Y. The Anthropic docs' "raise effort instead of prompting around it" heuristic is not unconditional — extra reasoning depth can backfire on harder fixtures when the loop has freedom to over-explore. Practical takeaway: each SDK has its own sweet spot; don't pin a single effort number for both. For *this* benchmark, `high` on Client SDK + `xhigh` on Agent SDK gives 5/7 each at the lowest combined cost.
10. **Two misses survive every knob we've tried** (`sentry_67876` CSRF/OAuth, `sentry_95633` Python-3.13-only API). Constant across SDK choice, effort level, tool surface, and prompt patterns. These are knowledge-frame gaps, not budget or strategy gaps — the model needs domain priming (security antipatterns; Python-version awareness) it doesn't carry by default. Cure is a prompt addendum or a small targeted retrieval corpus, not more turns or more effort.

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
