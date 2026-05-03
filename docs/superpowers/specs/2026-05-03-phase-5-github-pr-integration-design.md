# Phase 5 — GitHub PR Integration (live-demo edition)

**Status:** Design approved 2026-05-03 (brainstorming session). Ready for implementation planning.
**Owner:** Hendrik Krack (`Hendrik040`)
**Branch target:** new branch off `main`, parallel to the in-flight Phase 4 (Daytona) work.

## 1. Purpose

Build a one-shot CLI that takes a GitHub PR URL, runs the Agent SDK reviewer
against the PR locally, and posts the findings back as a single GitHub Pull
Request Review with N inline comments + a summary body. The primary use is a
**live pitch demo**: hand the agent a real PR, watch it produce real on-target
in-line comments. Production hardening (GH Actions trigger, webhooks, dedupe
on re-run, multi-tenant auth) is **explicitly out of scope** — we ship enough
to make the live demo land cleanly and to be re-run repeatably during
rehearsal.

## 2. Goals and non-goals

**Goals**
- One CLI command end-to-end: PR URL in, posted review URL out.
- Use the existing Agent SDK reviewer (`agent_sdk/reviewer.py`) **unchanged** —
  Phase 5 is a wrapper, not a modification.
- Findings render as inline review comments anchored to file + line/range,
  matching the visual style already prototyped in `github/review_body.py`.
- Findings whose `file:line` falls outside the PR's diff hunks are preserved
  in a CodeRabbit-style "Outside diff range comments" block in the review
  summary, never silently dropped.
- Re-running on the same PR appends a new versioned review (`Run #NNN`
  header) so rehearsal history is visible in the PR.
- Each module ≤ 200 LOC. Five small modules, one CLI script.

**Non-goals**
- Not a production reviewer service. No GH Actions trigger, no webhook server,
  no multi-PR scheduler.
- No dedupe/dismiss-prior-reviews on re-run (we explicitly want append +
  versioning).
- No SDK selection — Agent SDK at `effort="xhigh"` only. Client SDK / `--sdk`
  flag deferred to a later phase.
- No clone caching. Fresh clone into a temp dir per run; the parallel
  Phase 4 (Daytona) work will replace the clone path entirely. Phase 5 must
  not invent a cache that Phase 4 throws away.
- No demo PR composition tooling. The user supplies multi-bug demo PRs
  separately.
- No GitLab / Bitbucket support. GitHub only.
- No MCP server. CLI only — operators (and any future shelling-out agent)
  invoke it directly.

## 3. Architecture

```
                        +------------------------------+
                        |  scripts/github/review_pr.py |   CLI entry point
                        |  (orchestrator)              |   one operator command
                        +--------------+---------------+
                                       |
            +--------------------------+-------------------------+
            v                          v                         v
   +----------------+         +----------------+        +-----------------+
   | pr_fetch.py    |         | repo_setup.py  |        | trace_extract.py|
   |  gh api wrap   |         |  git clone +   |        |  trace.txt ->   |
   |  - PR metadata |         |  checkout PR   |        |  trail bullets  |
   |  - diff hunks  |         |  to temp dir   |        |  (operator      |
   |    per file    |         |  (Daytona seam)|        |   language)     |
   +--------+-------+         +--------+-------+        +--------+--------+
            |                          |                         |
            +--------------+-----------+-------------------------+
                           v                                     |
                +----------------------+                         |
                | agent_sdk/reviewer   |   already exists        |
                |   .run(repo_path,    |   (Phase 2.1+2.2)       |
                |   base_ref,head_ref) |   Agent SDK xhigh       |
                +----------+-----------+                         |
                           | list[Finding]                       |
                           v                                     |
                +----------------------+                         |
                | post_review.py       | <-----------------------+
                |  - per Finding,      |           trail bullets
                |    classify in/out   |
                |    of diff           |
                |  - build review:     |
                |    inline comments + |
                |    summary body      |
                |  - POST atomically   |
                |    via REST API      |
                +----------+-----------+
                           | uses
                           v
                +----------------------+
                | review_body.py       |  (exists, gets the
                |  render Finding ->   |   tightening change)
                |  markdown            |
                +----------------------+
```

**Single-command flow:**

```
$ uv run python scripts/github/review_pr.py https://github.com/Hendrik040/sentry/pull/1
[1/4] Fetching PR Hendrik040/sentry#1 ... base=abc12 head=def34, 12 files changed
[2/4] Cloning Hendrik040/sentry into /tmp/.../sentry-pr1 ... (this takes a minute)
[3/4] Running Agent SDK reviewer (effort=xhigh) ... 19 turns, $1.30, 4 findings
[4/4] Posting review (Run #042) ... 3 inline + 1 outside-diff
        https://github.com/Hendrik040/sentry/pull/1#pullrequestreview-555
```

**Architectural properties:**

- **Single responsibility per module.** Each module has one job and is
  independently testable.
- **Reviewer is untouched.** Phase 5 wraps `agent_sdk/reviewer.py:run`,
  doesn't modify it.
- **Three explicit seams for future phases:**
  - `repo_setup.py` — Phase 4 Daytona swap (same `setup_pr_repo(pr) -> RepoState`
    interface, sandbox-backed path).
  - `post_review.py` — alternate Git hosts.
  - `trace_extract.py` — richer trails for Phase 6 diary integration.
- **Auth is segregated.** Read-side via `gh` CLI (uses ambient `gh auth`).
  Write-side via `requests` + `GITHUB_REVIEW_BOT_TOKEN` (Working-Ant
  identity). Avoids the awkward `gh api -F comments[]=...` form for
  batched inline comments and gives us atomic submission.

## 4. Components

Five new/modified modules + one CLI script. None exceed ~150 LOC.

### `github/pr_fetch.py` (~80 LOC) — read-side GitHub

```python
@dataclass(frozen=True)
class PullRequest:
    owner: str; repo: str; number: int
    base_sha: str; head_sha: str
    title: str; html_url: str

@dataclass(frozen=True)
class Hunk:
    start_line: int; end_line: int; side: str  # always "RIGHT" for v1

def fetch_pr(pr_url: str) -> PullRequest: ...
def fetch_diff_hunks(owner: str, repo: str, pr_number: int) -> dict[str, list[Hunk]]: ...
```

`fetch_diff_hunks` parses the `patch` field in each entry from
`pulls/{n}/files` to extract added-line ranges. These are what
`post_review.py` checks findings against to decide inline-vs-orphan.
Pagination follows the same `_gh_json_paginated` pattern already used in
`scripts/build_pr_fixture.py`.

### `github/repo_setup.py` (~60 LOC) — code on disk

```python
@dataclass(frozen=True)
class RepoState:
    path: Path; base_ref: str; head_ref: str

@contextmanager
def setup_pr_repo(pr: PullRequest) -> Iterator[RepoState]:
    # git clone https://github.com/{pr.owner}/{pr.repo}.git into a tempdir
    # git fetch origin pull/{pr.number}/head:pr-{n}
    # git checkout pr-{n}
    # yield RepoState(path=tmpdir, base_ref=pr.base_sha, head_ref=pr.head_sha)
    # cleanup tmpdir on exit (including KeyboardInterrupt)
```

Context-managed so the temp dir is always cleaned up. `git clone` over HTTPS
is fine for the public Sentry fork. **This is the Phase-4 Daytona seam** —
same interface, sandbox path later.

### `github/trace_extract.py` (~100 LOC) — trace -> readable trail

```python
def extract_trail(trace_path: Path, max_bullets: int = 8) -> list[str]: ...
def _describe_tool_call(tool_name: str, args: dict) -> str | None: ...
```

Reads the trace, parses tool calls, applies the friendly-name mapping table
below, dedupes consecutive duplicates, caps at 8 bullets. The mapping table
is the **only place internal tool names appear** in user-visible output.

| Trace event | Trail bullet |
|---|---|
| `build_review_context` | *"Loaded the PR diff and surrounding context"* |
| `read_file_section src/.../grouptype.py 1 40` | *"Read src/sentry/incidents/grouptype.py (lines 1-40)"* |
| `ast_search 'class StatefulDetectorHandler'` | *"Searched the codebase for the StatefulDetectorHandler class definition"* |
| `grep '@abstractmethod'` | *"Looked for `@abstractmethod` decorators"* |
| `bash 'git diff --stat'` | *"Inspected which files the PR changes"* |
| `submit_findings` | omitted (terminal, not investigation) |

### `github/review_body.py` (modified, ~120 LOC after changes)

Already exists. Two changes per the body-tightening decision.

**Tightened `render_inline_comment(finding)` template:**

```
**{finding.summary}**          <- now phrased as a recommendation, not a noun-phrase headline

`{file}:{line}` · {severity_badge}

{finding.detail}               <- strictly 2-3 sentences (enforced via prompt update)

<details>
<summary>(emoji) Prompt for AI agents</summary>
... (existing block, unchanged) ...
</details>
```

Drops the "Review note | severity" header line. Drops `analysis_trail` from
the inline body — it moves to the review summary. The `analysis_trail`
parameter stays in the signature for API compat; v1 callers pass `()`.

**New: `render_review_summary(run_meta, orphans, trail) -> str`**
Assembles the review's top-level body:
- Run header line:
  `**Run #042** · Agent SDK · effort=xhigh · 2026-05-03 14:32 UTC · 19 turns · $1.30`
- `> [!CAUTION]` block + "Outside diff range comments (N)" details
  (CodeRabbit-style) when there are orphans. Each orphan rendered with
  file:line, summary, detail, and a fenced code-block snippet pulled from
  the cloned repo at +/- 2 lines.
- "Analysis trail" `<details>` block — the consolidated trail.

### `github/post_review.py` (~150 LOC) — GitHub write-side

```python
@dataclass(frozen=True)
class RunMeta:
    run_id: int; sdk: str; effort: str
    timestamp_utc: str             # ISO-8601 in UTC, e.g. "2026-05-03T14:32:00Z"
    num_turns: int; cost_usd: float
    # Display formatting (e.g. "2026-05-03 14:32 UTC") happens in
    # render_review_summary, not at construction time.

def submit_review(
    pr: PullRequest,
    findings: list[Finding],
    hunks: dict[str, list[Hunk]],
    run_meta: RunMeta,
    trail: list[str],
    token: str,
) -> str:                              # returns review URL
    inlines, orphans = _classify(findings, hunks)
    summary_body = render_review_summary(run_meta, orphans, trail)
    payload = {
        "commit_id": pr.head_sha,
        "event": "COMMENT",
        "body": summary_body,
        "comments": [_to_inline_payload(c) for c in inlines],
    }
    # POST /repos/{owner}/{repo}/pulls/{n}/reviews via requests, with token
    return resp_json["html_url"]

def _classify(findings, hunks) -> tuple[list[InlineComment], list[Finding]]: ...
def _to_inline_payload(c: InlineComment) -> dict: ...
```

One REST call posts the review and all inline comments atomically — partial
states are impossible.

**Inline comment payload schema (GH REST API):**
- Single line: `{"path": ..., "line": N, "side": "RIGHT", "body": ...}`
- Multi-line: `{"path": ..., "start_line": N, "start_side": "RIGHT", "line": M, "side": "RIGHT", "body": ...}`

### `scripts/github/review_pr.py` (~80 LOC) — CLI orchestrator

```python
def main():
    args = parse_args()                # pr_url; --dry-run
    pr = pr_fetch.fetch_pr(args.pr_url)
    hunks = pr_fetch.fetch_diff_hunks(pr.owner, pr.repo, pr.number)
    with repo_setup.setup_pr_repo(pr) as repo:
        result = agent_sdk.reviewer.run(
            repo.path, repo.base_ref, repo.head_ref,
        )
    trail = trace_extract.extract_trail(Path(result["trace_path"]))
    run_meta = RunMeta(
        run_id=result["run_id"], sdk="agent", effort="xhigh",
        timestamp_utc=now_iso(), num_turns=result["num_turns"],
        cost_usd=result["cost_usd"],
    )
    if args.dry_run:
        print(post_review.render_payload_for_inspection(
            pr, result["findings"], hunks, run_meta, trail))
        return
    token = os.environ["GITHUB_REVIEW_BOT_TOKEN"]
    url = post_review.submit_review(pr, result["findings"], hunks, run_meta, trail, token)
    print(f"Posted Run #{result['run_id']}: {url}")
```

## 5. Data flow

End-to-end with concrete shapes at each boundary.

1. **CLI parses URL.** `https://github.com/Hendrik040/sentry/pull/1`
   -> `(owner, repo, number)`.
2. **`pr_fetch.fetch_pr`** -> `PullRequest(owner, repo, number, base_sha, head_sha, title, html_url)`.
3. **`pr_fetch.fetch_diff_hunks`** -> `dict[file_path, list[Hunk]]` from
   parsed `@@ -X,N +Y,M @@` headers.
4. **`repo_setup.setup_pr_repo`** -> `RepoState(path, base_ref=pr.base_sha, head_ref=pr.head_sha)`.
5. **Reviewer call** (unchanged) -> `result` dict with `findings`,
   `trace_path`, `run_id`, `num_turns`, `cost_usd`, etc.
6. **`trace_extract.extract_trail`** -> `list[str]` (operator-language
   bullets, deduped, capped at 8).
7. **Build `RunMeta`** from result + `datetime.now(UTC)`.
8. **`post_review.submit_review`:**
   - **8a — `_classify`:** partition findings against hunks. A finding is
     inline iff its full `(line .. line_end)` span fits inside one hunk on
     `side=RIGHT`. Otherwise it's an orphan.
   - **8b — Render + assemble:** build summary body + inline comment list,
     POST `{commit_id, event:"COMMENT", body, comments}` to
     `/repos/{owner}/{repo}/pulls/{n}/reviews`.
9. **CLI prints** `Posted Run #042 (4 findings: 3 inline, 1 outside-diff)` +
   review URL.

**Invariants:**
- A finding's GH location is determined by `_classify` alone — no clever
  re-anchoring.
- A finding either appears inline at exactly its `(file, line[-line_end])`,
  or in the outside-diff section verbatim. Never both, never silently
  dropped.
- The single-POST design means the review and all its inline comments are
  atomic.
- The trace, results, and posted review all share `run_id=N`, so
  `agent_sdk/traces/run_NNN.txt`, `agent_sdk/results/run_NNN.txt`, and the
  GH review object are all cross-referenceable.

## 6. Body-tightening prompt change

The body bloat in current findings (paragraph-walls in `Finding.detail`)
comes from the soft cap in `shared/prompts.py`. Two-pronged fix:

1. **Prompt update** in `shared/prompts.py`:
   - `summary` -> 1-line directive recommendation, starts with a verb
     (e.g. *"Implement the abstract methods or keep MetricAlertDetectorHandler
     on the non-stateful base for now."*).
   - `detail` -> exactly 3 sentences. Sentence 1 diagnoses the failure
     mode. Sentence 2 names the concrete trigger or call site. Sentence 3
     ends with a binary fix recommendation. **No diff-walkthroughs in
     prose** — those belong in `suggested_fix`.
2. **Renderer update** in `github/review_body.py`: lead with `**{summary}**`
   as the bold first line; body is `{detail}`. Severity badge moves inline
   next to the file:line anchor.

This is part of Phase 5 (the rendered output is what the demo viewers see),
but it touches `shared/prompts.py` so it must be re-validated against the
fixture suite to confirm no regression in find rate. Plan to re-run the
7-fixture sweep once and update `docs/headtohead.md` if numbers shift.

## 7. Error handling and edge cases

Principle: **fail fast on the cheap stuff (before spending $1+ on a reviewer
run); preserve state on the expensive stuff (so a posting failure never
loses findings).**

### Pre-flight (cheap, before reviewer runs)

| Failure | Detection | Behavior |
|---|---|---|
| `GITHUB_REVIEW_BOT_TOKEN` not set | env var check | exit 2, message points at `.env` |
| `gh` CLI missing or unauthed | `gh auth status` non-zero | exit 2, message points at `gh auth login` |
| Invalid PR URL | regex `^https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$` fails | exit 2, print expected format |
| PR not found / no read access | `gh api` 404 | exit 1, print GH error verbatim |
| Token can't write to repo (Working-Ant not Collaborator) | `gh api -X GET repos/{o}/{r}/collaborators/Working-Ant/permission` < `write` | exit 2, instruct to add Working-Ant as Collaborator |

### Mid-run (reviewer in flight)

| Failure | Detection | Behavior |
|---|---|---|
| Reviewer raises | exception bubbles | exit 1, full traceback, **do not post** an empty review |
| 0 findings returned | `len(findings) == 0` | **still post** a "Run #N — no findings" review (silence is worse than emptiness) |
| `max_turns` hit before submit | `result["exit_reason"] == "max_turns"` and `not result["submitted"]` | post with `> [!WARNING]` header noting the truncation |

### Post-time (preserve findings on failure)

| Failure | Detection | Behavior |
|---|---|---|
| Network error / timeout | `requests.RequestException` | print "saved to agent_sdk/results/run_NNN.txt — re-run repost helper to retry"; exit 1 |
| GH 422 on POST | `resp.status_code == 422` | print response body + same "saved to ..." message; exit 1 (common cause: head_sha changed) |
| GH 403 (token revoked) | `resp.status_code == 403` | message about token / Collaborator status; exit 1 |
| GH 5xx | `500 <= status < 600` | retry once after 5s, then fail with "saved to ..." message |

### `_classify` edge cases

| Case | Policy |
|---|---|
| Multi-line range crossing a hunk boundary | orphan (treat as out-of-diff) |
| Reversed bounds (`line_end < line`) | swap defensively, then check normally |
| `line` exceeds file's actual line count at head_sha | orphan, log warning |
| File not in PR's changed-files list | orphan (out-of-diff) |
| Two findings at identical `(file, line, line_end)` | post both — dedup is the reviewer's responsibility, not ours |

### Defensive niceties
- `setup_pr_repo` is a context manager — temp dir cleaned on any exit
  including `KeyboardInterrupt`.
- `extract_trail` returns `[]` on missing/unparseable trace; summary just
  omits the trail block.
- `git clone` runs with a 10-minute timeout for the Sentry-sized case.
- All `subprocess.run` calls use `text=True, check=False` and read return
  codes explicitly — no silent failures.

## 8. Testing strategy

Match the repo's light posture (`scripts/inspect_*.py`, `scripts/*/smoke_*.py`,
sparse `tests/`). No heavyweight pytest suite.

### Unit tests — pure logic only, no network

`tests/test_phase5/`:
- `test_pr_fetch.py` — `_parse_pr_url` regex, `_parse_patch_to_hunks` parser
  (mock `subprocess.run`, sample patch fixtures).
- `test_classify.py` — `_classify` boundary cases from the error table
  (synthesized `Hunk` + `Finding` lists in-test).
- `test_trace_extract.py` — every entry in the friendly-name mapping table;
  `extract_trail` dedup + cap (sample trace at
  `tests/test_phase5/fixtures/sample_trace.txt`).
- `test_review_body.py` — snapshot tests against expected markdown for the
  tightened `render_inline_comment` and `render_review_summary`.

`uv run pytest tests/test_phase5/` should be sub-2-second, zero network,
zero auth.

### Inspect scripts — operator-facing, look at real output without posting

| Script | Purpose |
|---|---|
| `scripts/github/inspect_hunks.py <pr_url>` | Print parsed hunks dict |
| `scripts/github/inspect_trail.py <run_id>` | Read trace, print rendered bullets |
| `scripts/github/inspect_classify.py <pr_url> <result_path>` | Dry-run classification, print inline-vs-orphan with reasons |
| `scripts/github/inspect_render.py <pr_url> <result_path>` | Full dry-run: print the entire would-be review payload as markdown |

`inspect_render.py` is the most-used affordance during demo rehearsal —
iterate prompt + render changes against a real run's findings without
posting.

### Dry-run flag on the main script

`scripts/github/review_pr.py <pr_url> --dry-run` runs everything except the
POST: clone, reviewer call, trace extraction, classification, rendering all
happen; the rendered payload prints to stdout instead of being POSTed. Use
this to confirm the full pipeline before posting.

### Smoke test — one full E2E before demo

`scripts/github/smoke_phase5.py`:
- **Test A** (structural, no network): import every module, confirm
  `GITHUB_REVIEW_BOT_TOKEN` is set, confirm `gh` CLI reachable.
- **Test B** (one real post): run `review_pr.py` against a pre-designated
  *sandbox* PR (separate from the demo PR) on `Hendrik040/sentry`; verify
  `resp.status_code == 200` and a review URL came back; print URL for
  visual verification.

Test A is sub-second. Test B costs ~$1.30 + posts one real review on the
sandbox PR — run before high-stakes rehearsals, not on every code change.

### Out of test scope

- Mocked GH failure modes (422, 5xx). Section 7 codifies the policy; if a
  real failure surfaces during rehearsal, fix the handler then.
- Reviewer correctness on real PRs — Phase 1.8 / Phase 2 territory, already
  covered by `scripts/run_suite.py`. Phase 5 trusts the reviewer.
- Property tests on `_classify` — the space is small; boundary tests cover
  it.

## 9. Open follow-ups (post-Phase-5)

- **Repost helper** (`scripts/github/repost.py run_NNN`) — re-runs only
  step 8 (`post_review`) against an existing local result file. Reserved by
  Section 7 error messages; ship if a posting failure ever bites in a real
  rehearsal.
- **Concurrent runs on the same PR** — if two operators run simultaneously,
  two reviews post with adjacent run numbers. Not breaking, just redundant.
  Out of scope to lock.
- **Webhook / GH Action trigger** — production hardening. Not in scope.
- **`--sdk` flag** for Client SDK demos — once Daytona lands and the demo
  story stabilizes, easy follow-on.
- **Phase 6 hook** — `trace_extract.py` is the natural callsite for emitting
  diary entries on each run. Designed with that future caller in mind.
