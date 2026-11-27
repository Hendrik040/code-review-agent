# code-review-agent

> **📄 Talk slides (PDF): [How to build an effective agent harness for code review](docs/talks/effective-agent-harness.pdf)**
> 19 slides, opens right here on GitHub. Interactive version and benchmarks in [Talk slides](#talk-slides) below.

An agentic code-review harness built **twice** — once on the Anthropic
Client SDK, once on the Claude Agent SDK — for head-to-head comparisons
of agentic patterns. Includes a CodeRabbit-style **Learnings** vector
store: tag the bot on a PR with a correction and it remembers the
lesson for future reviews of the same codebase.

## Talk slides

Slides from the talk **How to build an effective agent harness for code
review with Claude** (...and which SDK to reach for when you do):
[`docs/talks/effective-agent-harness.pdf`](docs/talks/effective-agent-harness.pdf) (PDF, views on GitHub) or
[`docs/talks/effective-agent-harness.html`](docs/talks/effective-agent-harness.html).
It's a single self-contained file: download it and open it in any browser
([view it online](https://htmlpreview.github.io/?https://github.com/Hendrik040/code-review-agent/blob/main/docs/talks/effective-agent-harness.html)).
The benchmark numbers behind the Client SDK vs Agent SDK slides are in
[`docs/headtohead.md`](docs/headtohead.md).

> **Looking for the version without Jev?** The harness as it was before
> any Jev integration (every decision made by a Claude model) is kept on
> the [`pure-llm`](https://github.com/Hendrik040/code-review-agent/tree/pure-llm)
> branch. On `main`, Jev is used only when `TYPESAFE_API_KEY` is set.

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

# 3. Run the reviewer on any PR URL
uv run python scripts/github/review_pr.py \
  https://github.com/<owner>/<repo>/pull/<n>
```

The agent clones the PR, investigates the diff with `read_file_section`,
`bash`, `ast_search`, and `grep` tools, files structured findings, and
posts them as a single GitHub Pull Request Review with inline
line-anchored comments + a summary body. Default model:
`claude-opus-4-7` at `effort="max"` (the most capable mode).

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

### Model routing with Jev (Phase 7)

By default every PR is reviewed by `claude-opus-4-7` at `effort="max"`.
With `TYPESAFE_API_KEY` set, `review_pr.py` makes one call to
[Jev](https://typesafe.ai) (TypeSafe's decision model) after the clone
and before the agent starts, and picks a tier for that PR:

| Tier | For | Default model : effort |
|---|---|---|
| `light` | docs, comments, renames; no behavior change | `claude-haiku-5-5:medium` |
| `standard` | a behavior change you can judge from the diff | `claude-sonnet-5-5:high` |
| `deep` | correctness depends on code outside the diff, or high-stakes code | the reviewer's `MODEL`:`EFFORT` |

Jev returns a probability for each depth level. The router takes the
cheapest tier where the chance that the PR needs a deeper one is at
most `ROUTER_RISK` (default 0.15), and goes straight to `deep` when the
diff probably touches auth, payments, migrations or concurrency. No
key, a timeout or any Jev error also means `deep`, so routing can only
lower the cost of a review, never block one.

To compare setups on the fixtures, run one sweep per arm and compare
`suite_NNN.md` cost and line-hit (`--tier` runs a fixed tier with no
Jev call; `ROUTER_TIER_DEEP` sets what "deep" means):

```bash
uv run python scripts/run_suite.py --sdk agent --tier deep                  # old setup
ROUTER_TIER_DEEP=claude-opus-5-5:high uv run python scripts/run_suite.py --sdk agent --tier deep
uv run python scripts/run_suite.py --sdk agent --route                      # Jev routing
```

```bash
uv run python scripts/github/review_pr.py <pr_url>               # --tier auto
uv run python scripts/github/review_pr.py <pr_url> --tier deep   # skip Jev
uv run python scripts/run_suite.py --sdk agent --route           # measure it
```

The tier defaults and `ROUTER_RISK` are starting points, not tuned
values. Jev routes all seven planted-bug fixtures to `deep`, so
`run_suite.py --route` confirms routing doesn't under-serve hard PRs
but can't show a saving; for that, compare `--tier auto` against
`--tier deep` on a sample of your own merged PRs. To keep one model and route only
effort, point all three `ROUTER_TIER_*` variables at that model (see
`.env.example`). The Client SDK reviewer is not routed.

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

With `TYPESAFE_API_KEY` set, [Jev](https://typesafe.ai) (TypeSafe's
decision model) replaces Haiku as the classifier in this layer,
following TypeSafe's
[Classifying RAG passages](https://docs.typesafe.ai/cookbooks/classifying_rag_passages)
cookbook:

- **Retrieval.** Each retrieved learning gets one request with two
  yes/no questions: does it apply to this diff, and is it trying to
  make the reviewer do something other than review code. Learnings
  that fail either test are dropped; the rest are re-sorted by how
  likely they are to apply, so the `LEARNINGS_TOP_K` cut keeps the most
  applicable ones instead of the nearest vectors.
- **Capture.** A free-form @mention is stored only if Jev judges it a
  learning and not an instruction to the reviewer.

The thresholds live in one table in `learnings/jev_judge.py`, and each
verdict is logged with its probabilities so they can be tuned from
logs. Haiku remains the fallback if a Jev call fails, and
`LEARNINGS_JUDGE=haiku` switches Jev off here. One difference: Haiku
condensed a free-form mention into a lesson, while Jev cannot write
text, so a Jev-accepted mention is stored as the maintainer's own
paragraph with the handle removed.

The `scripts/demo.py` launcher spawns the capture daemon and the
reviewer together for a single-command end-to-end demo:

```bash
uv run python scripts/demo.py --repo owner/repo --pr <n>
```

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
