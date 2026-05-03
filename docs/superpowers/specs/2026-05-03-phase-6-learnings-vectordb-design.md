# Phase 6 — Learnings (VectorDB) Design

**Status:** Design approved 2026-05-03 (brainstorming session). Ready for implementation planning.
**Owner:** Hendrik Krack (`Hendrik040`)
**Branch:** `phase-6/learnings-vectordb` (worktree at `~/Desktop/code-review-agent-phase6/`)
**Implementation gating:** waits on Phase 5 merge. Steps 1–6 of the implementation sequence are unblocked today against a stubbed GitHub adapter.

## 1. Purpose

Replicate CodeRabbit's "Learnings" feature: when a maintainer tags the bot on a
PR with a correction, store that correction (anchored to its enclosing AST unit)
in a vector store. On every subsequent review, retrieve high-similarity past
learnings for the new diff and surface them to the reviewer so it can apply
them. The pitch artifact is a before/after diff of the reviewer's output on the
same PR — first run with empty learnings, second run after a single mention has
been captured. Same model, same prompt scaffolding, different output.

This phase **replaces** the original Phase 6 ("Filesystem-based learning loop"
— manual diary + `reflect` → `REVIEW_RULES.md`). The plan's earlier
out-of-scope line "Vector DB before manual diary scales out"
(`docs/architecture.md:142`) is deliberately reversed here: we skip the diary
and go straight to vectors. The "Evolve context" pattern slot in the
design-pattern map is now filled by retrieval, not hand-curated rules.

## 2. Goals and non-goals

**Goals**

- Capture maintainer corrections via an `@Working-Ant <call-word> <text>` syntax
  in PR review comments. Polling-based; no webhooks.
- Embed corrections at function/method/module-scope granularity (AST units via
  ast-grep). Same chunker for capture and query so embeddings stay in the same
  semantic neighborhood.
- Store in Qdrant Cloud, one collection per repo, with code chunk text +
  learning text + PR metadata in the payload.
- On every review: chunk the diff into AST units, search the repo's collection
  per unit, threshold-filter, applicability-filter via Haiku 4.5
  (`claude-haiku-4-5-20251001`), inject top-K (5) into the reviewer's user
  prompt as a fixed `<past_learnings>` XML section.
- Expose `search_learnings(query)` as a tool for ad-hoc retrieval beyond the
  auto-injected block. Both SDKs implement it; new axis on the head-to-head
  pitch table.
- Layer is strictly additive: any failure in retrieval, embedding, vector
  search, or applicability filtering must NOT prevent the reviewer from
  completing a review.
- Each new file ≤ 200 LOC (the project's load-bearing rule).

**Non-goals**

- Not a real-time webhook receiver. No public URL, no ngrok.
- No reply-to-bot-comment auto-capture (CodeRabbit's other trigger). Explicit
  `@mention` syntax only. Reply-to-bot is a future extension.
- No Daytona / sandbox integration. Capture pipeline runs on the host.
  (Reviewer-side retrieval inherits whatever sandbox the reviewer uses.)
- No migration tooling. The first run starts with an empty store; learnings
  accumulate as maintainers tag them.
- No multi-tenant auth, no per-user collections. Single-org demo.
- No web UI. Stdout logs + Qdrant Cloud's web console for inspection.
- No observability layer (metrics, tracing). Debug logging only.

## 3. Architecture

```
v1/
├── learnings/                          NEW — capture-side, single process
│   ├── __init__.py
│   ├── capture.py                      entry: --once / --watch modes; polls
│   │                                   GitHub adapter, dispatches to
│   │                                   extractor → chunker → embedder → store
│   ├── extractor.py                    parses @Working-Ant <call-word> <text>
│   │                                   from PR review comment bodies
│   ├── ast_chunker.py                  ast-grep wrapper. Two entry points:
│   │                                   - chunk_for_anchor(file, line_range)
│   │                                     -> enclosing AST unit text + span
│   │                                     (capture side)
│   │                                   - chunks_for_diff(repo_path, diff)
│   │                                     -> list[chunk] for changed AST units
│   │                                     (query side)
│   ├── voyage_client.py                Voyage embed wrapper: voyage-code-3,
│   │                                   batching, exponential backoff
│   ├── qdrant_store.py                 Qdrant Cloud client, collection-per-
│   │                                   repo, idempotent bootstrap, upsert,
│   │                                   search
│   ├── github_adapter.py               Phase-5-shaped wrapper:
│   │                                   list_open_prs, list_pr_review_comments
│   │                                   (calls into github/pr_fetch.py
│   │                                   functions we contribute upstream)
│   └── state.py                        per-repo last-seen comment cursor
│                                       persisted to
│                                       shared/memory/learnings_state.json
│
├── shared/
│   ├── learnings.py                    NEW — retrieval-side, ≤ 200 LOC,
│   │                                   used by BOTH reviewers
│   │                                   - retrieve_for_diff(repo, diff)
│   │                                     -> list[Hit]
│   │                                   - applicability_filter(hits, diff)
│   │                                     -> filtered hits via Haiku
│   │                                   - format_for_prompt(hits) -> str
│   │                                     (the <past_learnings> XML block)
│   │                                   - search_tool_handler(query, k)
│   │                                     -> list[Hit] (the search_learnings
│   │                                     tool body)
│   ├── memory/
│   │   └── learnings_state.json        capture cursor; gitignored
│   └── skills/
│       └── learnings_search.md         NEW — progressive-disclosure skill,
│                                       loaded by the model on demand. Documents
│                                       query formulation tactics for the
│                                       search_learnings tool.
│
├── client_sdk/reviewer.py              EDITED: builds prompt with
│                                       shared.learnings.format_for_prompt()
│                                       output as a <past_learnings> section;
│                                       registers search_learnings tool
│
├── agent_sdk/reviewer.py               EDITED: same two integrations,
│                                       search_learnings exposed as MCP tool
│                                       on the in-process MCP server
│
├── github/                             EDITED (contributed back to Phase 5):
│   └── pr_fetch.py                     +list_open_prs(owner_repo, since)
│                                       +list_pr_review_comments(pr, since)
│                                       +Comment dataclass (body, author,
│                                        file_path, line_start, line_end,
│                                        comment_id, created_at)
│
├── scripts/
│   └── demo.py                         NEW — launcher: spawns capture daemon
│                                       as subprocess + runs reviewer; SIGINT
│                                       cleanly shuts down both
│
└── tests/learnings/                    NEW — unit + integration; live Qdrant
                                        Cloud against test__<random>
                                        collections (no in-memory mode)
```

**Architectural rationale**

- **`learnings/` (capture) vs. `shared/learnings.py` (retrieval).** Capture is
  single-process, doesn't need SDK parity, owns external I/O (Voyage, Qdrant
  Cloud writes, GitHub polling). Retrieval is on the hot path of every review,
  needs to be importable from both SDK reviewers, owns minimal logic (read +
  filter + format). Different lifetimes, different concerns, different files.
- **Reviewer integration is two surgical edits, not a wrapper.** Each
  `reviewer.py` gains one prompt-building call and one tool registration.
  Total diff per reviewer ≈ 30 LOC. A "reviewer with learnings" decorator
  would obscure what the reviewer does and make traces harder to read.
- **`github/pr_fetch.py` upstream contribution.** Phase 5 doesn't need
  `list_open_prs` or `list_pr_review_comments`, but the gh-api plumbing
  (`_gh_json`, `_gh_json_paginated`) lives there already. Adding two thin
  functions next to the existing ones is cleaner than duplicating the
  plumbing in `learnings/github_adapter.py`. The adapter then becomes a thin
  Phase-6-shaped facade, ~30 LOC.
- **200-LOC budget per file** is enforced. If `capture.py` grows past ~150
  LOC, it splits.

## 4. Trigger syntax

Maintainer leaves a PR review comment (anchored to a file + line/range by
GitHub's standard PR-review-comment mechanic). The extractor builds the regex
at runtime from `LEARNINGS_HANDLE` and `LEARNINGS_CALL_WORDS` (both
`re.escape`'d):

```
{escaped_handle}\s+({call_word_alternation})\b\s*[:.\-]?\s*(.+)
```

with the default config that resolves to:

```
@working-ant\s+(learn|remember|note|teach)\b\s*[:.\-]?\s*(.+)
```

- Handle: `@Working-Ant`, case-insensitive (regex compiled with `re.IGNORECASE`).
- Call words: configurable list in `learnings/extractor.py`, default
  `["learn", "remember", "note", "teach"]`.
- Captured group `(.+)` is the learning text. Whitespace stripped, multi-line
  comments collapsed via standard whitespace normalization.
- Anchor (file + line range) comes from GitHub's comment payload, not parsed
  from the body.
- Comments not matching the regex are ignored (skip + advance cursor).
- Reply-to-bot-comment auto-capture is a future extension; this phase only
  captures explicit `@mention` form.

## 5. Data flow

### 5.1 Capture pipeline (in the daemon, runs every `--interval` seconds, default 60)

```
        ┌───────────────────────────────────────────────┐
        │ Loop forever (or once if --once flag)         │
        └───────────────────────────────────────────────┘
                              │
                              ▼
   for each watched repo:
     [P5+P6] github_adapter.list_open_prs(repo, since=cursor)
     [P5+P6] github_adapter.list_pr_review_comments(pr, since=cursor)
                              │
                              ▼
     [P6]    extractor.parse(comment.body) -> Mention | None
             - regex match
             - skip if already seen (state.json has comment_id)
                              │
                              ▼
     [P6]    chunk_for_anchor(file=comment.file_path,
                              line_range=(comment.line_start, line_end))
             - read file at PR head SHA (cloned via Phase 5's
               repo_setup.setup_pr_repo, which we reuse)
             - ast-grep finds enclosing function/method/module-scope unit
             - returns chunk_text + chunk_kind + actual line span
                              │
                              ▼
     [P6]    voyage_client.embed(chunk_text) -> vec[1024]
             qdrant_store.upsert(
                collection=collection_for(repo),
                point=Point(
                  id=hash(repo, comment_id),
                  vector=vec,
                  payload=full_payload
                )
             )
             state.advance(repo, comment_id)
```

**Failure isolation**: every per-comment operation is wrapped in
`try/except`. A bad comment (malformed mention, file not found in checkout,
embed timeout after retries) gets logged and skipped, with the cursor
advancing past it so we don't retry forever. Per-PR errors don't abort the
loop.

**At-least-once semantics**: cursor advances *after* successful upsert. If
the daemon crashes between embed and upsert, the same comment is reprocessed
next iteration. The Qdrant point ID is `uuid5(NAMESPACE_URL, f"{repo}:{comment_id}")`
— deterministic — so reprocessing overwrites the same point, no duplicates.

### 5.2 Review pipeline (inside both reviewers)

```
   reviewer.run(repo_path, base_ref, head_ref) starts
                              │
                              ▼
     Phase 1+2 work (unchanged): build_review_context, ODIS, diff parse
                              │
                              ▼
     [P6] shared.learnings.retrieve_for_diff(repo, diff,
                                             chunker=ast_chunker,
                                             embedder=voyage_client,
                                             store=qdrant_store)
          - chunks_for_diff() identifies enclosing AST units of changed lines
            (dedupe: a unit with many changes is still one chunk)
          - embed each unit
          - search collection_for(repo), top-K=5 per unit
          - merge + dedupe by point_id
          - filter by score >= 0.78 (configurable, see §10)
                              │
                              ▼
     [P6] applicability_filter(hits, diff)
          - Haiku call per candidate: "given this diff hunk and this past
            learning, is the learning applicable here? yes/no/maybe"
          - drop "no"; keep "yes" + "maybe"; cap at 5 results
          - skipped if --no-filter flag set or env LEARNINGS_FILTER=0
                              │
                              ▼
     [P6] format_for_prompt(filtered) -> str
          - returns <past_learnings>...</past_learnings> XML block
          - empty string if no hits (no section emitted at all)
                              │
                              ▼
     reviewer's user prompt = ODIS context
                            + format_for_prompt(filtered)
     tools registered: existing tools + search_learnings
                              │
                              ▼
     reviewer runs as before; submit_findings as before.
```

**Cost added per review (rough)**:
- Voyage embed: N changed-AST-units × ~1k tokens × $0.00006/1k = fractions of a cent
- Qdrant search: free on the free tier
- Applicability filter: ≤5 Haiku calls × ~1k tokens ≈ ~$0.005
- **Total additive: ~$0.01 per review**, noise vs. the $0.50–$5 reviewer cost.

### 5.3 Critical timing assumption

For the demo, the capture daemon must be running **before** the reviewer fires
to show "look, a learning was captured then applied" in one session. The
launcher (`scripts/demo.py`) enforces ordering: daemon starts first, settles,
*then* reviewer fires.

## 6. Storage schema

One Qdrant Cloud collection per repo, named `learnings__<repo-slug>` (slug =
`owner-name` lowercased, slashes replaced with underscores).

Collection config:
- Vector size: 1024 (Voyage `voyage-code-3` dimension)
- Distance: cosine
- On-disk: yes (persistent, free tier supports it)

Point shape:

```python
Point(
    id=str,                              # UUIDv5 over (UUID_NAMESPACE_URL,
                                         # f"{repo}:{comment_id}") — Qdrant
                                         # requires either int or UUID-format
                                         # string; UUIDv5 is deterministic so
                                         # re-upserts overwrite the same point
    vector=list[float],                  # voyage_code_3.embed(code_chunk_text)
    payload={
        "code_chunk_text":  str,         # the embedded function/method body
        "learning_text":    str,         # the @mention's captured text
        "repo":             str,         # "owner/name"
        "pr_number":        int,         # GitHub PR number
        "file_path":        str,         # e.g. "src/foo.py"
        "line_start":       int,         # 1-indexed
        "line_end":         int,         # 1-indexed; equal to line_start
                                         # if comment was single-line
        "chunk_kind":       str,         # "function" | "method" |
                                         # "module-scope" | "fallback_window"
        "language":         str,         # "python" only for v1
        "author":           str,         # GitHub login of the maintainer
        "captured_at":      str,         # ISO-8601 UTC
        "commit_sha":       str,         # PR head SHA at capture time
    },
)
```

Both `code_chunk_text` and `learning_text` are stored. Retrieval needs both at
format time: the model sees the human-written learning AND the code it was
anchored to. The vector is built only from `code_chunk_text`, because that's
what query-time AST units look like.

## 7. Prompt integration

### 7.1 The auto-injected `<past_learnings>` block

Appended to the **user prompt** (not system prompt) so it's per-PR and doesn't
poison cache for other reviews. Goes after the ODIS context, before the
reviewer's `<task>` block:

```xml
<repository_context>
  ... existing ODIS output ...
</repository_context>

<past_learnings>
  <intro>
    These are corrections previous maintainers have given for code with
    similar shape. Treat them as priors, not rules. If a learning clearly
    applies to a finding you're about to make, cite it; if it suggests a
    finding you'd otherwise miss, raise that finding. If it doesn't apply,
    ignore it silently.
  </intro>
  <item id="1" score="0.84" file="src/js/node/perf_hooks.ts" lines="211-213"
        author="Jarred-Sumner" pr="oven-sh/bun#22338" captured="2025-09-02">
    <learning>Always use .$apply instead of Reflect.apply in Bun's codebase.</learning>
    <original_code language="typescript"><![CDATA[
... the embedded function/method text from capture-time ...
    ]]></original_code>
  </item>
  <item id="2" score="0.79" ...>
    ...
  </item>
</past_learnings>

<task>
  ... existing task block ...
</task>
```

Design choices:
- **XML, not markdown.** Matches the system prompt + ODIS output convention
  already in use (`PLAN.md:32`).
- **`<intro>` policy embedded in the section.** Three sentences, embedded in
  the data, not the system prompt. Section only appears when there ARE
  learnings; putting policy in the system prompt makes it conditional dead
  context on most PRs early on.
- **`score` exposed.** Helps the model weight items.
- **`<learning>` text first, then `<original_code>`.** The learning is the
  call to action; the code is supporting evidence.
- **Block omitted entirely** if no items pass the filter. Empty
  `<past_learnings/>` would still consume model attention.

### 7.2 The `search_learnings` tool

```python
SEARCH_LEARNINGS_TOOL = {
    "name": "search_learnings",
    "description": (
        "Search past maintainer corrections by free-text query. Use when "
        "you suspect a finding's category (security, concurrency, etc.) "
        "or pattern matches something previously taught, but the auto-"
        "injected <past_learnings> didn't surface it. Returns top-5."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Code snippet OR natural-language description.",
            },
            "k": {"type": "integer", "default": 5, "maximum": 10},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}
```

Returns the same `<item>` shape as the auto-injected block, but as a JSON
tool_result rather than embedded XML, so the model parses it as data and can
re-cite items.

**Progressive-disclosure path**:
- The tool's `description` is the always-loaded layer — short.
- `shared/skills/learnings_search.md` documents query-formulation tactics
  ("use code patterns for syntactic matches; use NL for security-pattern
  matches"), loaded by the model on demand exactly like
  `shared/skills/ast_grep.md` is today.

### 7.3 The system-prompt nudge

One line added to `<action_space>` in `shared/prompts.py`:

```
- search_learnings(query): retrieve past maintainer corrections by free-text
  query. The system also auto-injects high-confidence past learnings into the
  user prompt under <past_learnings>; only call this tool if you need more.
```

The explicit "the system also auto-injects" tells the model the auto-block
exists and that the tool is for *gaps*, not duplicate work.

### 7.4 Two-SDK parity for the tool

- **Client SDK**: `search_learnings` is added to the tool list in
  `client_sdk/reviewer.py`. Handler calls
  `shared.learnings.search_tool_handler(query, k)`. ~5 LOC of glue.
- **Agent SDK**: `search_learnings` is added to the in-process MCP server
  alongside `build_review_context` and `submit_findings`. Same handler body,
  MCP-wrapped.

Third axis on the comparison story (after ODIS-as-tool and submit_findings)
where each SDK registers a custom tool through different surfaces.

## 8. Error handling

The learnings layer is **strictly additive**. Any failure must NOT prevent the
reviewer from completing a review. Tests assert this — a fixture run with
`QDRANT_URL=http://broken.invalid` must still produce the same
`submit_findings` output as today's baseline.

### 8.1 Capture pipeline (fail-open, never lose state)

| Failure | Behavior |
|---|---|
| Malformed `@mention` (regex doesn't match) | Skip silently, advance cursor |
| AST chunker can't find enclosing unit (e.g. comment on a blank line) | Log warning, fall back to ±50-line window for *this one* learning, store with `chunk_kind="fallback_window"`. Advance cursor |
| Source file not in checkout (rare — comment on deleted file) | Log warning, skip, advance cursor |
| Voyage rate limit / 5xx | Exponential backoff (1s, 2s, 4s, 8s); after 4 retries, requeue (do NOT advance cursor — retry next loop iteration) |
| Qdrant upsert failure | Same — backoff + requeue |
| GitHub API rate limit | Honor `Retry-After` header; sleep + resume |
| Daemon process crash | Cursor on disk; restart picks up where it left off |

### 8.2 Review pipeline (fail-open, never block the reviewer)

| Failure | Behavior |
|---|---|
| Qdrant unreachable during `retrieve_for_diff` | Log, return empty hits. Reviewer runs without `<past_learnings>` block |
| Voyage embed failure on query | Same — log + skip |
| Applicability filter (Haiku) failure | Skip filter; pass through threshold-only results |
| `search_learnings` tool call fails | Return `{"error": "...", "results": []}` to model. Model continues |
| AST parsing failure on a changed file | Skip that file's contribution to query chunks; continue with others |

## 9. Testing strategy

Three tiers, all using the same Qdrant Cloud cluster (per user direction — no
in-memory or local Qdrant). Test isolation via collection naming.

### 9.1 Unit tests (mocked external services, free, fast — runs in CI)

- `extractor.py`: regex matches/non-matches across a fixture set of comment
  bodies (including multi-line, missing call-word, wrong handle case,
  edge whitespace).
- `ast_chunker.py`: line-range → expected enclosing AST unit on small Python
  fixtures. Both directions: `chunk_for_anchor` and `chunks_for_diff`.
- `state.py`: cursor advance/persist/load.
- `qdrant_store.py`: against real Qdrant Cloud, but using a test collection
  prefixed `test__unit__<random_suffix>`. Test creates collection in
  `setUp`, drops it in `tearDown`. Cost: zero (free tier handles it).
- `voyage_client.py`: mocked — assert request shape, no real API call.
- `format_for_prompt.py`: golden-file XML output from synthetic hits.

### 9.2 Integration tests (live Voyage + live Qdrant Cloud, gated behind `--live` flag)

- One end-to-end capture test: ingest a known synthetic mention into a
  test collection, assert it round-trips (vector retrievable, payload intact).
- One end-to-end retrieve test: pre-seed a known learning, run review on a
  fixture diff that should match, assert the learning surfaces in the prompt
  section.
- Test collections prefixed `test__integration__<run_id>` for isolation;
  teardown drops them.

### 9.3 Regression (the existing fixture suite, full)

- `scripts/run_suite.py --sdk client` and `--sdk agent` must still pass the
  7-fixture baselines. With the learnings layer attached but no learnings in
  the store, the reviewer should produce identical findings to today's
  baseline (the layer is no-op-able).
- With a few hand-seeded learnings targeted at the known-miss fixtures
  (`sentry_67876` CSRF, `sentry_95633` Python-3.13 API), hits per fixture
  should be **≥** today's hits. This is the headline pitch number.

## 10. Tunable parameters

Configurable via env vars or CLI flags. Initial values are defensible defaults;
all subject to recalibration after first real-data run.

| Parameter | Default | Notes |
|---|---|---|
| `LEARNINGS_THRESHOLD` | `0.78` | Cosine similarity floor for surfacing |
| `LEARNINGS_TOP_K` | `5` | Max items in `<past_learnings>` block |
| `LEARNINGS_PER_QUERY_K` | `5` | Top-K returned per AST-unit query |
| `LEARNINGS_FILTER` | `1` | Applicability filter on (1) or off (0) |
| `LEARNINGS_INTERVAL` | `60` | Daemon poll interval, seconds |
| `LEARNINGS_HANDLE` | `@Working-Ant` | Configurable bot handle |
| `LEARNINGS_CALL_WORDS` | `learn,remember,note,teach` | Comma-separated |
| `VOYAGE_API_KEY` | (env) | Required, loaded from `.env` |
| `QDRANT_URL` | (env) | Required, loaded from `.env` |
| `QDRANT_API_KEY` | (env) | Required, loaded from `.env` |

All thresholds will be logged on every retrieval so we can recalibrate after
the first sweep against real data.

## 11. Demo flow

Single command from a clean checkout (post-Phase-5):

```bash
# Setup, one-time
cp .env.example .env  # user fills in 3 keys: ANTHROPIC, VOYAGE, QDRANT
uv sync

# The demo
python scripts/demo.py --repo owner/test-repo --pr 42

# Scene 1 (live):
#   - launcher starts capture daemon (background subprocess)
#   - launcher runs reviewer on PR 42 → reviewer surfaces no learnings yet
#   - reviewer's comment posts to GitHub via Phase 5
#
# (presenter switches to GitHub UI)
#   - presenter goes to the PR, finds a line, leaves a review comment:
#     "@Working-Ant learn: in this codebase always use X instead of Y"
#   - within ~60s, daemon picks up the mention, embeds, stores
#     (presenter shows Qdrant Cloud console — point appears)
#
# Scene 2 (live, in a second terminal — original launcher still running):
#   python scripts/demo.py --pr 42 --rerun
#   - --rerun mode: assumes a daemon is already alive elsewhere; runs only
#     the reviewer half against the same PR. The newly-captured learning
#     surfaces in <past_learnings>.
#   - reviewer's new comment cites the learning.
#
# Ctrl-C in the original terminal → daemon + first reviewer shut down.
```

The pitch graphic is a **before/after diff of the reviewer's output** on the
same PR — first run with empty learnings, second run after one mention
captured. Same model, same prompt scaffolding, different output. That is the
load-bearing slide.

## 12. Implementation sequence (Phase-5-aware)

| # | Step | Depends on Phase 5? | Can start now? |
|---|---|---|---|
| 1 | `learnings/voyage_client.py` + `qdrant_store.py` + bootstrap | No | Yes |
| 2 | `learnings/ast_chunker.py` (capture-side: `chunk_for_anchor`) + tests | No | Yes |
| 3 | `learnings/extractor.py` + tests | No | Yes |
| 4 | `shared/learnings.py` retrieve + format + applicability filter + tool handler | No | Yes |
| 5 | `learnings/ast_chunker.py` query-side (`chunks_for_diff`, post-diff parsing) | Indirect (uses ODIS, already exists) | Yes |
| 6 | Reviewer integration on both SDKs | No | Yes |
| 7 | Contribute `list_open_prs` + `list_pr_review_comments` + `Comment` dataclass to `github/pr_fetch.py` | **Yes** | Stub now, real after P5 lands |
| 8 | `learnings/github_adapter.py` (Phase-5-shaped facade) | Yes (uses 7) | Stub now |
| 9 | `learnings/capture.py` daemon glue | Yes (uses 8) | Stub now |
| 10 | `scripts/demo.py` launcher | Yes (uses 9) | Stub now |
| 11 | Integration test against real PR | Yes | After P5 lands |

**Interim milestone**: steps 1–6 ship a fully testable retrieval layer
attached to both reviewers, validated against hand-seeded learnings in
Qdrant. This proves the load-bearing pitch slide (before/after on a fixture
diff with seeded learnings) before Phase 5 ships.

## 13. Open follow-ups

- **Phase-4 (Daytona) coordination.** §5.1 reuses Phase 5's
  `repo_setup.setup_pr_repo` for cloning at capture time. Phase 5's spec
  notes that Phase 4 will eventually replace the clone path entirely. When
  Phase 4 lands, the capture pipeline's clone call may need to swap to the
  Daytona-backed equivalent. Anchor: a single function in `github_adapter.py`,
  trivial swap.
- **Phase 5 contribution acceptance.** Step 7 contributes
  `list_open_prs` + `list_pr_review_comments` + `Comment` dataclass to
  `github/pr_fetch.py`. If Phase 5 prefers these in a separate file (e.g.
  `github/pr_comments.py`), that's a coordination call, not a design change.
- **Threshold recalibration.** 0.78 is a defensible default; the first real
  data run logs all retrieval scores. After the first sweep, pick the
  threshold from the precision/recall curve at K=5.
- **Reply-to-bot-comment trigger** (CodeRabbit's other capture mechanism).
  Future extension; trivial to add as a second extractor that infers anchor
  from the parent comment's anchor.
- **Multi-language support.** Python-only for v1 (matches the rest of the
  project's scope). Adding TypeScript / Go / etc. requires (a) language-
  specific ast-grep patterns in `ast_chunker.py`, (b) a `language` field
  on the chunker output. No data-shape changes.
- **Learnings garbage collection.** No expiry / pruning in v1. Free-tier
  Qdrant is plenty for demo scale; add a manual `prune` command if a
  collection grows past, say, 10k points.
- **Multi-repo daemon.** v1 daemon polls one repo at a time per launch.
  Watching N repos = launching N daemons. If this becomes annoying, add a
  `--repos` list arg with round-robin polling.
- **Cross-collection search.** v1 searches only the per-repo collection.
  No cross-pollination by design (a Bun-codebase learning shouldn't leak
  into a Sentry review). Revisit only if a clear cross-org pattern emerges.

## 14. Working agreement

- Each new file ≤ 200 LOC. If a file approaches the limit during
  implementation, split it; don't justify exceeding the rule.
- Comments explain *why*, not *what*.
- ASCII for diagrams. No emoji.
- Plain Python. No LangChain. Vector-DB-as-library (qdrant-client), not
  vector-DB-as-framework.
- All credentials loaded from `.env` at the worktree root via
  `python-dotenv`. No hardcoded keys, no per-module env lookups.
- Stacked PR consolidation per the project's standard (one merge per phase).
- CR triage SOP at `.claude/agents/coderabbit-triage.md`: Critical/Major
  fix in-PR, nits reply-only.
