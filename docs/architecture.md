# code-review-agent — Architecture

The plan, scope, and phases live in [`PLAN.md`](./PLAN.md). This document is the
**operational reference**: what files exist, what they expose, and which design
pattern each piece embodies. New code without a clear cell on the design-pattern
map below should be questioned.

## Goal

Build the same code-review agent twice — once on the Anthropic Client SDK, once
on the Claude Agent SDK — and use the head-to-head comparison as a presentation
about agentic harness design. The product of this project is the comparison,
not the reviewer.

## Repo layout

```text
v1/
├── shared/                          imported by both SDK implementations
│   ├── odis.py                      Outside-Diff Impact Slicing (port of baseline)
│   ├── fixtures.py                  golden test repos + expected findings
│   ├── findings.py                  Finding dataclass + JSON serializer + tool schema
│   ├── prompts.py                   canonical system prompt + few-shot
│   ├── agent_tools.py               build_review_context / bash /
│   │                                read_file_section / ast_search / grep /
│   │                                write_file + their tool schemas
│   │                                (used by both SDKs)
│   └── memory/                      reflective rules (Phase 6)
│       └── REVIEW_RULES.md
├── client_sdk/
│   ├── offload_runner.py            Phase-0 offload comparison (existing)
│   ├── reviewer.py                  code-review agent (Phase 1.5/1.6)
│   ├── results/
│   └── traces/
├── agent_sdk/
│   ├── offload_runner.py            existing
│   ├── reviewer.py                  code-review agent (Phase 2)
│   ├── results/
│   └── traces/
├── compare.py                       orchestrator (--task offload | review)
├── pricing.py                       cost computation
├── docs/
│   ├── PLAN.md                      multi-phase plan
│   ├── architecture.md              this file
│   ├── verification.md              evidence gates before completion claims
│   ├── comparison.md                Phase 3: ASCII diagrams + numbers
│   └── pitch.md                     Phase 3: presentation deck
├── sandbox/                         Phase 4: Daytona client wrapper
├── github/                          Phase 5: gh CLI driver
├── mcp_gateway/                     Phase 8: MCP token-budget + cache layer
└── code-review-baseline/            submodule pinned at a48bca3c
    └── ai-code-reviewer/            source of ODIS algorithm
```

## I/O contract

The shapes below describe the **Phase 1 reviewer contract** (the
`reviewer.py` modules listed in the repo layout, not the existing
offload `runner.py` files which already take `url` and return
`tool_result_text` / `next_turn_input_tokens`). Both reviewers will
expose the identical `run()` signature so `compare.py --task review`
can drive them interchangeably:

```python
def run(
    repo_path: Path,
    base_ref: str,           # e.g. "HEAD~1"
    head_ref: str,           # e.g. "HEAD"
    *,
    run_id: int | None = None,
    use_oauth: bool = False, # agent_sdk only; client_sdk ignores
) -> dict[str, Any]:
    ...
```

Returned dict:

| Key | Type | Description |
|---|---|---|
| `findings` | `list[Finding]` | parsed from the model's `submit_findings` tool calls |
| `cost_usd` | `float` | actual billed cost (Max OAuth or API key, whichever) |
| `api_rate_cost_usd` | `float` | what it would cost at standard public Opus 4 rates |
| `num_turns` | `int` | tool-loop iterations |
| `total_usage` | `dict` | input/output/cache_w/cache_r token totals |
| `tool_result_chars` | `int` | total chars across tool_results the model saw |
| `trace_path` | `str` | `<sdk>/traces/run_NNN.txt` |
| `result_path` | `str` | `<sdk>/results/run_NNN.txt` |
| `run_id` | `int` | shared monotonic across both SDKs (compare.py controls) |

## Finding shape

```python
@dataclass
class Finding:
    file: str            # path relative to repo root
    line: int            # primary line
    line_end: int | None
    category: str        # contract-mismatch | logic | concurrency
                         # | resource | error | security | other
    severity: str        # high | medium | low
    summary: str         # one-line headline
    detail: str          # 2-4 sentences explaining the bug
    suggested_fix: str   # diff-format suggestion; may be empty
```

Mirrors the baseline's structured-output schema so we can swap implementations
without breaking downstream consumers.

## Design-pattern map

Each pattern from Lance Martin's agent_design post (with additions from
Anthropic, Manus, and the Claude-diary post) lands somewhere concrete:

| Pattern | Source | Where it lives |
|---|---|---|
| Give agents a computer | LM | Phase 1.6 v2: the agent has `bash` (cwd-locked to the repo, 15s timeout), `read_file_section`, `write_file` (filesystem-as-memory). Phase 4 (Daytona) replaces local execution with a real sandbox; the tool surface stays identical. |
| Multi-layer action space | LM / CodeAct | `bash` is the general primitive; typed wrappers (`read_file_section`, `ast_search`, `grep`, `build_review_context`, `write_file`) are sugar with cleaner schemas the model picks for common ops. `ast_search` is backed by [`ast-grep`](https://ast-grep.github.io) — single Rust binary, structural patterns like `add($$$)` or `def $NAME($$$): $$$`, multi-language. Phase 4 sandbox image will need ast-grep preinstalled. |
| Progressive disclosure | LM / Anthropic | Tool definitions terse; agent runs `--help` if needed. ODIS context is the first-shot prompt; deeper reads happen on demand. |
| Offload context | LM / Manus | Already proven in `agent_sdk/runner.py` (run 002 → 99.7% reduction). Maintained in Phase 2; manually mimicked in `client_sdk/reviewer.py` via a `read_file_section` tool in Phase 1.5. |
| Cache context | LM / Manus | `cache_control` on system prompt + tools array. Skip caching tool_results in 2-turn flows (see `compare.py` run_008 — naive caching cost +25%). |
| Isolate context | LM / Anthropic | Phase 2.2: subagent dispatch for >5-file diffs. Each returns ~1 KB summary of 10K+ token investigation. Phase 9: linter false-positive validation. |
| Evolve context | LM / Claude-diary | Phase 6: filesystem diary at `shared/memory/diary/YYYY-MM-DD-run-NNN.md`. `reflect` command updates `REVIEW_RULES.md`. Manual approval gate. |
| Recitation | Manus | Phase 2.3: long Agent SDK runs rewrite a `plan.md` every N tool calls to combat drift. |
| Preserve error traces | Manus | We never prune failed tool calls from message history. Both SDKs. |
| Just-in-time retrieval | Anthropic | Agent gets file *paths* in ODIS context, not file contents. Reads on demand. |
| Goldilocks system prompt | Anthropic | `shared/prompts.py` < 500 tokens, XML-tagged, identical between SDKs. |

## Working agreement

- Each numbered sub-step in `PLAN.md` is a checkpoint: I show the artifact, you
  approve, we move on.
- No file > 200 LOC without an explicit reason.
- Comments explain *why*, not *what*.
- ASCII for diagrams. No emoji.
- Plain Python — no LangChain, no agent frameworks. The whole point is comparing
  the SDKs directly.

## Out of scope for v1

- Multi-language support beyond Python.
- Real-time streaming UI / web dashboard.
- Vector DB before manual diary scales out.
- LLM-as-a-judge for evaluation. Hand-eval the small fixture suite in Phase 3.

## Success bars per phase

| Phase | Success means |
|---|---|
| 0 | This file approved; fixture repo + prompt v0 chosen. |
| 1 | `python compare.py --task review` finds the planted bug; ≤12 turns; valid Finding schema. |
| 2 | Same fixture, comparable findings, lower API-rate cost than Phase 1. |
| 3 | `docs/comparison.md` and `docs/pitch.md` reproduce numbers from compare.py runs verbatim. |
| 4 | Both reviewers pass Phase 1's fixture using a Daytona sandbox. |
| 5 | Real PR gets a real comment at the right line via `gh pr review`. |
| 6 | A diary entry is written; `reflect` produces a sensible bullet that gets human-approved into `REVIEW_RULES.md`. |
| 7-9 | Each is a feature flag; tested independently; regression on Phase 3 fixture suite holds. |
