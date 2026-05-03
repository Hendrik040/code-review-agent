# code-review-agent

A code-review agent harness, built **twice** — once on the bare Anthropic
Client SDK, once on the Claude Agent SDK — so the head-to-head numbers
make a clean pitch about agentic harness design.

The product of the project is the comparison, not the reviewer. See
[`docs/PLAN.md`](docs/PLAN.md) for the multi-phase plan and
[`docs/architecture.md`](docs/architecture.md) for the operational
reference.

## What's in here today

- `agent_sdk/offload_runner.py`, `client_sdk/offload_runner.py` —
  Phase-0 experiment: same `fetch_url` tool on both SDKs, measures how
  much of the tool output each path lets into the model's context. Run
  via `compare.py`.
- `shared/findings.py` — the `Finding` dataclass + JSON serializer that
  both reviewers will eventually fill (Phase 1.1).
- `code-review-baseline/ai-code-reviewer/` — the OpenAI-based baseline
  this project is porting and benchmarking against (pinned submodule).
- The reviewer modules (`*/reviewer.py`) and the rest of the `shared/`
  utilities land in Phase 1.

## Setup

Uses [**uv**](https://docs.astral.sh/uv/) for dependency and venv
management. Install uv if you don't have it:

```bash
brew install uv         # macOS
# or: curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then from this directory:

```bash
uv sync                       # creates .venv and installs locked deps
cp .env.example .env          # then fill in ANTHROPIC_API_KEY
git submodule update --init   # pull in the baseline (pinned commit)
```

The Agent SDK path requires the `claude` CLI on `PATH` (Claude Code must
be installed locally — the SDK shells out to it). For OAuth/Max-billed
runs, log in with `claude /login` once.

## Run (Phase-0 offload comparison)

```bash
uv run python compare.py                              # default: Wikipedia article
uv run python compare.py https://example.com         # small-page sanity
uv run python compare.py --use-oauth                 # bill Agent SDK via Max
```

Each run writes a per-run trace and result file under
`agent_sdk/{traces,results}/run_NNN.txt` and the same under
`client_sdk/`. The headline numbers print to stdout in a side-by-side
table (cost, turns, tokens, tool-result chars).

## Layout

See [`docs/architecture.md`](docs/architecture.md) for the full repo
layout and the design-pattern map.
