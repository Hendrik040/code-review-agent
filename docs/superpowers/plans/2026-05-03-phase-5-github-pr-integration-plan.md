# Phase 5 — GitHub PR Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A one-shot CLI that takes a GitHub PR URL, runs the existing Agent SDK reviewer locally, and posts the findings back as a single GitHub Pull Request Review with N inline comments + a CodeRabbit-style summary block for findings outside the PR diff. Used for the live pitch demo.

**Architecture:** Five small modules under `github/` (each ≤200 LOC), one CLI entry script under `scripts/github/`, four operator-facing inspect scripts, one smoke test. Wraps `agent_sdk/reviewer.py` unchanged. Read-side via `gh` CLI (subprocess), write-side via `httpx` + `GITHUB_REVIEW_BOT_TOKEN`. Posts a single atomic review (one POST, N comments).

**Tech Stack:** Python 3.10+, `httpx` (already a project dep) for HTTP, `gh` CLI for read-side GH API, `pytest` for unit tests, `git` CLI for repo cloning, `claude-agent-sdk` (already installed) via the existing `agent_sdk/reviewer.py`.

**Spec:** `docs/superpowers/specs/2026-05-03-phase-5-github-pr-integration-design.md`

---

## File structure

**Create (5 modules + 6 scripts + 4 test files + 1 fixture):**
- `github/__init__.py` — empty (turns dir into a package)
- `github/pr_fetch.py` — read-side GitHub: PR metadata + diff hunks via `gh api`. Dataclasses: `PullRequest`, `Hunk`. Functions: `fetch_pr`, `fetch_diff_hunks`. ~80 LOC.
- `github/repo_setup.py` — context-managed clone + checkout. Dataclass: `RepoState`. Function: `setup_pr_repo`. ~60 LOC. **The Phase-4 Daytona seam.**
- `github/trace_extract.py` — trace file → friendly trail bullets. Functions: `extract_trail`, `_describe_tool_call`. ~100 LOC. **Only place internal tool names appear.**
- `github/review_body.py` — Markdown rendering. Functions: `render_inline_comment`, `render_review_summary`. ~120 LOC.
- `github/post_review.py` — write-side GitHub: classify in-diff vs orphan, build payload, POST atomically. Dataclasses: `RunMeta`, `InlineComment`. Functions: `submit_review`, `_classify`, `_to_inline_payload`, `render_payload_for_inspection`. ~150 LOC.
- `scripts/github/__init__.py` — empty
- `scripts/github/review_pr.py` — CLI orchestrator. ~80 LOC.
- `scripts/github/inspect_hunks.py` — print parsed hunks for a PR.
- `scripts/github/inspect_trail.py` — print rendered trail for a run.
- `scripts/github/inspect_classify.py` — dry-run classification.
- `scripts/github/inspect_render.py` — full dry-run: print would-be review payload as markdown.
- `scripts/github/smoke_phase5.py` — pre-demo end-to-end smoke test.
- `tests/test_phase5/__init__.py` — empty
- `tests/test_phase5/test_pr_fetch.py`
- `tests/test_phase5/test_classify.py`
- `tests/test_phase5/test_trace_extract.py`
- `tests/test_phase5/test_review_body.py`
- `tests/test_phase5/fixtures/sample_trace.txt` — a checked-in trace excerpt

**Modify:**
- `shared/prompts.py` — body-tightening prompt change (Task 13). Lines depend on what the rebase brings in.

---

## Task 0: Verify prerequisites and rebase onto Phase 2.2

**Context:** The branch was created off `main` (Phase 1), but Phase 5 wraps `agent_sdk/reviewer.py` which lives on `phase-2.2/tool-parity-and-effort`. Rebase first.

**Files:**
- Modify: branch base (rebase only, no file changes)

- [ ] **Step 0.1: Confirm worktree location and branch**

Run:
```bash
pwd                     # expect: /Users/hendrikkrack/Desktop/code-review-agent-phase5
git branch --show-current
```
Expected: `phase-5/github-pr-integration`. If `pwd` differs, `cd /Users/hendrikkrack/Desktop/code-review-agent-phase5` and re-check. Do NOT proceed if either check fails.

- [ ] **Step 0.2: Verify the reviewer module is missing (proves we need the rebase)**

Run: `ls agent_sdk/reviewer.py`
Expected: `ls: cannot access 'agent_sdk/reviewer.py': No such file or directory`

- [ ] **Step 0.3: Rebase onto phase-2.2/tool-parity-and-effort**

Run:
```bash
git fetch
git rebase phase-2.2/tool-parity-and-effort
```
Expected: clean rebase (the only commit on this branch is the spec, which only touches `docs/superpowers/`, no conflicts with Phase 2.2 code). If conflicts, stop and report them — do not improvise resolution.

- [ ] **Step 0.4: Verify rebase brought in the reviewer**

Run:
```bash
ls agent_sdk/reviewer.py
git log --oneline -3
```
Expected: `agent_sdk/reviewer.py` exists. Log shows the spec commit on top of `dd9f851 docs(plan): expand Phase 2 with effort-frontier + harness-stress fixtures` (or whatever Phase 2.2 head is when you run this).

- [ ] **Step 0.5: Verify the reviewer's I/O contract by reading its run() signature**

Run: `grep -A 20 "^def run\|^async def run" agent_sdk/reviewer.py | head -40`

The plan assumes `result["findings"]`, `result["trace_path"]`, `result["run_id"]`, `result["num_turns"]`, `result["cost_usd"]`, `result["exit_reason"]`, `result["submitted"]` keys are present. If the actual signature differs, stop and report — the plan needs an update before continuing.

- [ ] **Step 0.6: Confirm `pyproject.toml` has httpx**

Run: `grep httpx pyproject.toml`
Expected: `"httpx>=0.27.0"` line present. If missing, add it under `dependencies`, run `uv sync`, then continue.

- [ ] **Step 0.7: Create test scaffolding directories**

Run:
```bash
mkdir -p tests/test_phase5/fixtures
touch tests/test_phase5/__init__.py
touch tests/test_phase5/fixtures/.gitkeep
mkdir -p github scripts/github
touch github/__init__.py scripts/github/__init__.py
```

- [ ] **Step 0.8: Verify pytest works in this worktree**

Run: `uv run pytest tests/test_phase5/ -v`
Expected: `no tests ran` (or `collected 0 items`) — confirms pytest is reachable but we have no tests yet. If pytest itself errors out, fix the venv before proceeding.

- [ ] **Step 0.9: Commit scaffolding**

```bash
git add github/__init__.py scripts/github/__init__.py tests/test_phase5/__init__.py tests/test_phase5/fixtures/.gitkeep
git commit -m "phase 5: scaffold github/ + scripts/github/ + tests/test_phase5/ packages"
```

---

## Task 1: `github/pr_fetch.py` — URL parsing and dataclasses

**Files:**
- Create: `github/pr_fetch.py`
- Test: `tests/test_phase5/test_pr_fetch.py`

- [ ] **Step 1.1: Write the failing test for URL parsing**

Create `tests/test_phase5/test_pr_fetch.py`:

```python
"""Unit tests for github.pr_fetch — URL parsing + dataclasses (Task 1)."""

from __future__ import annotations

import pytest

from github.pr_fetch import PullRequest, Hunk, _parse_pr_url


class TestParsePrUrl:
    def test_https_basic(self):
        assert _parse_pr_url("https://github.com/Hendrik040/sentry/pull/1") == (
            "Hendrik040", "sentry", 1
        )

    def test_https_with_trailing_slash(self):
        assert _parse_pr_url("https://github.com/owner/repo/pull/42/") == (
            "owner", "repo", 42
        )

    def test_http_is_accepted(self):
        assert _parse_pr_url("http://github.com/o/r/pull/7") == ("o", "r", 7)

    def test_rejects_non_pull_url(self):
        with pytest.raises(ValueError, match="not a GitHub PR URL"):
            _parse_pr_url("https://github.com/owner/repo/issues/1")

    def test_rejects_non_github_host(self):
        with pytest.raises(ValueError, match="not a GitHub PR URL"):
            _parse_pr_url("https://gitlab.com/owner/repo/pull/1")

    def test_rejects_garbage(self):
        with pytest.raises(ValueError, match="not a GitHub PR URL"):
            _parse_pr_url("not a url")


class TestDataclasses:
    def test_pullrequest_is_frozen(self):
        pr = PullRequest(
            owner="o", repo="r", number=1,
            base_sha="a", head_sha="b",
            title="t", html_url="u",
        )
        with pytest.raises(Exception):
            pr.owner = "x"  # frozen dataclass

    def test_hunk_is_frozen(self):
        h = Hunk(start_line=1, end_line=10, side="RIGHT")
        with pytest.raises(Exception):
            h.start_line = 99
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `uv run pytest tests/test_phase5/test_pr_fetch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'github.pr_fetch'`.

- [ ] **Step 1.3: Implement minimal pr_fetch with dataclasses + URL parser**

Create `github/pr_fetch.py`:

```python
"""Read-side GitHub: PR metadata + diff hunks via the `gh` CLI.

Used by scripts/github/review_pr.py and the inspect_* helpers. Wraps
`gh api` calls (no token in process; auth is via the user's `gh auth`
state). Write-side posting lives in github/post_review.py and uses a
separate token (GITHUB_REVIEW_BOT_TOKEN).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# https://github.com/<owner>/<repo>/pull/<n>(/)
_PR_URL_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$"
)


@dataclass(frozen=True)
class PullRequest:
    owner: str
    repo: str
    number: int
    base_sha: str
    head_sha: str
    title: str
    html_url: str


@dataclass(frozen=True)
class Hunk:
    """An added-line range in a PR file's diff. side is always 'RIGHT'
    for v1 — we only comment on new code, never on the deleted side."""
    start_line: int
    end_line: int
    side: str


def _parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    m = _PR_URL_RE.match(pr_url.strip())
    if not m:
        raise ValueError(
            f"not a GitHub PR URL: {pr_url!r} "
            "(expected https://github.com/<owner>/<repo>/pull/<n>)"
        )
    owner, repo, number = m.group(1), m.group(2), int(m.group(3))
    return owner, repo, number
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `uv run pytest tests/test_phase5/test_pr_fetch.py -v`
Expected: 8 tests pass.

- [ ] **Step 1.5: Commit**

```bash
git add github/pr_fetch.py tests/test_phase5/test_pr_fetch.py
git commit -m "phase 5: pr_fetch — URL parser + PullRequest/Hunk dataclasses"
```

---

## Task 2: `github/pr_fetch.py` — diff hunk parser

The `gh api repos/.../pulls/{n}/files` response gives us each file's `patch` string in unified-diff format. We need to extract added-line ranges (`@@ -X,N +Y,M @@` headers) so post_review.py can decide which findings can be posted inline.

**Files:**
- Modify: `github/pr_fetch.py`
- Test: `tests/test_phase5/test_pr_fetch.py`

- [ ] **Step 2.1: Add failing tests for the hunk parser**

Append to `tests/test_phase5/test_pr_fetch.py`:

```python
from github.pr_fetch import _parse_patch_to_hunks


class TestParsePatchToHunks:
    def test_single_hunk(self):
        # +Y,M means: starting at NEW line Y, M new lines are added/context
        patch = "@@ -10,3 +10,5 @@\n context\n+added 1\n+added 2\n context\n context"
        assert _parse_patch_to_hunks(patch) == [Hunk(10, 14, "RIGHT")]

    def test_multiple_hunks(self):
        patch = (
            "@@ -1,3 +1,3 @@\n unchanged\n unchanged\n unchanged\n"
            "@@ -100,2 +120,4 @@\n line\n+a\n+b\n line"
        )
        assert _parse_patch_to_hunks(patch) == [
            Hunk(1, 3, "RIGHT"),
            Hunk(120, 123, "RIGHT"),
        ]

    def test_pure_addition_at_start(self):
        # New file: -0,0 means no prior lines; +1,N means N added lines
        patch = "@@ -0,0 +1,3 @@\n+a\n+b\n+c"
        assert _parse_patch_to_hunks(patch) == [Hunk(1, 3, "RIGHT")]

    def test_omits_zero_length_added(self):
        # Pure deletion: +Y,0 means no added lines on the new side
        patch = "@@ -10,2 +10,0 @@\n-removed 1\n-removed 2"
        # Nothing to comment on RIGHT side — no hunks emitted.
        assert _parse_patch_to_hunks(patch) == []

    def test_empty_patch(self):
        assert _parse_patch_to_hunks("") == []

    def test_single_added_line_default_count(self):
        # @@ -X +Y @@ form (no comma, count defaults to 1)
        patch = "@@ -5 +5 @@\n unchanged"
        assert _parse_patch_to_hunks(patch) == [Hunk(5, 5, "RIGHT")]
```

- [ ] **Step 2.2: Run tests to verify they fail**

Run: `uv run pytest tests/test_phase5/test_pr_fetch.py::TestParsePatchToHunks -v`
Expected: FAIL with `ImportError: cannot import name '_parse_patch_to_hunks'`.

- [ ] **Step 2.3: Implement the patch parser**

Append to `github/pr_fetch.py`:

```python
# Hunk header: @@ -<old_start>[,<old_count>] +<new_start>[,<new_count>] @@
# We only care about the +<new_start>,<new_count> portion (the RIGHT side).
_HUNK_HEADER_RE = re.compile(
    r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@"
)


def _parse_patch_to_hunks(patch: str) -> list[Hunk]:
    """Extract added-line ranges from a unified-diff patch string.

    Returns one Hunk per `@@ ... @@` header that has a non-zero new-side
    count. Zero-count headers (pure deletions) are omitted — there's
    nothing on the RIGHT side to comment on.
    """
    hunks: list[Hunk] = []
    for line in patch.splitlines():
        m = _HUNK_HEADER_RE.match(line)
        if not m:
            continue
        new_start = int(m.group(1))
        new_count = int(m.group(2)) if m.group(2) is not None else 1
        if new_count == 0:
            continue  # pure deletion, nothing to anchor a comment to
        hunks.append(Hunk(new_start, new_start + new_count - 1, "RIGHT"))
    return hunks
```

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `uv run pytest tests/test_phase5/test_pr_fetch.py -v`
Expected: 14 tests pass (6 new + 8 existing).

- [ ] **Step 2.5: Commit**

```bash
git add github/pr_fetch.py tests/test_phase5/test_pr_fetch.py
git commit -m "phase 5: pr_fetch — _parse_patch_to_hunks for diff @@ headers"
```

---

## Task 3: `github/pr_fetch.py` — gh-api wrappers (`fetch_pr`, `fetch_diff_hunks`)

Now wrap the actual subprocess calls to `gh api`. Pattern is already established in `scripts/build_pr_fixture.py`; reuse the `_gh_json` and `_gh_json_paginated` helpers conceptually (but keep them local to this module — no shared utility yet).

**Files:**
- Modify: `github/pr_fetch.py`
- Test: `tests/test_phase5/test_pr_fetch.py`

- [ ] **Step 3.1: Add failing tests with mocked subprocess**

Append to `tests/test_phase5/test_pr_fetch.py`:

```python
import json
from unittest.mock import patch as mock_patch, MagicMock

from github.pr_fetch import fetch_pr, fetch_diff_hunks


class TestFetchPr:
    def test_returns_pullrequest_from_gh_api(self):
        gh_response = json.dumps({
            "base": {"sha": "abc123"},
            "head": {"sha": "def456"},
            "title": "Demo: recreate sentry#80168",
            "html_url": "https://github.com/Hendrik040/sentry/pull/1",
        })
        with mock_patch("github.pr_fetch.subprocess.check_output") as run:
            run.return_value = gh_response
            pr = fetch_pr("https://github.com/Hendrik040/sentry/pull/1")
        assert pr == PullRequest(
            owner="Hendrik040", repo="sentry", number=1,
            base_sha="abc123", head_sha="def456",
            title="Demo: recreate sentry#80168",
            html_url="https://github.com/Hendrik040/sentry/pull/1",
        )
        # Verify the gh CLI was called with the right endpoint
        cmd = run.call_args[0][0]
        assert cmd[:2] == ["gh", "api"]
        assert cmd[2] == "repos/Hendrik040/sentry/pulls/1"


class TestFetchDiffHunks:
    def test_aggregates_hunks_per_file(self):
        # gh api --paginate --slurp wraps the response in an outer list (one entry per page)
        page = [
            {"filename": "a.py", "patch": "@@ -1,2 +1,3 @@\n line\n+added\n line"},
            {"filename": "b.py", "patch": "@@ -10,2 +10,0 @@\n-x\n-y"},  # pure deletion
            {"filename": "c.py", "patch": None},  # binary or no patch
        ]
        gh_response = json.dumps([page])
        with mock_patch("github.pr_fetch.subprocess.check_output") as run:
            run.return_value = gh_response
            hunks = fetch_diff_hunks("Hendrik040", "sentry", 1)
        assert hunks == {
            "a.py": [Hunk(1, 3, "RIGHT")],
            # b.py omitted (no RIGHT-side lines)
            # c.py omitted (no patch)
        }
        cmd = run.call_args[0][0]
        assert cmd[:4] == ["gh", "api", "--paginate", "--slurp"]
        assert cmd[4] == "repos/Hendrik040/sentry/pulls/1/files"
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `uv run pytest tests/test_phase5/test_pr_fetch.py::TestFetchPr tests/test_phase5/test_pr_fetch.py::TestFetchDiffHunks -v`
Expected: FAIL with `ImportError: cannot import name 'fetch_pr'`.

- [ ] **Step 3.3: Implement the gh-api wrappers**

Append to `github/pr_fetch.py`:

```python
import json
import subprocess
from typing import Any


def _gh_json(endpoint: str) -> Any:
    """Invoke `gh api <endpoint>` and parse stdout as JSON."""
    out = subprocess.check_output(["gh", "api", endpoint], text=True)
    return json.loads(out)


def _gh_json_paginated(endpoint: str) -> list[Any]:
    """Invoke `gh api --paginate --slurp <endpoint>` and flatten the
    list-of-pages response into a single list. Plain `_gh_json` returns
    only the first page (~30 items by default); large PRs lose files
    silently without paginate."""
    out = subprocess.check_output(
        ["gh", "api", "--paginate", "--slurp", endpoint], text=True
    )
    pages = json.loads(out)
    flat: list[Any] = []
    for page in pages:
        flat.extend(page)
    return flat


def fetch_pr(pr_url: str) -> PullRequest:
    """Parse the PR URL and fetch metadata via `gh api`."""
    owner, repo, number = _parse_pr_url(pr_url)
    data = _gh_json(f"repos/{owner}/{repo}/pulls/{number}")
    return PullRequest(
        owner=owner,
        repo=repo,
        number=number,
        base_sha=data["base"]["sha"],
        head_sha=data["head"]["sha"],
        title=data["title"],
        html_url=data["html_url"],
    )


def fetch_diff_hunks(
    owner: str, repo: str, pr_number: int
) -> dict[str, list[Hunk]]:
    """Fetch the PR's changed-file list and parse each file's patch into
    Hunk ranges. Files with no RIGHT-side content (pure deletions, binary
    files without a patch) are omitted from the result."""
    files = _gh_json_paginated(f"repos/{owner}/{repo}/pulls/{pr_number}/files")
    out: dict[str, list[Hunk]] = {}
    for entry in files:
        patch = entry.get("patch") or ""
        hunks = _parse_patch_to_hunks(patch)
        if hunks:
            out[entry["filename"]] = hunks
    return out
```

- [ ] **Step 3.4: Run tests to verify all pr_fetch tests pass**

Run: `uv run pytest tests/test_phase5/test_pr_fetch.py -v`
Expected: 16 tests pass.

- [ ] **Step 3.5: Commit**

```bash
git add github/pr_fetch.py tests/test_phase5/test_pr_fetch.py
git commit -m "phase 5: pr_fetch — fetch_pr + fetch_diff_hunks via gh api"
```

---

## Task 4: `github/repo_setup.py` — context-managed clone + checkout

The Phase-4 Daytona seam: same `setup_pr_repo(pr) -> RepoState` interface, sandbox-backed path swap later. For now, just `git clone` over HTTPS into a tempdir, fetch the PR ref, checkout, yield, cleanup.

**Files:**
- Create: `github/repo_setup.py`
- Test: none for this task — the heavy lifting is `git clone` against a real network, which we exercise via the inspect/smoke scripts later. The dataclass + signature are simple enough.

- [ ] **Step 4.1: Implement repo_setup.py**

Create `github/repo_setup.py`:

```python
"""Get the PR's code on disk for the reviewer to read.

This module is the **Phase-4 Daytona seam**: same `setup_pr_repo(pr) ->
RepoState` interface; the local-tempdir backend is replaced with a Daytona
sandbox in Phase 4. Reviewer code (`agent_sdk/reviewer.py`) doesn't notice.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from github.pr_fetch import PullRequest

# Sentry-sized clones can take 1-3 minutes. Cap so a hung network gives up.
CLONE_TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class RepoState:
    path: Path        # tmpdir root containing the cloned repo
    base_ref: str     # base SHA from the PR (passed to reviewer.run)
    head_ref: str     # head SHA from the PR


@contextmanager
def setup_pr_repo(pr: PullRequest) -> Iterator[RepoState]:
    """Clone the PR's repo into a tempdir, check out the PR head, yield.

    Cleanup runs on any exit path including KeyboardInterrupt.
    Public-fork clones use HTTPS without a token (Sentry fork is public).
    For private repos this would need the token in the URL — out of scope
    for v1.
    """
    tmp = Path(tempfile.mkdtemp(prefix=f"cra-{pr.repo}-pr{pr.number}-"))
    try:
        clone_url = f"https://github.com/{pr.owner}/{pr.repo}.git"
        repo_dir = tmp / pr.repo
        # `text=True, check=True` so any non-zero exit raises CalledProcessError
        # with stderr captured for the operator.
        subprocess.run(
            ["git", "clone", "--quiet", clone_url, str(repo_dir)],
            text=True, check=True, timeout=CLONE_TIMEOUT_SECONDS,
        )
        # Fetch the PR ref into a local branch and check it out.
        subprocess.run(
            ["git", "-C", str(repo_dir), "fetch", "origin",
             f"pull/{pr.number}/head:pr-{pr.number}"],
            text=True, check=True, timeout=CLONE_TIMEOUT_SECONDS,
        )
        subprocess.run(
            ["git", "-C", str(repo_dir), "checkout", "--quiet",
             f"pr-{pr.number}"],
            text=True, check=True, timeout=60,
        )
        yield RepoState(path=repo_dir, base_ref=pr.base_sha, head_ref=pr.head_sha)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
```

- [ ] **Step 4.2: Smoke-check the module imports cleanly**

Run: `uv run python -c "from github.repo_setup import setup_pr_repo, RepoState; print('ok')"`
Expected: `ok`

- [ ] **Step 4.3: Commit**

```bash
git add github/repo_setup.py
git commit -m "phase 5: repo_setup — context-managed clone + PR checkout (Daytona seam)"
```

---

## Task 5: `github/trace_extract.py` — trace → friendly trail bullets

Read the agent's trace file, parse tool-call events, apply the friendly-name mapping table from the spec, dedupe consecutive duplicates, cap at 8 bullets. **The only place internal tool names appear in user-visible output.**

**Files:**
- Create: `github/trace_extract.py`
- Create: `tests/test_phase5/fixtures/sample_trace.txt`
- Test: `tests/test_phase5/test_trace_extract.py`

- [ ] **Step 5.1: First, peek at the actual trace file format we'll be parsing**

Run:
```bash
ls agent_sdk/traces/ | head -3
head -80 agent_sdk/traces/run_026.txt 2>/dev/null || head -80 "$(ls agent_sdk/traces/run_*.txt | tail -1)"
```

Read the format. Trace files are append-only text logs written by the reviewer; each tool call is recorded as a line or block with the tool name and arguments. Verify the format matches what the parser below assumes (`>>> tool_name(args_dict)` or `[tool_use] name=... input=...`). **If the format differs**, adjust the parser regex in step 5.4 before running tests.

- [ ] **Step 5.2: Create the sample trace fixture**

Inspect the actual trace format from step 5.1, then create `tests/test_phase5/fixtures/sample_trace.txt` with a representative excerpt — at minimum enough to exercise these tool calls in this order: `build_review_context`, `read_file_section` (twice with same args, to test dedup), `ast_search`, `grep`, `bash`, `submit_findings`. If you can't isolate a small representative excerpt, copy 50-100 lines from `agent_sdk/traces/run_026.txt`.

- [ ] **Step 5.3: Write the failing tests**

Create `tests/test_phase5/test_trace_extract.py`:

```python
"""Unit tests for github.trace_extract — trace parsing + friendly-name mapping."""

from __future__ import annotations

from pathlib import Path

import pytest

from github.trace_extract import _describe_tool_call, extract_trail

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class TestDescribeToolCall:
    def test_build_review_context(self):
        assert _describe_tool_call("build_review_context", {}) == (
            "Loaded the PR diff and surrounding context"
        )

    def test_read_file_section(self):
        result = _describe_tool_call("read_file_section", {
            "path": "src/sentry/incidents/grouptype.py",
            "start_line": 1, "end_line": 40,
        })
        assert result == "Read src/sentry/incidents/grouptype.py (lines 1-40)"

    def test_ast_search(self):
        result = _describe_tool_call("ast_search", {
            "pattern": "class StatefulDetectorHandler",
        })
        assert result == (
            "Searched the codebase for the StatefulDetectorHandler class definition"
        )

    def test_ast_search_generic_pattern(self):
        # Pattern that doesn't match the "class X" shape: fall back to a
        # generic phrasing instead of inventing structure.
        result = _describe_tool_call("ast_search", {"pattern": "$X.foo($$$)"})
        assert result == "Searched the codebase using a structural pattern"

    def test_grep(self):
        result = _describe_tool_call("grep", {"pattern": "@abstractmethod"})
        assert result == "Looked for `@abstractmethod` in the codebase"

    def test_bash_git_diff(self):
        result = _describe_tool_call("bash", {"command": "git diff --stat"})
        assert result == "Inspected which files the PR changes"

    def test_bash_other(self):
        # Any other bash command: generic phrasing, never echo the command verbatim
        result = _describe_tool_call("bash", {"command": "rm -rf /"})
        assert result == "Ran a shell command on the working tree"

    def test_submit_findings_omitted(self):
        # Terminal call, not part of the investigation
        assert _describe_tool_call("submit_findings", {"findings": []}) is None

    def test_unknown_tool_omitted(self):
        # Defensive: never crash; just skip
        assert _describe_tool_call("totally_made_up", {}) is None


class TestExtractTrail:
    def test_extracts_friendly_bullets_from_sample_trace(self):
        trail = extract_trail(FIXTURE_DIR / "sample_trace.txt")
        assert len(trail) > 0
        # First substantive call should be build_review_context
        assert trail[0] == "Loaded the PR diff and surrounding context"
        # Internal tool names must NEVER appear in the rendered trail
        for bullet in trail:
            for forbidden in ("ast_search", "build_review_context",
                              "read_file_section", "submit_findings",
                              "ODIS"):
                assert forbidden not in bullet, (
                    f"internal name {forbidden!r} leaked into trail: {bullet!r}"
                )

    def test_dedupes_consecutive_duplicates(self):
        # The fixture has two identical read_file_section calls in a row;
        # they should collapse to one bullet.
        trail = extract_trail(FIXTURE_DIR / "sample_trace.txt")
        # No two consecutive bullets are identical
        for prev, nxt in zip(trail, trail[1:]):
            assert prev != nxt, f"duplicate consecutive bullet: {prev!r}"

    def test_caps_at_max_bullets(self):
        trail = extract_trail(FIXTURE_DIR / "sample_trace.txt", max_bullets=3)
        assert len(trail) <= 3

    def test_returns_empty_on_missing_file(self):
        # Defensive: must NEVER raise; the summary just omits the trail block
        assert extract_trail(Path("/nonexistent/trace.txt")) == []

    def test_returns_empty_on_unparseable_file(self, tmp_path):
        f = tmp_path / "garbage.txt"
        f.write_text("this is not a trace at all")
        assert extract_trail(f) == []
```

- [ ] **Step 5.4: Run tests to verify they fail**

Run: `uv run pytest tests/test_phase5/test_trace_extract.py -v`
Expected: FAIL with `ImportError: cannot import name 'extract_trail'`.

- [ ] **Step 5.5: Implement trace_extract.py**

Create `github/trace_extract.py`. **Important**: the regex on line `_TOOL_CALL_RE` below assumes a trace format like `>>> tool_name({...})` or `[tool_use] name=tool_name input={...}`. Adjust it based on what you found in step 5.1. The mapping table and dedup logic are format-independent.

```python
"""Convert an agent trace file into a readable analysis trail.

The mapping table below is THE ONLY PLACE internal tool names like
`build_review_context` or `ast_search` appear in user-visible output.
Trail bullets are what the GitHub review summary shows under "Analysis
trail" — they must read as plain operator language, not jargon.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Trace format: each tool call appears as a line containing a JSON-ish
# fragment with the tool name and its input. This regex captures both.
# REVIEW the actual format in agent_sdk/traces/run_NNN.txt before
# trusting this — adjust the pattern if reality differs.
_TOOL_CALL_RE = re.compile(
    r"\b(?:tool_use|>>>)\s+(?:name=)?(\w+)\s*[\(=]\s*(\{[^\n]*\})"
)


def _describe_tool_call(tool_name: str, args: dict) -> str | None:
    """Map a (tool_name, args) pair to a one-line operator-language bullet.

    Returns None for tool calls we deliberately omit (terminal calls,
    unknown tools). Never raises on bad inputs — defensive.
    """
    if tool_name == "build_review_context":
        return "Loaded the PR diff and surrounding context"

    if tool_name == "read_file_section":
        path = args.get("path", "<unknown>")
        start = args.get("start_line", "?")
        end = args.get("end_line", "?")
        return f"Read {path} (lines {start}-{end})"

    if tool_name == "ast_search":
        pattern = args.get("pattern", "")
        m = re.match(r"class\s+(\w+)", pattern)
        if m:
            return (
                f"Searched the codebase for the {m.group(1)} class definition"
            )
        m = re.match(r"def\s+(\w+)", pattern)
        if m:
            return (
                f"Searched the codebase for the {m.group(1)} function definition"
            )
        return "Searched the codebase using a structural pattern"

    if tool_name == "grep":
        pattern = args.get("pattern", "")
        return f"Looked for `{pattern}` in the codebase"

    if tool_name == "bash":
        cmd = args.get("command", "")
        if cmd.startswith("git diff"):
            return "Inspected which files the PR changes"
        return "Ran a shell command on the working tree"

    if tool_name == "write_file":
        path = args.get("path", "<unknown>")
        return f"Wrote scratch notes to {path}"

    # Terminal calls and unknown tools: omit from the trail.
    return None


def _parse_trace(text: str) -> list[tuple[str, dict]]:
    """Extract (tool_name, args_dict) tuples from the trace text.

    Robust to malformed JSON (skips that entry). Never raises.
    """
    out: list[tuple[str, dict]] = []
    for m in _TOOL_CALL_RE.finditer(text):
        name = m.group(1)
        try:
            args = json.loads(m.group(2))
            if isinstance(args, dict):
                out.append((name, args))
        except (json.JSONDecodeError, TypeError):
            continue  # skip un-parseable entries
    return out


def extract_trail(trace_path: Path, max_bullets: int = 8) -> list[str]:
    """Read a trace file, return up to `max_bullets` friendly bullets.

    Deduplicates consecutive duplicates. Returns [] if the file is
    missing or unparseable — never raises (the caller treats empty
    result as "no trail to show").
    """
    try:
        text = Path(trace_path).read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return []

    bullets: list[str] = []
    for name, args in _parse_trace(text):
        described = _describe_tool_call(name, args)
        if described is None:
            continue
        if bullets and bullets[-1] == described:
            continue  # consecutive dup
        bullets.append(described)
        if len(bullets) >= max_bullets:
            break
    return bullets
```

- [ ] **Step 5.6: Run tests, iterate on the regex if needed**

Run: `uv run pytest tests/test_phase5/test_trace_extract.py -v`
Expected: all tests pass. If `test_extracts_friendly_bullets_from_sample_trace` fails, the trace format regex (`_TOOL_CALL_RE`) doesn't match what's in the fixture. Inspect the fixture, fix the regex, re-run. **Do NOT change the test assertions to match a broken parser** — the assertions reflect the spec; the parser must match the trace.

- [ ] **Step 5.7: Commit**

```bash
git add github/trace_extract.py tests/test_phase5/test_trace_extract.py tests/test_phase5/fixtures/sample_trace.txt
git commit -m "phase 5: trace_extract — friendly-name mapping + extract_trail"
```

---

## Task 6: `github/review_body.py` — `render_inline_comment` (tightened template)

Per the body-tightening decision, the template is restructured: bold one-line `summary` (now phrased as a recommendation), then `file:line` + severity badge inline, then the `detail` paragraph, then the collapsible "Prompt for AI agents" block. Drop the per-comment "Review note | severity" header; drop the `analysis_trail` from the inline body (it moves to the review summary in Task 7).

Reference style: `~/Desktop/code-review-agent/v1/github/review_body.py` is the user's untracked WIP — it has the un-tightened template. Use it for stylistic cues (severity badges, "Prompt for AI agents" block content) but the spec's tightened template is authoritative for structure.

**Files:**
- Create: `github/review_body.py`
- Test: `tests/test_phase5/test_review_body.py`

- [ ] **Step 6.1: Write the failing test**

Create `tests/test_phase5/test_review_body.py`:

```python
"""Snapshot tests for github.review_body — tightened render_inline_comment."""

from __future__ import annotations

from shared.findings import Finding
from github.review_body import render_inline_comment, SEVERITY_BADGES


def test_render_inline_comment_tightened_template():
    f = Finding(
        file="src/sentry/incidents/grouptype.py",
        line=11,
        line_end=12,
        category="contract-mismatch",
        severity="medium",
        summary=(
            "Implement the abstract methods or keep MetricAlertDetectorHandler "
            "on the non-stateful base for now."
        ),
        detail=(
            "StatefulDetectorHandler declares four abstract methods "
            "(counter_names, get_dedupe_value, get_group_key_values, "
            "build_occurrence_and_event_data). Detector.detector_handler "
            "instantiates the subclass at detector.py:86, which now raises "
            "TypeError. Either implement the four methods or revert to the "
            "non-stateful parent class."
        ),
        suggested_fix="",
    )
    out = render_inline_comment(f)

    # Bold summary leads
    assert out.startswith("**Implement the abstract methods")
    # File anchor + severity badge inline (one line, two tokens)
    assert "`src/sentry/incidents/grouptype.py:11-12`" in out
    assert SEVERITY_BADGES["medium"] in out
    # The DROPPED elements must not appear
    assert "Review note" not in out, (
        "old 'Review note | severity' header should be gone"
    )
    # The detail paragraph is present
    assert "StatefulDetectorHandler declares four abstract methods" in out
    # "Prompt for AI agents" collapsible block is present
    assert "<summary>" in out and "Prompt for AI agents" in out


def test_render_inline_comment_single_line_location():
    # When line_end is None or equals line, location renders as `file:line`
    f = Finding(
        file="a.py", line=5, line_end=None,
        category="logic", severity="low",
        summary="Use .get() instead of [].",
        detail="x. y. z.",
        suggested_fix="",
    )
    out = render_inline_comment(f)
    assert "`a.py:5`" in out
    assert "`a.py:5-" not in out


def test_render_inline_comment_severity_badges_used():
    # All three severities must have a badge
    for sev in ("high", "medium", "low"):
        assert sev in SEVERITY_BADGES or sev.title() in str(SEVERITY_BADGES)


def test_render_inline_comment_keeps_analysis_trail_param():
    # Backward-compat: param stays in the signature even if v1 callers
    # pass () (trail moved to review summary). Calling with () must work.
    f = Finding(
        file="a.py", line=1, line_end=None,
        category="other", severity="low",
        summary="x", detail="y", suggested_fix="",
    )
    render_inline_comment(f, analysis_trail=())  # must not raise
```

- [ ] **Step 6.2: Run test to verify failure**

Run: `uv run pytest tests/test_phase5/test_review_body.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'github.review_body'`.

- [ ] **Step 6.3: Implement github/review_body.py with the tightened template**

Create `github/review_body.py`:

```python
"""Render Findings as GitHub-friendly Markdown.

Two public entry points:
- render_inline_comment(finding, analysis_trail=()) -> str
    The body of one inline review comment. Tightened template: bold
    summary headline (a fix-recommendation, not a noun-phrase bug name),
    inline file:line + severity badge, 2-3 sentence detail paragraph,
    collapsible "Prompt for AI agents" block.

- render_review_summary(run_meta, orphans, trail) -> str
    The summary body of the wrapping PR Review. Run-header line,
    optional CodeRabbit-style "Outside diff range comments" block,
    consolidated "Analysis trail" details block. (Implemented in Task 7.)

The PLAN.md "no emoji" rule applies to source code; rendered output to
GitHub uses badges/icons because they read well in-PR (confirmed during
brainstorming).
"""

from __future__ import annotations

from typing import Iterable

from shared.findings import Finding

SEVERITY_BADGES: dict[str, str] = {
    "high": "🟥 High risk",
    "medium": "🔶 Medium risk",
    "low": "🔹 Low risk",
}


def _location(f: Finding) -> str:
    if f.line_end and f.line_end != f.line:
        return f"{f.file}:{f.line}-{f.line_end}"
    return f"{f.file}:{f.line}"


def render_inline_comment(
    finding: Finding,
    *,
    analysis_trail: Iterable[str] = (),
) -> str:
    """Render one Finding as inline-comment markdown.

    `analysis_trail` is accepted for backward compat; v1 callers pass ()
    because the trail moved to the wrapping review's summary.
    """
    loc = _location(finding)
    sev = SEVERITY_BADGES.get(finding.severity, finding.severity.title())

    lines = [
        f"**{finding.summary}**",
        "",
        f"`{loc}` · {sev}",
        "",
        finding.detail,
        "",
    ]

    # The "Prompt for AI agents" block — copyable handoff prompt that
    # downstream agents can paste directly into a fix session.
    fix_goal = (
        finding.suggested_fix
        or "Fix the bug while preserving the intended behavior."
    )
    lines += [
        "<details>",
        "<summary>🤖 Prompt for AI agents</summary>",
        "",
        "```text",
        "Verify this finding against the current code before editing.",
        "",
        f"Location: {loc}",
        f"Category: {finding.category}",
        f"Severity: {finding.severity}",
        "",
        "Finding:",
        finding.summary,
        "",
        "Context:",
        finding.detail,
        "",
        "Goal:",
        fix_goal,
        "",
        "Before finishing:",
        f"- Inspect {loc} directly.",
        "- Confirm the relevant caller/callee contracts involved in the finding.",
        "- Add or update a focused test that would fail before the fix.",
        "```",
        "",
        "</details>",
    ]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 6.4: Run test to verify it passes**

Run: `uv run pytest tests/test_phase5/test_review_body.py -v`
Expected: 4 tests pass.

- [ ] **Step 6.5: Commit**

```bash
git add github/review_body.py tests/test_phase5/test_review_body.py
git commit -m "phase 5: review_body — tightened render_inline_comment template"
```

---

## Task 7: `github/review_body.py` — `render_review_summary`

The wrapping PR Review's summary body. Three sections:
1. Run-header line (`**Run #042** · Agent SDK · effort=xhigh · ... · 19 turns · $1.30`)
2. Optional `> [!CAUTION]` block + "Outside diff range comments (N)" details for orphan findings (CodeRabbit style)
3. Consolidated "Analysis trail" details block

Each orphan rendered with file:line, summary, detail, and a fenced code-block snippet pulled from the cloned repo at +/-2 lines around the orphan's range. Snippet reading is the only non-trivial bit here.

**Files:**
- Modify: `github/review_body.py`
- Test: `tests/test_phase5/test_review_body.py`

- [ ] **Step 7.1: Write the failing tests**

Append to `tests/test_phase5/test_review_body.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

# Forward import — RunMeta lives in post_review.py per the spec, but the
# render function takes it as input. Since post_review hasn't been built
# yet (Task 9), define a minimal stand-in inline for testing.
from dataclasses import dataclass

from github.review_body import render_review_summary


@dataclass(frozen=True)
class _RunMetaStub:
    run_id: int
    sdk: str
    effort: str
    timestamp_utc: str
    num_turns: int
    cost_usd: float


def _meta(**overrides):
    base = dict(
        run_id=42, sdk="agent", effort="xhigh",
        timestamp_utc="2026-05-03T14:32:00Z",
        num_turns=19, cost_usd=1.30,
    )
    base.update(overrides)
    return _RunMetaStub(**base)


def test_run_header_line_is_present():
    out = render_review_summary(_meta(), orphans=[], trail=[], repo_path=None)
    assert "**Run #042**" in out
    assert "Agent SDK" in out
    assert "effort=xhigh" in out
    assert "19 turns" in out
    assert "$1.30" in out
    # Timestamp rendered as friendly format, not raw ISO
    assert "2026-05-03 14:32 UTC" in out


def test_no_orphans_no_caution_block():
    out = render_review_summary(_meta(), orphans=[], trail=[], repo_path=None)
    assert "[!CAUTION]" not in out
    assert "Outside diff range" not in out


def test_orphans_render_caution_block_with_snippet(tmp_path: Path):
    # Set up a fake cloned repo containing the file the orphan references
    src = tmp_path / "src" / "x.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "line 1\nline 2\nline 3\nORPHAN LINE 4\nline 5\nline 6\nline 7\n"
    )
    orphan = Finding(
        file="src/x.py", line=4, line_end=None,
        category="logic", severity="medium",
        summary="Recommendation here.",
        detail="Detail here.",
        suggested_fix="",
    )
    out = render_review_summary(
        _meta(), orphans=[orphan], trail=[], repo_path=tmp_path,
    )
    assert "[!CAUTION]" in out
    assert "Outside diff range comments (1)" in out
    assert "src/x.py:4" in out
    assert "Recommendation here." in out
    # Snippet is a fenced code block containing the orphan line plus context
    assert "```" in out
    assert "ORPHAN LINE 4" in out
    assert "line 2" in out  # +/- 2 lines of context
    assert "line 6" in out


def test_trail_renders_in_collapsible_details():
    out = render_review_summary(
        _meta(), orphans=[],
        trail=["Loaded the PR diff", "Read foo.py (lines 1-10)"],
        repo_path=None,
    )
    assert "Analysis trail" in out
    assert "<details>" in out
    assert "Loaded the PR diff" in out
    assert "Read foo.py (lines 1-10)" in out


def test_no_trail_no_trail_section():
    out = render_review_summary(_meta(), orphans=[], trail=[], repo_path=None)
    assert "Analysis trail" not in out


def test_truncated_renders_warning_header():
    out = render_review_summary(
        _meta(), orphans=[], trail=[], repo_path=None, truncated=True,
    )
    assert "[!WARNING]" in out
    assert "MAX_TURNS" in out
    assert "Run #042" in out


def test_not_truncated_no_warning():
    out = render_review_summary(_meta(), orphans=[], trail=[], repo_path=None)
    assert "[!WARNING]" not in out
```

- [ ] **Step 7.2: Run tests to verify they fail**

Run: `uv run pytest tests/test_phase5/test_review_body.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_review_summary'`.

- [ ] **Step 7.3: Implement render_review_summary**

Append to `github/review_body.py`:

```python
from datetime import datetime
from pathlib import Path
from typing import Protocol


class _RunMetaLike(Protocol):
    """Structural type for the RunMeta object passed in.

    The real RunMeta lives in github/post_review.py (Task 9). Defining
    it here as a Protocol avoids a circular import while keeping the
    rendering layer typed.
    """
    run_id: int
    sdk: str
    effort: str
    timestamp_utc: str        # ISO-8601, e.g. "2026-05-03T14:32:00Z"
    num_turns: int
    cost_usd: float


_SNIPPET_CONTEXT = 2  # lines of context above + below the orphan


def _format_timestamp(iso: str) -> str:
    """Render '2026-05-03T14:32:00Z' as '2026-05-03 14:32 UTC' for display."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, AttributeError):
        return iso  # if format is unexpected, show raw rather than crash


def _render_run_header(meta: "_RunMetaLike") -> str:
    sdk_label = "Agent SDK" if meta.sdk == "agent" else "Client SDK"
    return (
        f"**Run #{meta.run_id:03d}** · {sdk_label} · "
        f"effort={meta.effort} · {_format_timestamp(meta.timestamp_utc)} · "
        f"{meta.num_turns} turns · ${meta.cost_usd:.2f}"
    )


def _read_snippet(repo_path: Path | None, file_path: str,
                   start: int, end: int) -> str | None:
    """Read +/- _SNIPPET_CONTEXT lines around [start..end] from the file.

    Returns None if the file can't be read — the orphan still renders,
    just without the snippet block.
    """
    if repo_path is None:
        return None
    full = Path(repo_path) / file_path
    try:
        all_lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
    except (FileNotFoundError, OSError):
        return None
    lo = max(1, start - _SNIPPET_CONTEXT)
    hi = min(len(all_lines), end + _SNIPPET_CONTEXT)
    if lo > hi:
        return None
    # 1-indexed slice
    return "\n".join(all_lines[lo - 1:hi])


def _render_orphan(orphan: Finding, repo_path: Path | None) -> str:
    loc = _location(orphan)
    sev = SEVERITY_BADGES.get(orphan.severity, orphan.severity.title())
    end = orphan.line_end or orphan.line
    snippet = _read_snippet(repo_path, orphan.file, orphan.line, end)
    parts = [
        f"#### `{loc}` · {sev}",
        "",
        f"**{orphan.summary}**",
        "",
        orphan.detail,
        "",
    ]
    if snippet is not None:
        parts += [
            "```",
            snippet,
            "```",
            "",
        ]
    return "\n".join(parts)


def render_review_summary(
    meta: "_RunMetaLike",
    orphans: list[Finding],
    trail: list[str],
    *,
    repo_path: Path | None = None,
    truncated: bool = False,
) -> str:
    """Render the body of the wrapping PR Review.

    `repo_path` is the local cloned repo (RepoState.path) — used to read
    snippets for orphan findings. Pass None if you don't have it on
    hand (orphans render without snippets).

    `truncated=True` means the reviewer hit max_turns without calling
    submit_findings — render a warning header so demo viewers know
    findings may be incomplete.
    """
    sections: list[str] = [_render_run_header(meta), ""]

    if truncated:
        sections += [
            "> [!WARNING]",
            f"> Run #{meta.run_id:03d} hit MAX_TURNS without calling "
            "submit_findings. Findings below may be incomplete.",
            "",
        ]

    if orphans:
        sections += [
            "> [!CAUTION]",
            "> Some comments are outside the diff and can't be posted "
            "inline due to platform limits.",
            "",
            "<details>",
            f"<summary>🔭 Outside diff range comments ({len(orphans)})</summary>",
            "",
            *[_render_orphan(o, repo_path) for o in orphans],
            "</details>",
            "",
        ]

    if trail:
        sections += [
            "<details>",
            f"<summary>🔎 Analysis trail ({len(trail)} steps)</summary>",
            "",
            *[f"- {bullet}" for bullet in trail],
            "",
            "</details>",
            "",
        ]

    return "\n".join(sections).rstrip() + "\n"
```

- [ ] **Step 7.4: Run all review_body tests**

Run: `uv run pytest tests/test_phase5/test_review_body.py -v`
Expected: 9 tests pass (5 new + 4 from Task 6).

- [ ] **Step 7.5: Commit**

```bash
git add github/review_body.py tests/test_phase5/test_review_body.py
git commit -m "phase 5: review_body — render_review_summary (run header + orphans + trail)"
```

---

## Task 8: `github/post_review.py` — `_classify` (in-diff vs orphan)

Partition findings into those that anchor inside a hunk on the RIGHT side (post inline) versus those whose location is outside any hunk (post in the summary's "Outside diff range" block). Edge cases per the spec's Section 7 table.

**Files:**
- Create: `github/post_review.py` (with `_classify` only; HTTP POST in Task 9)
- Test: `tests/test_phase5/test_classify.py`

- [ ] **Step 8.1: Write the failing tests**

Create `tests/test_phase5/test_classify.py`:

```python
"""Unit tests for github.post_review._classify."""

from __future__ import annotations

import pytest

from shared.findings import Finding
from github.pr_fetch import Hunk
from github.post_review import _classify, InlineComment


def _f(file="a.py", line=5, line_end=None, summary="r", detail="d"):
    return Finding(
        file=file, line=line, line_end=line_end,
        category="logic", severity="low",
        summary=summary, detail=detail, suggested_fix="",
    )


class TestClassifyInDiff:
    def test_single_line_inside_hunk_is_inline(self):
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        inlines, orphans = _classify([_f("a.py", line=5)], hunks)
        assert len(inlines) == 1 and len(orphans) == 0
        assert inlines[0].path == "a.py"
        assert inlines[0].line == 5

    def test_range_fully_inside_one_hunk_is_inline(self):
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        inlines, _ = _classify([_f("a.py", line=3, line_end=7)], hunks)
        assert len(inlines) == 1
        assert inlines[0].start_line == 3
        assert inlines[0].line == 7

    def test_at_hunk_boundary_inclusive(self):
        # First and last line of a hunk both qualify
        hunks = {"a.py": [Hunk(5, 10, "RIGHT")]}
        inlines, orphans = _classify(
            [_f("a.py", line=5), _f("a.py", line=10)], hunks
        )
        assert len(inlines) == 2 and len(orphans) == 0


class TestClassifyOrphans:
    def test_file_not_in_hunks_is_orphan(self):
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        # b.py isn't a changed file
        inlines, orphans = _classify([_f("b.py", line=5)], hunks)
        assert len(inlines) == 0 and len(orphans) == 1

    def test_line_outside_all_hunks_is_orphan(self):
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        inlines, orphans = _classify([_f("a.py", line=99)], hunks)
        assert len(inlines) == 0 and len(orphans) == 1

    def test_range_crossing_hunk_boundary_is_orphan(self):
        # Spans hunk boundary: GH would 422 on a partial-hunk inline
        hunks = {"a.py": [Hunk(1, 10, "RIGHT"), Hunk(20, 30, "RIGHT")]}
        inlines, orphans = _classify(
            [_f("a.py", line=5, line_end=25)], hunks
        )
        assert len(inlines) == 0 and len(orphans) == 1

    def test_range_spanning_two_separate_hunks_is_orphan(self):
        # Even though both endpoints are in *some* hunk, they're in
        # different hunks. Orphan it.
        hunks = {"a.py": [Hunk(1, 5, "RIGHT"), Hunk(10, 15, "RIGHT")]}
        inlines, orphans = _classify(
            [_f("a.py", line=3, line_end=12)], hunks
        )
        assert len(inlines) == 0 and len(orphans) == 1


class TestClassifyDefensive:
    def test_reversed_bounds_swap_then_check(self):
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        # line=8, line_end=3 (reversed) — defensively swap, then it's inside hunk
        inlines, orphans = _classify(
            [_f("a.py", line=8, line_end=3)], hunks
        )
        assert len(inlines) == 1 and len(orphans) == 0
        # The emitted inline comment uses the corrected (swapped) bounds
        assert inlines[0].start_line == 3
        assert inlines[0].line == 8

    def test_two_findings_at_same_location_both_post(self):
        # We don't dedup — that's the reviewer's responsibility, not ours
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        inlines, orphans = _classify(
            [_f("a.py", line=5, summary="A"),
             _f("a.py", line=5, summary="B")],
            hunks,
        )
        assert len(inlines) == 2

    def test_empty_findings_returns_empty(self):
        inlines, orphans = _classify([], {"a.py": [Hunk(1, 10, "RIGHT")]})
        assert inlines == [] and orphans == []
```

- [ ] **Step 8.2: Run tests to verify they fail**

Run: `uv run pytest tests/test_phase5/test_classify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'github.post_review'`.

- [ ] **Step 8.3: Implement post_review.py with _classify**

Create `github/post_review.py`:

```python
"""GitHub write-side: classify findings, render, POST one PR Review.

This module owns:
- _classify        : partition findings into inline vs orphan based on hunks
- render_payload_for_inspection : build the payload dict (used by inspect/dry-run)
- submit_review    : the actual HTTP POST to GitHub (Task 9)

Auth: GITHUB_REVIEW_BOT_TOKEN env var (Working-Ant identity). The token
is passed to submit_review explicitly — never read from os.environ here,
so tests can inject a fake without monkey-patching the environment.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.findings import Finding
from github.pr_fetch import Hunk


@dataclass(frozen=True)
class RunMeta:
    run_id: int
    sdk: str           # "agent" | "client"
    effort: str        # "high" | "xhigh" | ...
    timestamp_utc: str # ISO-8601 UTC, e.g. "2026-05-03T14:32:00Z"
    num_turns: int
    cost_usd: float


@dataclass(frozen=True)
class InlineComment:
    """One inline review comment, ready to be POSTed.

    Single-line: start_line is None.
    Multi-line:  start_line is set, line is the end line, both side="RIGHT".
    """
    path: str
    line: int
    side: str             # "RIGHT"
    body: str
    start_line: int | None = None
    start_side: str | None = None  # set to "RIGHT" iff start_line is set


def _span(f: Finding) -> tuple[int, int]:
    """Defensively-corrected (start_line, end_line) for a Finding."""
    end = f.line_end or f.line
    if end < f.line:
        return end, f.line  # swap reversed bounds
    return f.line, end


def _fits_in_one_hunk(span: tuple[int, int], hunks: list[Hunk]) -> bool:
    start, end = span
    for h in hunks:
        if h.start_line <= start and end <= h.end_line:
            return True
    return False


def _classify(
    findings: list[Finding],
    hunks: dict[str, list[Hunk]],
) -> tuple[list[InlineComment], list[Finding]]:
    """Partition findings into (inline, orphan).

    A finding is inline iff its full (line .. line_end) span fits inside
    a single hunk on side="RIGHT". Otherwise it's an orphan.

    The body field on InlineComment is left empty here — the renderer
    fills it during submit_review (separation of concerns: classification
    doesn't depend on rendering).
    """
    from github.review_body import render_inline_comment  # late import to avoid cycle

    inlines: list[InlineComment] = []
    orphans: list[Finding] = []

    for f in findings:
        file_hunks = hunks.get(f.file)
        if not file_hunks:
            orphans.append(f)
            continue
        start, end = _span(f)
        if not _fits_in_one_hunk((start, end), file_hunks):
            orphans.append(f)
            continue
        body = render_inline_comment(f)
        if start == end:
            inlines.append(InlineComment(
                path=f.file, line=start, side="RIGHT", body=body,
            ))
        else:
            inlines.append(InlineComment(
                path=f.file, line=end, side="RIGHT",
                start_line=start, start_side="RIGHT",
                body=body,
            ))

    return inlines, orphans
```

- [ ] **Step 8.4: Run tests to verify they pass**

Run: `uv run pytest tests/test_phase5/test_classify.py -v`
Expected: 9 tests pass.

- [ ] **Step 8.5: Commit**

```bash
git add github/post_review.py tests/test_phase5/test_classify.py
git commit -m "phase 5: post_review — _classify partitions findings into inline vs orphan"
```

---

## Task 9: `github/post_review.py` — `submit_review` + `render_payload_for_inspection`

The actual GitHub REST POST. One call posts the whole review (summary body + N inline comments) atomically. Uses `httpx` (already a project dep).

**Files:**
- Modify: `github/post_review.py`
- Test: extend `tests/test_phase5/test_classify.py` (rename file? no — keep it focused; add a separate `test_post_review.py` for the HTTP layer)
- Test: `tests/test_phase5/test_post_review.py`

- [ ] **Step 9.1: Write the failing tests**

Create `tests/test_phase5/test_post_review.py`:

```python
"""Unit tests for the HTTP layer of github.post_review."""

from __future__ import annotations

from unittest.mock import patch as mock_patch, MagicMock

import pytest

from shared.findings import Finding
from github.pr_fetch import PullRequest, Hunk
from github.post_review import (
    RunMeta, submit_review, render_payload_for_inspection,
)


def _pr():
    return PullRequest(
        owner="Hendrik040", repo="sentry", number=1,
        base_sha="abc123", head_sha="def456",
        title="t", html_url="https://github.com/Hendrik040/sentry/pull/1",
    )


def _meta():
    return RunMeta(
        run_id=42, sdk="agent", effort="xhigh",
        timestamp_utc="2026-05-03T14:32:00Z",
        num_turns=19, cost_usd=1.30,
    )


def _f(file="a.py", line=5, summary="r"):
    return Finding(
        file=file, line=line, line_end=None,
        category="logic", severity="low",
        summary=summary, detail="d.", suggested_fix="",
    )


class TestRenderPayloadForInspection:
    def test_payload_shape_with_inline_only(self):
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        payload = render_payload_for_inspection(
            _pr(), [_f("a.py", line=5)], hunks, _meta(), trail=[],
        )
        assert payload["commit_id"] == "def456"
        assert payload["event"] == "COMMENT"
        assert "**Run #042**" in payload["body"]
        assert len(payload["comments"]) == 1
        assert payload["comments"][0]["path"] == "a.py"
        assert payload["comments"][0]["line"] == 5
        assert payload["comments"][0]["side"] == "RIGHT"
        assert "start_line" not in payload["comments"][0]  # single-line

    def test_orphan_lands_in_summary_not_comments(self):
        # b.py isn't in the hunks dict — orphan
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        payload = render_payload_for_inspection(
            _pr(), [_f("b.py", line=5)], hunks, _meta(), trail=[],
        )
        assert payload["comments"] == []
        assert "Outside diff range comments (1)" in payload["body"]


class TestSubmitReview:
    def test_posts_to_correct_endpoint_with_token(self):
        hunks = {"a.py": [Hunk(1, 10, "RIGHT")]}
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {
            "html_url": "https://github.com/o/r/pull/1#pullrequestreview-555"
        }
        with mock_patch("github.post_review.httpx.post") as post:
            post.return_value = fake_resp
            url = submit_review(
                _pr(), [_f("a.py", line=5)], hunks, _meta(),
                trail=[], token="ghp_fake",
            )
        assert url == "https://github.com/o/r/pull/1#pullrequestreview-555"
        called_url = post.call_args[0][0]
        assert called_url == (
            "https://api.github.com/repos/Hendrik040/sentry/pulls/1/reviews"
        )
        headers = post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "token ghp_fake"
        assert headers["Accept"] == "application/vnd.github+json"

    def test_raises_on_4xx_no_retry(self):
        fake_resp = MagicMock(status_code=422)
        fake_resp.text = '{"message": "position outside diff"}'
        with mock_patch("github.post_review.httpx.post") as post:
            post.return_value = fake_resp
            with pytest.raises(RuntimeError, match="422"):
                submit_review(
                    _pr(), [_f("a.py", line=5)],
                    {"a.py": [Hunk(1, 10, "RIGHT")]},
                    _meta(), trail=[], token="ghp_fake",
                )
        # 4xx means caller bug (e.g. position outside diff) — never retry
        assert post.call_count == 1

    def test_retries_once_on_5xx_then_succeeds(self):
        first = MagicMock(status_code=503)
        first.text = "service unavailable"
        second = MagicMock(status_code=200)
        second.json.return_value = {"html_url": "https://x/y"}
        with mock_patch("github.post_review.httpx.post") as post, \
             mock_patch("github.post_review.time.sleep"):
            post.side_effect = [first, second]
            url = submit_review(
                _pr(), [_f("a.py", line=5)],
                {"a.py": [Hunk(1, 10, "RIGHT")]},
                _meta(), trail=[], token="ghp_fake",
            )
        assert url == "https://x/y"
        assert post.call_count == 2

    def test_raises_after_5xx_retry_also_fails(self):
        fake = MagicMock(status_code=503)
        fake.text = "still unavailable"
        with mock_patch("github.post_review.httpx.post") as post, \
             mock_patch("github.post_review.time.sleep"):
            post.return_value = fake
            with pytest.raises(RuntimeError, match="503"):
                submit_review(
                    _pr(), [_f("a.py", line=5)],
                    {"a.py": [Hunk(1, 10, "RIGHT")]},
                    _meta(), trail=[], token="ghp_fake",
                )
        assert post.call_count == 2
```

- [ ] **Step 9.2: Run tests to verify they fail**

Run: `uv run pytest tests/test_phase5/test_post_review.py -v`
Expected: FAIL with `ImportError: cannot import name 'submit_review'`.

- [ ] **Step 9.3: Implement submit_review + render_payload_for_inspection**

Append to `github/post_review.py`:

```python
import time
from pathlib import Path

import httpx

from github.pr_fetch import PullRequest
from github.review_body import render_review_summary


_GITHUB_API = "https://api.github.com"
_HTTP_TIMEOUT_SECONDS = 30


def _to_inline_payload(c: InlineComment) -> dict:
    """Convert an InlineComment dataclass to the GH REST API shape."""
    payload: dict = {
        "path": c.path,
        "line": c.line,
        "side": c.side,
        "body": c.body,
    }
    if c.start_line is not None:
        payload["start_line"] = c.start_line
        payload["start_side"] = c.start_side or "RIGHT"
    return payload


def render_payload_for_inspection(
    pr: PullRequest,
    findings: list[Finding],
    hunks: dict[str, list[Hunk]],
    run_meta: RunMeta,
    trail: list[str],
    *,
    repo_path: Path | None = None,
    truncated: bool = False,
) -> dict:
    """Build the full POST payload without sending it. Used by --dry-run
    and inspect_render.py."""
    inlines, orphans = _classify(findings, hunks)
    summary = render_review_summary(
        run_meta, orphans, trail, repo_path=repo_path, truncated=truncated,
    )
    return {
        "commit_id": pr.head_sha,
        "event": "COMMENT",
        "body": summary,
        "comments": [_to_inline_payload(c) for c in inlines],
    }


def submit_review(
    pr: PullRequest,
    findings: list[Finding],
    hunks: dict[str, list[Hunk]],
    run_meta: RunMeta,
    trail: list[str],
    token: str,
    *,
    repo_path: Path | None = None,
    truncated: bool = False,
) -> str:
    """POST a single PR Review with N inline comments + summary body.

    Returns the review's html_url on success. Raises RuntimeError with
    the GH response body on any non-2xx status — caller is responsible
    for the "saved to ..." retry-instruction message per spec section 7.

    Retries once on 5xx after a 5-second sleep (transient GH outage).
    """
    payload = render_payload_for_inspection(
        pr, findings, hunks, run_meta, trail,
        repo_path=repo_path, truncated=truncated,
    )
    url = f"{_GITHUB_API}/repos/{pr.owner}/{pr.repo}/pulls/{pr.number}/reviews"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    for attempt in (1, 2):
        resp = httpx.post(
            url, json=payload, headers=headers, timeout=_HTTP_TIMEOUT_SECONDS,
        )
        if 200 <= resp.status_code < 300:
            return resp.json()["html_url"]
        # Retry once on 5xx; raise immediately on 4xx (caller's bug)
        if 500 <= resp.status_code < 600 and attempt == 1:
            time.sleep(5)
            continue
        raise RuntimeError(
            f"GitHub POST failed with status {resp.status_code}: {resp.text}"
        )
    raise RuntimeError("unreachable")  # for type checker
```

- [ ] **Step 9.4: Run all post_review tests**

Run: `uv run pytest tests/test_phase5/test_post_review.py tests/test_phase5/test_classify.py -v`
Expected: all tests pass.

- [ ] **Step 9.5: Commit**

```bash
git add github/post_review.py tests/test_phase5/test_post_review.py
git commit -m "phase 5: post_review — submit_review (HTTP POST) + render_payload_for_inspection"
```

---

## Task 10: `scripts/github/review_pr.py` — CLI orchestrator

Ties everything together. Pre-flight checks fail fast, reviewer runs, post happens, URL prints.

**Files:**
- Create: `scripts/github/review_pr.py`
- Test: smoke-only (driving the real reviewer + real GH POST is the smoke test in Task 12)

- [ ] **Step 10.1: Implement the CLI orchestrator**

Create `scripts/github/review_pr.py`:

```python
"""CLI: review a GitHub PR with the Agent SDK reviewer and post the result.

Usage:
    uv run python scripts/github/review_pr.py <pr_url> [--dry-run]

Pre-flight checks (fail fast before the costly reviewer call):
- GITHUB_REVIEW_BOT_TOKEN env var is set
- gh CLI is installed and authed
- PR URL parses
- PR exists (gh api succeeds)

Mid-run: the reviewer runs unchanged. If it raises, exit 1 (no review
posted). If it returns 0 findings, still post a "no findings" review.
If it hit max_turns without submitting, post with a warning header.

Post-time: HTTP failures print where to find the saved findings so
nothing is lost. (Reposting them is a future helper, out of scope.)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent_sdk import reviewer
from github import pr_fetch, repo_setup, trace_extract, post_review
from github.post_review import RunMeta


def _exit(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


BOT_USER = "Working-Ant"


def _preflight(pr_url: str) -> pr_fetch.PullRequest:
    if not os.environ.get("GITHUB_REVIEW_BOT_TOKEN"):
        _exit(2, "ERROR: GITHUB_REVIEW_BOT_TOKEN not set. "
                  "Add it to .env (Working-Ant token).")
    if shutil.which("gh") is None:
        _exit(2, "ERROR: `gh` CLI not on PATH. Install it and run `gh auth login`.")
    auth = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    if auth.returncode != 0:
        _exit(2, "ERROR: gh CLI not authenticated. Run `gh auth login`.")
    try:
        pr = pr_fetch.fetch_pr(pr_url)
    except ValueError as e:
        _exit(2, f"ERROR: {e}")
    except subprocess.CalledProcessError as e:
        _exit(1, f"ERROR: gh api failed (PR may not exist or be inaccessible): {e}")

    # Confirm the bot user has write access on this repo. Without this
    # check, posting fails opaquely with 403 after a 2-min clone + $1+
    # reviewer run. Fail fast here instead.
    perm_check = subprocess.run(
        ["gh", "api",
         f"repos/{pr.owner}/{pr.repo}/collaborators/{BOT_USER}/permission"],
        capture_output=True, text=True,
    )
    if perm_check.returncode != 0:
        _exit(2, f"ERROR: {BOT_USER} is not a collaborator on "
                  f"{pr.owner}/{pr.repo}. Add as Collaborator with write access "
                  f"before running.")
    try:
        perm_data = json.loads(perm_check.stdout)
        perm = perm_data.get("permission", "none")
    except json.JSONDecodeError:
        _exit(1, f"ERROR: unexpected response from gh api collaborators check: "
                  f"{perm_check.stdout!r}")
    if perm not in ("write", "admin", "maintain"):
        _exit(2, f"ERROR: {BOT_USER} has '{perm}' access to {pr.owner}/{pr.repo}; "
                  f"need at least 'write' to post reviews.")

    return pr


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pr_url", help="https://github.com/<owner>/<repo>/pull/<n>")
    p.add_argument("--dry-run", action="store_true",
                   help="Run everything except the GH POST; print the would-be payload.")
    args = p.parse_args()

    pr = _preflight(args.pr_url)
    print(f"[1/4] Fetching PR {pr.owner}/{pr.repo}#{pr.number} ... "
          f"base={pr.base_sha[:7]} head={pr.head_sha[:7]}")
    hunks = pr_fetch.fetch_diff_hunks(pr.owner, pr.repo, pr.number)
    print(f"      {sum(len(v) for v in hunks.values())} hunks across "
          f"{len(hunks)} files")

    print(f"[2/4] Cloning {pr.owner}/{pr.repo} into a tempdir "
          f"(this may take a minute) ...")
    with repo_setup.setup_pr_repo(pr) as repo:
        print(f"[3/4] Running Agent SDK reviewer (effort=xhigh) ...")
        try:
            result = reviewer.run(repo.path, repo.base_ref, repo.head_ref)
        except Exception as e:
            _exit(1, f"ERROR: reviewer raised: {e!r}")

        print(f"      {result['num_turns']} turns, "
              f"${result['cost_usd']:.2f}, "
              f"{len(result['findings'])} findings, "
              f"exit_reason={result.get('exit_reason', 'unknown')}")

        trail = trace_extract.extract_trail(Path(result["trace_path"]))
        run_meta = RunMeta(
            run_id=result["run_id"],
            sdk="agent",
            effort="xhigh",
            timestamp_utc=_now_iso(),
            num_turns=result["num_turns"],
            cost_usd=result["cost_usd"],
        )
        # Reviewer hit MAX_TURNS without calling submit_findings -- the
        # findings list will likely be empty/partial; surface a warning
        # in the posted review so demo viewers aren't misled.
        truncated = (
            result.get("exit_reason") == "max_turns"
            and not result.get("submitted", True)
        )
        if truncated:
            print("      WARN: reviewer hit MAX_TURNS before submitting findings")

        if args.dry_run:
            print(f"[4/4] --dry-run: payload below, not posting to GH")
            payload = post_review.render_payload_for_inspection(
                pr, result["findings"], hunks, run_meta, trail,
                repo_path=repo.path, truncated=truncated,
            )
            print(json.dumps(payload, indent=2))
            return

        print(f"[4/4] Posting review (Run #{result['run_id']}) ...")
        token = os.environ["GITHUB_REVIEW_BOT_TOKEN"]
        try:
            url = post_review.submit_review(
                pr, result["findings"], hunks, run_meta, trail,
                token=token, repo_path=repo.path, truncated=truncated,
            )
        except RuntimeError as e:
            _exit(1, f"ERROR: GH POST failed: {e}\n"
                     f"Findings preserved at {result['result_path']}.")
        print(f"        {url}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 10.2: Verify imports cleanly**

Run: `uv run python -c "from scripts.github import review_pr; print('ok')"`
Expected: `ok` (after the script's `sys.path.insert` resolves the imports correctly).
If fails: check the imports and fix.

- [ ] **Step 10.3: Verify --help works**

Run: `uv run python scripts/github/review_pr.py --help`
Expected: argparse help text printing usage + the docstring.

- [ ] **Step 10.4: Verify pre-flight catches missing token**

Run: `unset GITHUB_REVIEW_BOT_TOKEN; uv run python scripts/github/review_pr.py "https://github.com/Hendrik040/sentry/pull/1"`
Expected: `ERROR: GITHUB_REVIEW_BOT_TOKEN not set...` and exit code 2.
Then re-source `.env`.

- [ ] **Step 10.5: Commit**

```bash
git add scripts/github/review_pr.py
git commit -m "phase 5: scripts/github/review_pr.py — CLI orchestrator with --dry-run"
```

---

## Task 11: Inspect scripts (4 of them)

Operator-facing scripts that exercise individual layers in isolation. Each is small and follows the same pattern as the existing `scripts/inspect_*.py`.

**Files:**
- Create: `scripts/github/inspect_hunks.py`
- Create: `scripts/github/inspect_trail.py`
- Create: `scripts/github/inspect_classify.py`
- Create: `scripts/github/inspect_render.py`

- [ ] **Step 11.1: Write `inspect_hunks.py`**

Create `scripts/github/inspect_hunks.py`:

```python
"""Print the parsed diff hunks for a PR. Verifies pr_fetch end-to-end.

Usage:
    uv run python scripts/github/inspect_hunks.py <pr_url>
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from github import pr_fetch


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: inspect_hunks.py <pr_url>")
    pr = pr_fetch.fetch_pr(sys.argv[1])
    hunks = pr_fetch.fetch_diff_hunks(pr.owner, pr.repo, pr.number)
    print(f"PR {pr.owner}/{pr.repo}#{pr.number}: {len(hunks)} files with hunks\n")
    for fname, hs in sorted(hunks.items()):
        print(f"  {fname}")
        for h in hs:
            print(f"    line {h.start_line}-{h.end_line} ({h.side})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 11.2: Write `inspect_trail.py`**

Create `scripts/github/inspect_trail.py`:

```python
"""Print the rendered analysis trail bullets for a given run.

Usage:
    uv run python scripts/github/inspect_trail.py <run_id>
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from github import trace_extract


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: inspect_trail.py <run_id>")
    run_id = int(sys.argv[1])
    trace_path = PROJECT_ROOT / "agent_sdk" / "traces" / f"run_{run_id:03d}.txt"
    if not trace_path.exists():
        sys.exit(f"trace file not found: {trace_path}")
    bullets = trace_extract.extract_trail(trace_path)
    if not bullets:
        print("(empty trail — file unparseable or no recognized tool calls)")
        return
    print(f"Trail for run #{run_id} ({len(bullets)} bullets):\n")
    for b in bullets:
        print(f"  - {b}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 11.3: Write `inspect_classify.py`**

Create `scripts/github/inspect_classify.py`:

```python
"""Dry-run classification: print which findings would be inline vs orphan.

Usage:
    uv run python scripts/github/inspect_classify.py <pr_url> <result_path>

result_path points at agent_sdk/results/run_NNN.txt — the file the
reviewer wrote with the JSON list of findings.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.findings import Finding
from github import pr_fetch
from github.post_review import _classify


def _load_findings(path: Path) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    if "# ---" in text:
        text = text.split("# ---", 1)[1]
    return [Finding(**item) for item in json.loads(text.strip())]


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: inspect_classify.py <pr_url> <result_path>")
    pr_url, result_path = sys.argv[1], Path(sys.argv[2])
    pr = pr_fetch.fetch_pr(pr_url)
    hunks = pr_fetch.fetch_diff_hunks(pr.owner, pr.repo, pr.number)
    findings = _load_findings(result_path)
    inlines, orphans = _classify(findings, hunks)
    print(f"PR {pr.owner}/{pr.repo}#{pr.number} · {len(findings)} findings\n")
    print(f"INLINE ({len(inlines)}):")
    for c in inlines:
        loc = f"{c.path}:{c.start_line}-{c.line}" if c.start_line else f"{c.path}:{c.line}"
        print(f"  {loc}")
    print(f"\nORPHAN ({len(orphans)}):")
    for o in orphans:
        loc = f"{o.file}:{o.line}-{o.line_end}" if o.line_end else f"{o.file}:{o.line}"
        reason = "file not in PR" if o.file not in hunks else "line outside hunks"
        print(f"  {loc}  ({reason})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 11.4: Write `inspect_render.py`**

Create `scripts/github/inspect_render.py`:

```python
"""Full dry-run: print the would-be review payload as markdown.

Usage:
    uv run python scripts/github/inspect_render.py <pr_url> <result_path>

The most-used affordance during demo rehearsal — iterate prompt + render
changes against a real run's findings without posting to GitHub.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.findings import Finding
from github import pr_fetch, post_review, trace_extract
from github.post_review import RunMeta


def _load_findings(path: Path) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    if "# ---" in text:
        text = text.split("# ---", 1)[1]
    return [Finding(**item) for item in json.loads(text.strip())]


def _run_id_from_result_path(path: Path) -> int:
    # agent_sdk/results/run_042.txt -> 42
    name = path.stem  # "run_042"
    return int(name.split("_", 1)[1])


def _trace_path_for(run_id: int) -> Path:
    return PROJECT_ROOT / "agent_sdk" / "traces" / f"run_{run_id:03d}.txt"


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: inspect_render.py <pr_url> <result_path>")
    pr_url, result_path = sys.argv[1], Path(sys.argv[2])

    pr = pr_fetch.fetch_pr(pr_url)
    hunks = pr_fetch.fetch_diff_hunks(pr.owner, pr.repo, pr.number)
    findings = _load_findings(result_path)
    run_id = _run_id_from_result_path(result_path)
    trail = trace_extract.extract_trail(_trace_path_for(run_id))
    run_meta = RunMeta(
        run_id=run_id, sdk="agent", effort="xhigh",
        timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        num_turns=0, cost_usd=0.0,  # we don't have these here; show 0
    )
    payload = post_review.render_payload_for_inspection(
        pr, findings, hunks, run_meta, trail,
    )
    print("=" * 78)
    print("REVIEW SUMMARY BODY")
    print("=" * 78)
    print(payload["body"])
    print("=" * 78)
    print(f"INLINE COMMENTS ({len(payload['comments'])})")
    print("=" * 78)
    for i, c in enumerate(payload["comments"], 1):
        if c.get("start_line"):
            loc = f"{c['path']}:{c['start_line']}-{c['line']}"
        else:
            loc = f"{c['path']}:{c['line']}"
        print(f"\n--- comment {i} @ {loc} ---\n")
        print(c["body"])


if __name__ == "__main__":
    main()
```

- [ ] **Step 11.5: Run each inspect script's --help / usage line**

Run each (they should each exit cleanly with their usage text):
```bash
uv run python scripts/github/inspect_hunks.py 2>&1 | head -3
uv run python scripts/github/inspect_trail.py 2>&1 | head -3
uv run python scripts/github/inspect_classify.py 2>&1 | head -3
uv run python scripts/github/inspect_render.py 2>&1 | head -3
```
Expected: each prints `usage: ...` and exits.

- [ ] **Step 11.6: Commit**

```bash
git add scripts/github/inspect_hunks.py scripts/github/inspect_trail.py \
        scripts/github/inspect_classify.py scripts/github/inspect_render.py
git commit -m "phase 5: scripts/github/inspect_*.py — operator-facing layer-by-layer dry-runs"
```

---

## Task 12: Smoke test — `smoke_phase5.py`

Two tests: A) structural import check, B) one real POST against a designated sandbox PR. Run before each high-stakes rehearsal.

**Files:**
- Create: `scripts/github/smoke_phase5.py`

- [ ] **Step 12.1: Implement the smoke script**

Create `scripts/github/smoke_phase5.py`:

```python
"""Smoke test for Phase 5 — run before demo rehearsals.

Usage:
    uv run python scripts/github/smoke_phase5.py [<sandbox_pr_url>]

Test A (no network): structural import check + env/auth check.
Test B (one real POST): runs review_pr.py against the sandbox PR.

Default sandbox PR is the one configured in PHASE5_SMOKE_PR_URL env var,
or you can pass one as argv[1]. The sandbox PR should be SEPARATE from
the actual demo PR — runs leave a real review behind.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _test_a_structural() -> None:
    print("=== Test A: structural ===")
    # Imports must work
    from agent_sdk import reviewer  # noqa: F401
    from github import pr_fetch, repo_setup, trace_extract, post_review  # noqa: F401
    print("  imports: ok")

    # Env var
    if not os.environ.get("GITHUB_REVIEW_BOT_TOKEN"):
        sys.exit("FAIL: GITHUB_REVIEW_BOT_TOKEN not set")
    print("  GITHUB_REVIEW_BOT_TOKEN: set")

    # gh CLI
    if shutil.which("gh") is None:
        sys.exit("FAIL: gh CLI not on PATH")
    auth = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    if auth.returncode != 0:
        sys.exit("FAIL: gh CLI not authenticated")
    print("  gh CLI: ok\n")


def _test_b_real_post(sandbox_url: str) -> None:
    print(f"=== Test B: real POST to {sandbox_url} ===")
    print("  (this will run the agent and post one real review)\n")
    cmd = [
        "uv", "run", "python", "scripts/github/review_pr.py", sandbox_url,
    ]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        sys.exit(f"FAIL: review_pr.py exited {result.returncode}")
    print("\n  Visually verify the review URL above renders correctly in GitHub.")


def main() -> None:
    sandbox = (
        sys.argv[1] if len(sys.argv) > 1
        else os.environ.get("PHASE5_SMOKE_PR_URL")
    )
    _test_a_structural()
    if not sandbox:
        print("SKIPPING Test B (no sandbox PR URL provided).")
        print("  Set PHASE5_SMOKE_PR_URL or pass it as argv[1].")
        return
    _test_b_real_post(sandbox)


if __name__ == "__main__":
    main()
```

- [ ] **Step 12.2: Run Test A only (no sandbox URL provided)**

Run: `uv run python scripts/github/smoke_phase5.py`
Expected: Test A prints `imports: ok`, env+gh check pass, then prints `SKIPPING Test B`. Exit code 0.

- [ ] **Step 12.3: Commit**

```bash
git add scripts/github/smoke_phase5.py
git commit -m "phase 5: scripts/github/smoke_phase5.py — pre-rehearsal end-to-end smoke"
```

---

## Task 13: Body-tightening prompt update + fixture re-validation

The renderer now expects `Finding.summary` to be a verb-led recommendation and `Finding.detail` to be exactly 3 sentences. The prompt in `shared/prompts.py` needs to be updated to produce that shape, and the change must be re-validated against the fixture suite to confirm no regression in find rate.

**Files:**
- Modify: `shared/prompts.py`
- Modify: `docs/headtohead.md` (only if numbers shift)

- [ ] **Step 13.1: Read the current prompt and find the Finding-shape guidance**

Run: `grep -n "summary\|detail\|finding" shared/prompts.py | head -30`

Locate the section that describes how to fill the Finding fields (likely under `<reporting_rules>` or a similar tag). Note the line numbers of the current `summary` and `detail` instructions.

- [ ] **Step 13.2: Edit the prompt with the tightened spec**

The exact text varies depending on the current state, so make a targeted edit that replaces the current `summary` and `detail` guidance with this language (preserve surrounding tags/structure):

> **summary** (1 line, max 100 chars): A directive recommendation phrased
> as the action a developer should take. Start with a verb (Implement,
> Revert, Replace, Guard, Move, Drop, Add, Use). Do NOT phrase as a bug
> headline ("X is broken"). Examples: "Implement the abstract methods
> or revert MetricAlertDetectorHandler to the non-stateful base."
>
> **detail** (exactly 3 sentences): Sentence 1 names the failure mode.
> Sentence 2 names the concrete trigger or call site. Sentence 3 ends
> with a binary fix recommendation. Do NOT walk through the diff in
> prose — that belongs in suggested_fix as a code block.

Use the Edit tool to find-and-replace the existing summary/detail guidance with the above. If you can't find a clean unique match, read the file and rewrite the relevant section in one Write operation.

- [ ] **Step 13.3: Confirm the edit produced the intended text**

Run: `grep -A 8 "summary" shared/prompts.py | head -20`
Expected: the new text is present.

- [ ] **Step 13.4: Run the full unit-test suite to confirm nothing else broke**

Run: `uv run pytest tests/test_phase5/ -v`
Expected: all Phase 5 tests still pass.

- [ ] **Step 13.5: Re-run the fixture suite on Agent SDK (the slow + costly step)**

Run: `uv run python scripts/run_suite.py --sdk agent`
Expected: completes within the suite's existing cost ceiling (~$10). Outputs a new `agent_sdk/results/suite_NNN.md`.

- [ ] **Step 13.6: Compare new suite numbers against the previous Agent SDK suite_NNN.md**

Run: `diff agent_sdk/results/suite_005.md agent_sdk/results/suite_006.md` (substitute the actual file names from `ls agent_sdk/results/suite_*.md`).

Look for: are find rates the same or better? If WORSE (any fixture flipped from Y/Y to N/N), the prompt change regressed the reviewer — STOP and revert step 13.2, report the regression. If find rates held or improved, proceed.

- [ ] **Step 13.7: Update docs/headtohead.md if numbers shifted**

If turn counts or costs differ meaningfully, run: `uv run python scripts/headtohead.py` to regenerate `docs/headtohead.md`. Otherwise skip.

- [ ] **Step 13.8: Commit (one commit; suite_NNN.md and headtohead.md are evidence)**

```bash
git add shared/prompts.py
# Add new suite output(s) and any updated head-to-head doc:
git add agent_sdk/results/suite_*.md docs/headtohead.md 2>/dev/null || true
git commit -m "phase 5: prompt — tighten summary (verb-led) + detail (exactly 3 sentences)"
```

---

## Final integration check

- [ ] **Run the full phase-5 unit suite**

Run: `uv run pytest tests/test_phase5/ -v`
Expected: all tests pass.

- [ ] **Run a --dry-run end-to-end against a real PR**

Run: `uv run python scripts/github/review_pr.py "https://github.com/Hendrik040/sentry/pull/1" --dry-run` (substitute an existing PR on your fork). Expected: pre-flight passes, clone happens, reviewer runs, payload prints to stdout. No POST.

- [ ] **Run Test A of the smoke**

Run: `uv run python scripts/github/smoke_phase5.py` (no sandbox URL).
Expected: Test A passes, Test B skipped.

- [ ] **Stop here.** Test B (the real POST) is run by the user before a rehearsal, not as part of implementation. The implementation is complete when all the above checks pass.
