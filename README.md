# code-review-agent

An agentic code-review harness built **twice** — once on the Anthropic
Client SDK, once on the Claude Agent SDK — for head-to-head comparisons
of agentic patterns. Includes a CodeRabbit-style **Learnings** vector
store: tag the bot on a PR with a correction and it remembers the
lesson for future reviews of the same codebase.

## Quick start

Review a real GitHub PR end-to-end with the Agent SDK at maximum effort:

```bash
# 1. Install
brew install uv ast-grep gh                  # macOS (or use upstream installers)
uv sync                                       # creates .venv, installs deps
git submodule update --init                   # baseline (pinned commit)

# 2. Authenticate
gh auth login                                 # for cloning + reading PRs
cp .env.example .env                          # then fill in the 5 keys (see below)

# 3. One command, full demo run
uv run python scripts/full_agent_run.py \
  https://github.com/<owner>/<repo>/pull/<n>
```

That single command:

1. Spawns the **Learnings capture daemon** in the background (polls
   GitHub every 30s for new `@Working-Ant <call-word> <text>`
   mentions on the watched repo).
2. Runs the **Agent SDK reviewer** at `effort="max"` on the PR you
   passed — clones the PR, investigates the diff with
   `read_file_section`, `bash`, `ast_search`, and `grep` tools, files
   structured findings, and posts them as a single GitHub Pull Request
   Review with inline line-anchored comments + a summary body.
3. Keeps the daemon alive afterwards so any learnings you tag during
   the demo (`@Working-Ant remember …` on a finding, in the GitHub
   UI) land in Qdrant. Ctrl-C cleanly stops the daemon when you're
   done. Re-run this script to get a fresh review pass that picks up
   newly-captured learnings.

The reviewer does NOT auto-rerun on every new learning — each Agent
SDK pass costs ~$1-2 and 5+ minutes, so we leave the second-pass
trigger to you. Use `--no-daemon` to skip the daemon entirely (just
review and exit), or `scripts/github/review_pr.py <url>` directly if
you want the reviewer alone.

> **Important — collaborator requirement.** The bot account
> (`Working-Ant` by default) must be a **collaborator on the target
> repository with at least Write access**. The script's pre-flight
> checks fail fast if not, so you don't waste a 2-minute clone before
> finding out. To rebrand the handle, change `LEARNINGS_HANDLE` in
> `.env` and use a different bot user's PAT.

### Required `.env` keys

| Key | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API for the reviewer model |
| `GITHUB_REVIEW_BOT_TOKEN` | Bot user's personal-access token (used to POST the review) |
| `VOYAGE_API_KEY` | Voyage `voyage-code-3` embeddings (Learnings layer) |
| `QDRANT_URL` | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | Qdrant Cloud API key |

The Learnings layer (Voyage + Qdrant) is **strictly additive** — the
reviewer keeps running and posts findings even if those services are
unreachable, just without the past-learnings prompt block.

---

## Beyond the quick start

### Tuning effort + reviewer choice

The Agent SDK reviewer's effort level is set by the `EFFORT` constant
in `agent_sdk/reviewer.py`. Defaults to `"max"`. Other options, in
order of capability and cost: `"low" | "medium" | "high" | "xhigh" |
"max"`. Lower effort is faster and cheaper but finds fewer bugs. See
`docs/PLAN.md` for the effort-frontier data we collected during
Phase 2.3.

The **Client SDK** reviewer (`client_sdk/reviewer.py`) uses the
Anthropic SDK directly with a hand-rolled tool loop, 3-breakpoint
prompt caching, and the same `Finding` schema as the Agent SDK. Useful
for comparing harness vs. bare-loop economics — see
[`docs/headtohead.md`](docs/headtohead.md) for the full per-fixture
numbers.

### Evaluation harness — sweep the fixture suite

`scripts/run_suite.py` runs either reviewer across the 7 planted-bug
Sentry fixtures and writes a `suite_NNN.md` table with cost / turns /
findings / line-hit per fixture:

```bash
uv run python scripts/run_suite.py --sdk agent              # Agent SDK
uv run python scripts/run_suite.py --sdk client             # Client SDK
```

`scripts/headtohead.py` consolidates the latest run of each SDK into
[`docs/headtohead.md`](docs/headtohead.md) for the comparison story.

### The Learnings layer (Phase 6)

Tag the bot on a PR review comment with
`@Working-Ant {learn|remember|note|teach} <text>` and the capture
daemon will:

1. Extract the @mention as a learning anchored to the AST unit
   (function / method / module-scope) containing the comment line.
2. Embed the code chunk via `voyage-code-3` and store it in Qdrant
   Cloud (one collection per repo, named
   `learnings__<owner>_<repo>`).
3. On every subsequent review, retrieve high-similarity past learnings
   for the new diff and inject them into the reviewer's prompt as a
   `<past_learnings>` block.

Run the capture daemon (one-shot or watching):

```bash
uv run python -m learnings.capture --repo owner/repo --once   # process once + exit
uv run python -m learnings.capture --repo owner/repo --watch  # poll forever
```

Natural-language replies (e.g.
`@Working-Ant in this codebase that pattern is intentional`) also work
via a Haiku-classifier fallback. If the comment is a reply to one of
the bot's own review comments, the parent's text is captured as
`bug_context` for richer retrieval signal.

For the one-command end-to-end demo (capture daemon + reviewer
together), use `scripts/full_agent_run.py` — see the Quick Start above.

### Inspecting state

- **Stored learnings:** visible in your Qdrant Cloud console under the
  collection `learnings__<owner>_<repo>`.
- **Capture daemon's per-repo cursor:**
  `shared/memory/learnings_state.json` (gitignored — runtime state).
- **Reviewer traces (full tool-by-tool log):**
  `agent_sdk/traces/run_NNN.txt` (Agent SDK) and
  `client_sdk/traces/run_NNN.txt` (Client SDK).
- **Reviewer findings (header + JSON):**
  `agent_sdk/results/run_NNN.txt` and `client_sdk/results/run_NNN.txt`.

### Architecture + design

- [`docs/architecture.md`](docs/architecture.md) — operational
  reference: where each pattern lives, what each module exposes.
- [`docs/PLAN.md`](docs/PLAN.md) — multi-phase plan, empirical-evidence
  tables, lessons learned per phase.
- [`docs/headtohead.md`](docs/headtohead.md) — Client SDK vs Agent SDK
  comparison numbers across the fixture suite.
- [`docs/superpowers/specs/`](docs/superpowers/specs/) — design specs
  for individual phases (Phase 5 GitHub integration, Phase 6 Learnings
  vector DB).

## Project conventions

- Each new file ≤ 200 LOC (load-bearing for pitch-explainability).
- Comments explain *why*, not *what*.
- Plain Python — no LangChain, no agent frameworks. The whole point is
  comparing the two SDKs directly.
- Stacked PRs with one merge per phase. CR triage SOP at
  `.claude/agents/coderabbit-triage.md`: Critical/Major fix in-PR,
  Minor/Nit reply-only.
