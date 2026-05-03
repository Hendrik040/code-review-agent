# Plan: Code-Review Agent Harness — Comparative Build (Client SDK vs Agent SDK)

## Context

You're not just building a code-review agent. You're building **the same code-review agent twice** — once on the bare Anthropic Client SDK, once on the Claude Agent SDK — and using the head-to-head comparison as a presentation/pitch about agentic harness design.

This builds directly on work already in `/Users/hendrikkrack/Desktop/code-review-agent/v1/`:
- `compare.py` orchestrator + `pricing.py` cost model + per-run `traces/`/`results/` folders are already wired and running.
- `agent_sdk/runner.py` and `client_sdk/runner.py` proved offloading and caching patterns experimentally on a `fetch_url` toy.
- The baseline at `code-review-baseline/ai-code-reviewer/` provides the ODIS (Outside-Diff Impact Slicing) algorithm we'll port — currently OpenAI-based, single-shot, Python-only.

The plan unrolls in many small phases, with **explicit interactive checkpoints** at each sub-step. We won't rush. Architecture locks in before code.

## Working agreement

- Each numbered sub-step below is a checkpoint. I show the artifact (spec, file, run output), you approve, we proceed.
- No file grows past ~200 LOC without an explicit reason.
- Comments explain *why*, never *what*. Code reads like prose for a human reviewer.
- No emojis. ASCII for diagrams.
- Plain Python; no LangChain or unnecessary frameworks.
- Phases 1 → 3 are the critical path for the comparison pitch. Phases 4+ extend both implementations symmetrically.

## Reference architecture: which patterns we're applying where

These come from Lance Martin's *Agent Design Patterns* post + the Anthropic, Manus, and Claude-diary articles linked from it. Each pattern has a clear home in our build.

| Pattern | Source | Where it lives in our harness |
|---|---|---|
| **Give agents a computer** | Lance Martin | Phase 4 (Daytona) — replaces local FS with sandbox shell. Also the Bash/Read/Grep tools we expose in Phase 1.5+. |
| **Multi-layer action space** | Lance Martin / CodeAct | Single `bash` tool composes linters/greps/finds rather than 10 specific tools. Phase 1 minimum tools, Phase 4+ leans further. |
| **Progressive disclosure** | Lance Martin / Anthropic | Tool definitions kept terse; agent runs `--help` or `Read` on a manifest if it needs detail. ODIS context is the first-shot prompt; deeper code is fetched on demand. |
| **Offload context** | Lance Martin / Manus | Already proven in `agent_sdk/`. The harness offloads ≥5 KB tool outputs to disk; we keep that behavior in Phase 2. Client SDK manually mimics with explicit `read_file_section(path, lines)` tool in Phase 1.5. |
| **Cache context** | Lance Martin / Manus | Stable system-prompt prefix (no timestamps), append-only message history, `cache_control` on the heavy ODIS context block in the Client SDK reviewer. Manus reports 10× cost delta from this alone. |
| **Isolate context** | Lance Martin / Anthropic | Phase 2.2 dispatches subagents for parallel per-file review. Each returns ~1-2 KB summary of a 10K+ token investigation (Anthropic's recommended shape). |
| **Evolve context** | Lance Martin / Claude-diary | Phase 6: filesystem diary at `v1/shared/memory/diary/YYYY-MM-DD-run-NNN.md`, manual `reflect` command updates a `REVIEW_RULES.md` that loads into the system prompt. Vector DB only if/when manual reflection scales out — explicitly not the v1 of the feedback loop. |
| **Recitation** | Manus | Long Agent SDK runs rewrite a `plan.md` every N tool calls to combat drift. Phase 2.x. |
| **Preserve error traces** | Manus | We do NOT prune failed tool calls from message history. Both SDKs. |
| **Just-in-time retrieval** | Anthropic | The agent receives file *paths* in the ODIS context and reads them only when needed; never the full repo upfront. Phase 1.5. |
| **Goldilocks system prompt** | Anthropic | System prompt < 500 tokens, organized with XML tags, kept identical between both SDK implementations to make the comparison clean. |

## Architecture (high level)

```
v1/
├── shared/                          (new — used by both SDKs)
│   ├── odis.py                      ported from baseline review_demo.py
│   ├── fixtures.py                  golden test repos + expected findings
│   ├── findings.py                  Finding dataclass + JSON serializer
│   ├── prompts.py                   the canonical system prompt + few-shot
│   └── memory/                      filled in Phase 6
│       └── REVIEW_RULES.md          reflection-curated rules; loads into prompt
├── client_sdk/
│   ├── runner.py                    existing offload comparison (keep)
│   ├── reviewer.py                  NEW Phase 1 — code-review agent
│   ├── results/                     existing per-run output convention
│   └── traces/                      existing per-run output convention
├── agent_sdk/
│   ├── runner.py                    existing
│   ├── reviewer.py                  NEW Phase 2
│   ├── results/
│   └── traces/
├── compare.py                       extended: --task offload | review
├── pricing.py                       (no change)
├── docs/
│   └── architecture.md              Phase 0 deliverable
└── code-review-baseline/            unchanged; reference only
```

**Shared I/O contract for both reviewers:**

```python
# Both client_sdk/reviewer.py and agent_sdk/reviewer.py expose:
def run(
    repo_path: Path,
    base_ref: str,           # e.g. "HEAD~1"
    head_ref: str,           # e.g. "HEAD"
    *,
    run_id: int | None = None,
    use_oauth: bool = False, # agent_sdk only
) -> dict[str, Any]:
    """Returns: {
        'findings': list[Finding],
        'cost_usd': float,
        'api_rate_cost_usd': float,
        'num_turns': int,
        'total_usage': dict,
        'tool_result_chars': int,
        'trace_path': str,
        'result_path': str,
        'run_id': int,
    }"""
```

**Finding shape** (matches the baseline's structured output, language-agnostic):

```python
@dataclass
class Finding:
    file: str            # path relative to repo root
    line: int            # primary line; range optional
    line_end: int | None
    category: str        # contract-mismatch | logic | concurrency | resource | error | security | other
    severity: str        # high | medium | low
    summary: str         # one-line headline
    detail: str          # 2-4 sentences explaining the bug
    suggested_fix: str   # diff-format suggestion (may be empty)
```

## Phase 0 — Architecture doc + agreement (now)

**Output:** this plan file + a one-page `v1/docs/architecture.md` you can read before any code is written.

Critical files to author in this phase:
- `/Users/hendrikkrack/.claude/plans/declarative-marinating-harp.md` (this file)
- `/Users/hendrikkrack/Desktop/code-review-agent/v1/docs/architecture.md` (Phase 0.1)

**Checkpoints in Phase 0:**

- 0.1 I write `docs/architecture.md` — single page, ~200 lines, with the diagram above + the I/O contract + the design-pattern table. You read it.
- 0.2 We pick the **fixture repo** for the comparison. Default candidate: `code-review-baseline/ai-code-reviewer/demo_project/` — it already has a planted contract-mismatch bug (function signature changed without updating callers) and is small enough to inspect by eye. We may add 1-2 more later.
- 0.3 We pick the **review prompt v0**. Starting point: the baseline's prompt in `review_demo.py:313–333` (quoted in `shared/prompts.py`). Reduced to <500 tokens. XML-tagged sections (per Anthropic's guidance).

## Phase 1 — Client SDK reviewer MVP (the slow path)

This is the bulk of the build. Each sub-step is its own checkpoint.

- **1.1 — Author `shared/findings.py`** (~30 LOC). Just the dataclass + JSON serializer. No model code yet.
- **1.2 — Port ODIS to `shared/odis.py`** from `code-review-baseline/ai-code-reviewer/review_demo.py`. Key functions to lift verbatim or near-verbatim: `changed_lines()` (lines 30-ish), `symbols_containing_lines()`, `symbols_with_signature_changes()`, `callgraph_for_files()`, `one_hop_slice()`, `snippet()`, `format_context_as_markdown()`. Replace OpenAI-specific bits. Keep Python-AST scope (matches user's "Python only" decision).
- **1.3 — Author `shared/fixtures.py`** (~50 LOC). Loads the demo_project, returns `(repo_path, base_ref, head_ref, expected_findings)`. Lets us assert correctness.
- **1.4 — Author `shared/prompts.py`** (~80 LOC). One file containing: `SYSTEM_PROMPT`, `USER_PROMPT_TEMPLATE`, optional `FEW_SHOT_EXAMPLES`. XML-tagged. Identical for both SDKs.
- **1.5 — `client_sdk/reviewer.py` v0: single-shot** (~120 LOC). `run()` calls `shared.odis.build_context(...)`, sends one `messages.create` with the structured-output JSON schema (Anthropic supports `tools` for structured output; we'll use a single `submit_findings` tool). No agentic loop yet. This is the ODIS port to Anthropic.
- **1.6 — `client_sdk/reviewer.py` v1: agentic loop** (~+80 LOC). Add tools: `read_file_section(path, start, end)`, `search_codebase(pattern, path_glob)`, `get_function_definition(symbol, file)`. The agent gets the ODIS context as starter, then can dig further. Manual tool-calling loop with append-only message history (per Manus). Cap turns at 12.
- **1.7 — Caching**, applied surgically. Mark `cache_control` on the system prompt + tools array (the stable prefix). **Skip caching the tool_result and ODIS context** — Phase 1.5 has only 2-4 turns, so there are no reads to amortize the write cost (we proved this empirically with the offload script: caching a tool_result with 0 reads cost +25%). Document this in code comments referring back to `compare.py` run_008.
- **1.8 — Wire into `compare.py`** with a `--task review` flag. Existing `--task offload` keeps working. Result file format extended to include findings list. Trace format unchanged (the new boxed style).
- **1.9 — Run on the fixture, capture run_010+**. Inspect findings. Sanity check: did it find the planted contract-mismatch bug?

**Checkpoints:** I show the diff after each sub-step. We don't move past 1.5 until you've actually read `client_sdk/reviewer.py` and we agree the loop is clean.

## Phase 2 — Agent SDK reviewer MVP

Same I/O contract. The harness does the heavy lifting we did manually in Phase 1.

- **2.1 — `agent_sdk/reviewer.py` v0** (~100 LOC). `create_sdk_mcp_server` with two tools: `build_odis_context(repo, base, head)` (calls `shared.odis`) and `submit_findings(findings)`. Allow `Read`, `Bash`, `Grep`, `Glob` from the harness — these *are* the agent's investigation tools, no need to reimplement.
- **2.2 — Subagent dispatch for >N changed files**. If the diff touches more than ~5 files, dispatch a Task subagent per file or per cluster. Each subagent has its own context, returns 1-2 KB findings summary. Lead agent dedupes and consolidates. (Anthropic pattern, Pattern 6.)
- **2.3 — Recitation `plan.md`** for long runs. After every 5 tool calls, the agent rewrites a `plan.md` listing files reviewed / files outstanding. (Manus pattern.)
- **2.4 — Run on same fixture, capture run_NNN**.

## Phase 3 — Comparison + pitch

- **3.1 — Fixture suite expansion**. Add 2 more repos: one larger (1-2 MB) to show the Agent SDK pulling ahead on offloading, one with cross-file impact to show subagent dispatch.
- **3.2 — Comparison table** in `compare.py` already exists; extend rows to include: `findings_count`, `findings_match_expected` (boolean), `latency_s`, the existing cost/turn columns.
- **3.3 — ASCII flow diagrams** in `docs/comparison.md` showing both architectures side by side (we have a draft from a prior turn — refine it).
- **3.4 — Pitch document** `docs/pitch.md`. ~500 words, the "why Agent SDK is worth it (or isn't) for this task". Refers to actual numbers from our runs, not generalities.

## Phase 4 — Daytona sandbox layer (only after Phase 3 lands)

Both reviewers swap local FS / `subprocess.run` for the Daytona Python SDK. Same I/O contract. Three sub-steps: provision sandbox, clone repo into it, route `read_file_section` / `Bash` through it.

This realizes the **Give Agents a Computer** pattern in its full form — the agent has a real isolated computer, not just our laptop's filesystem.

## Phase 5 — GitHub PR integration

A new front door: `code-review --pr <url>` clones the PR's branches, runs the reviewer, posts findings as inline review comments via `gh pr review` inside the Daytona sandbox. Designated GitHub account; PAT in `.env`.

## Phase 6 — Learning loop (filesystem first, vector DB later)

Per the **Claude-diary** post, the smart move is filesystem-based first:
- **6.1** — After each review run, optionally write `shared/memory/diary/YYYY-MM-DD-run-NNN.md` capturing: findings the user accepted, findings they rejected as false positives, any free-text response.
- **6.2** — A `reflect` CLI command reads accumulated diary entries, asks the model to distill recurring patterns into one-line bullets in `shared/memory/REVIEW_RULES.md`. Manual approval gate (per Claude-diary's lesson — never auto-update).
- **6.3** — `REVIEW_RULES.md` loads into the system prompt at every run. This is the **Evolve Context** pattern.
- **6.4** — Vector DB upgrade is *only* introduced if the manual diary corpus exceeds a few hundred entries. By default, plain markdown beats Pinecone for low volume.

## Phase 7 — Web search

`web_search(query)` and `web_fetch(url)` exposed to both SDKs. The Agent SDK gets these natively; the Client SDK gets a thin wrapper. Useful for: "is this CVE? is this idiomatic in this framework version?" Standard tool, low risk.

## Phase 8 — Docs MCP servers + gateway

Connect to Mintlify or Context7 MCP servers for project-specific docs. Add a small **MCP gateway** in front (separate process, in-memory cache) that:
1. Caches frequent doc lookups so the same query doesn't repeatedly burn tokens.
2. Filters tool descriptions to a token budget per turn (progressive disclosure pattern).
3. Drops responses that don't pass a relevance check (some MCP servers are noisy).

## Phase 9 — Linters in sandbox + subagent false-positive validation

In the Daytona sandbox: run `ruff`, `pyright`, `bandit`, etc. Pipe output to a subagent whose only job is "for each lint warning: open the file, decide if this is a real bug or a false positive". Returns a filtered list to the lead agent. This is **Pattern 6 (Isolate Context)** at its strongest — lint output can be huge, the lead agent never sees it.

## Verification plan

| Phase | Verification |
|---|---|
| 0 | You read `architecture.md` and approve, or send back changes. |
| 1 | `python compare.py --task review` finds the planted bug in `demo_project/`. JSON output validates against the `Finding` schema. Trace shows ≤12 turns. |
| 2 | Same fixture, same finding, comparable findings. Cost lower than Phase 1 at API rates. |
| 3 | `compare.py --task review` prints the comparison table; `docs/pitch.md` reproduces those numbers verbatim. |
| 4 | Both reviewers pass the same fixture test using a Daytona sandbox instead of local FS. |
| 5 | A PR with the planted bug, reviewed end-to-end, gets a real comment on GitHub at the right line. |
| 6 | A diary entry is written; `reflect` produces a sensible bullet you can hand-approve into `REVIEW_RULES.md`; subsequent runs cite the rule. |
| 7-9 | Each is a feature flag; tested independently, regression-tested against Phase 3's fixture suite. |

## What we're explicitly NOT doing in v1

- Multi-language support beyond Python (decided in clarifying Q&A).
- Real-time streaming UI / web dashboard.
- Vector DB before manual diary scales out.
- LangChain / LangGraph or other agent frameworks. We use the SDKs directly because the entire point is the comparison.
- LLM-as-a-judge for evaluation. For Phase 3 we hand-eval the small fixture suite.

## Critical files (cumulative across phases)

| Path | Phase | Purpose |
|---|---|---|
| `v1/docs/architecture.md` | 0 | Single-page reference |
| `v1/shared/odis.py` | 1.2 | Ported from `code-review-baseline/ai-code-reviewer/review_demo.py` lines 30-304 |
| `v1/shared/fixtures.py` | 1.3 | Golden test inputs |
| `v1/shared/findings.py` | 1.1 | `Finding` dataclass |
| `v1/shared/prompts.py` | 1.4 | Canonical prompt, identical across both SDKs |
| `v1/client_sdk/reviewer.py` | 1.5-1.7 | Manual tool loop |
| `v1/agent_sdk/reviewer.py` | 2.1-2.3 | `claude_agent_sdk.query` + harness |
| `v1/compare.py` | 1.8, 3.2 | Extended with `--task review` |
| `v1/pricing.py` | (existing) | Cost computation; reused |
| `v1/shared/memory/REVIEW_RULES.md` | 6.3 | Reflection output, loads into prompt |
| `v1/sandbox/daytona_client.py` | 4 | Thin wrapper around Daytona SDK |
| `v1/github/pr_runner.py` | 5 | gh CLI driver |
| `v1/mcp_gateway/` | 8 | Token-budget + cache layer |
