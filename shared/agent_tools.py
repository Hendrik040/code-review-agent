"""Investigation tools the reviewer can call.

Phase 4 refactor: every tool is now a thin shell-idiom wrapper over
`Repo.exec` (or `Repo.upload_bytes` for write_file). The repo argument
is a `sandbox.repo.Repo` — `LocalRepo` for the host backend,
`DaytonaRepo` for the sandbox backend. Tools never touch host bytes
directly; bash, ast-grep, grep, file IO, and ODIS all run wherever
the repo lives.

Both reviewers (Client SDK and Agent SDK) use the same callables.
The Client SDK passes the JSON tool schemas in `messages.create(tools=[...])`;
the Agent SDK wraps them via the @tool decorator inside its in-process
MCP server.
"""

from __future__ import annotations

import json
import shlex
from typing import Any

from sandbox.repo import Repo

# Cap output at sane sizes so a chatty grep doesn't blow context. These
# also serve as the auto-offload mitigation on the Agent SDK path,
# since Phase 4 replaces the harness's Read/Bash/Grep with our MCP
# proxies (which lose harness-side auto-offloading).
_MAX_AST_MATCHES = 30
_MAX_GREP_LINES = 50
_MAX_BASH_OUTPUT_CHARS = 8000
_AST_TIMEOUT_S = 15
_GREP_TIMEOUT_S = 10
_BASH_TIMEOUT_S = 15
_ODIS_TIMEOUT_S = 30


def read_file_section(repo: Repo, path: str, start_line: int, end_line: int) -> str:
    """Read [start_line, end_line] (1-indexed, inclusive) from repo/path.

    Returns line-numbered text (same format as pre-Phase-4) or a short
    error string. Never raises — the agent loop should never crash
    because the model passed a bad path. Path traversal is the
    backend's job (LocalRepo's `_safe_target`; sandbox cwd is locked
    to /workspace/repo).
    """
    result = repo.exec(f"cat -- {shlex.quote(path)}", timeout=_BASH_TIMEOUT_S)
    if not result.ok:
        # cat-style failures (no such file, is a directory, etc.) come
        # back as exit_code != 0 with stderr describing the issue.
        return f"Error reading {path}: {result.stderr.strip() or 'exit ' + str(result.exit_code)}"
    rows = result.stdout.splitlines()
    start = max(1, start_line) - 1
    end = min(len(rows), max(start_line, end_line))
    if start >= end:
        return f"(empty range {start_line}-{end_line} in {path}; file has {len(rows)} lines)"
    return "\n".join(f"{i:>4}  {rows[i - 1]}" for i in range(start + 1, end + 1))


def ast_search(repo: Repo, pattern: str, language: str = "python") -> str:
    """Run `ast-grep run -p <pattern> --lang <language>` in the repo.

    Returns a compact text summary of matches (capped at 30) or an error
    string. Pattern syntax: `$VAR` matches a single AST node, `$$$` matches
    any sequence. E.g. `add($$$)` finds every call to `add` regardless of
    arity or whitespace.
    """
    cmd = (
        f"ast-grep run -p {shlex.quote(pattern)} "
        f"--lang {shlex.quote(language)} --json=stream"
    )
    result = repo.exec(cmd, timeout=_AST_TIMEOUT_S)
    # ast-grep returns 0 on matches, 1 on no matches, anything else is
    # an error. Match the pre-Phase-4 behavior: 0/1 are normal exit
    # codes; only the others surface as errors. A FileNotFoundError
    # from a missing binary now appears as a non-zero exit + stderr
    # mentioning "ast-grep: command not found" or similar.
    if result.exit_code not in (0, 1):
        return (
            f"Error: ast-grep exit {result.exit_code}: "
            f"{result.stderr.strip()[:400]}"
        )

    matches: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        # `--json=stream` emits one object per match (when matches exist),
        # OR one array per file. Normalize both.
        if isinstance(obj, list):
            matches.extend(obj)
        else:
            matches.append(obj)

    if not matches:
        return f"No matches for pattern {pattern!r} in lang={language}."

    out = [f"Found {len(matches)} match(es) for pattern {pattern!r}:"]
    for m in matches[:_MAX_AST_MATCHES]:
        path_match = m.get("file", "?")
        rng = m.get("range", {})
        start = rng.get("start", {})
        text_match = (m.get("text") or "").strip().replace("\n", " ")
        if len(text_match) > 120:
            text_match = text_match[:117] + "..."
        out.append(
            f"  {path_match}:{start.get('line', '?')}:{start.get('column', '?')}  {text_match}"
        )
    if len(matches) > _MAX_AST_MATCHES:
        out.append(f"  ... and {len(matches) - _MAX_AST_MATCHES} more (truncated)")
    return "\n".join(out)


def grep(repo: Repo, pattern: str, path_glob: str = "") -> str:
    """Plain regex grep via `git grep -E` — searches the working tree.

    Cap on output to avoid blowing the agent's context. Returns "no
    matches" cleanly rather than as an error.
    """
    cmd = f"git grep -n -E {shlex.quote(pattern)}"
    if path_glob:
        cmd += f" -- {shlex.quote(path_glob)}"
    result = repo.exec(cmd, timeout=_GREP_TIMEOUT_S)
    # git grep exits 1 when there are no matches; 0 means matches; >1
    # is a real error. Match the pre-Phase-4 wrapper behavior.
    if result.exit_code == 1:
        return f"No matches for pattern {pattern!r}."
    if result.exit_code != 0:
        return (
            f"Error: git grep exit {result.exit_code}: "
            f"{result.stderr.strip()[:400]}"
        )
    lines = result.stdout.splitlines()
    if len(lines) > _MAX_GREP_LINES:
        return (
            "\n".join(lines[:_MAX_GREP_LINES])
            + f"\n... and {len(lines) - _MAX_GREP_LINES} more (truncated)"
        )
    return result.stdout.rstrip("\n")


def bash(repo: Repo, command: str, timeout_s: int = _BASH_TIMEOUT_S) -> str:
    """Run a shell command in the repo. cwd locked to repo root.

    The general-purpose escape hatch — covers anything the typed
    wrappers (read_file_section / ast_search / grep / write_file)
    don't fit. Composes pipelines, runs `git`, `find`, `head`/`tail`,
    `jq`, `python -c`, and so on.

    Phase 4: this proxies into the sandbox via Repo.exec. The blast
    radius is now a per-review Daytona sandbox (when SANDBOX_BACKEND=
    daytona) or a local tempdir (LocalRepo).
    """
    result = repo.exec(command, timeout=timeout_s)

    parts: list[str] = []
    if result.stdout:
        parts.append(result.stdout.rstrip("\n"))
    if result.stderr:
        parts.append(f"--- stderr ---\n{result.stderr.rstrip(chr(10))}")
    out = "\n".join(parts) if parts else f"(no output, exit={result.exit_code})"
    if result.exit_code != 0:
        out = f"[exit {result.exit_code}]\n" + out
    if len(out) > _MAX_BASH_OUTPUT_CHARS:
        out = out[:_MAX_BASH_OUTPUT_CHARS] + (
            f"\n... (truncated; total {len(out):,} chars)"
        )
    return out


def write_file(repo: Repo, path: str, content: str) -> str:
    """Write content to repo/path. Creates parent directories.

    Used as scratch space (notes the agent wants to remember between
    turns) or to write a script the agent then executes via bash. The
    filesystem-as-context pattern from Manus / Lance Martin.

    Phase 4 routes through `Repo.upload_bytes`, which avoids escaping
    a heredoc through the shell. Path traversal is the backend's
    responsibility — both implementations reject any remote_path that
    escapes the repo root.
    """
    try:
        repo.upload_bytes(content.encode("utf-8"), path)
    except PermissionError as e:
        return f"Error: {e}"
    except Exception as e:  # noqa: BLE001 — boundary; surface to model
        return f"Error writing {path} ({type(e).__name__}): {e}"
    return f"Wrote {len(content):,} chars to {path}"


def build_review_context(repo: Repo, base_ref: str, head_ref: str) -> str:
    """ODIS-as-a-tool: same algorithm as `shared.odis.build_context`,
    exposed for the agent to call when it wants the curated slice.

    Phase 4 invokes the ODIS CLI (`python -m shared.odis_cli BASE..HEAD`)
    inside the sandbox so the algorithm runs next to the repo. The
    Daytona image bakes the `shared/` package at /opt/code-review-agent
    with PYTHONPATH set; LocalRepo seeds the same env in `exec`.

    Recommended as the first investigation step — 1-5 KB of context
    surfaces most boundary bugs immediately.
    """
    cmd = (
        f"python -m shared.odis_cli "
        f"{shlex.quote(base_ref)}..{shlex.quote(head_ref)}"
    )
    # NB: the ".." in BASE..HEAD must NOT be quoted; that's why we
    # quote each ref individually.
    result = repo.exec(cmd, timeout=_ODIS_TIMEOUT_S)
    if not result.ok:
        return (
            f"Error: build_review_context failed (exit {result.exit_code}): "
            f"{result.stderr.strip() or '(no stderr)'}"
        )
    return result.stdout


# --------------------------------------------------------------------------- #
# Tool schemas for the Anthropic Client SDK (`tools=[...]`).
# Agent SDK (Phase 2.x) wraps the same callables via the @tool decorator.
# Schemas are unchanged from pre-Phase-4 — the model sees the same surface.
# --------------------------------------------------------------------------- #

READ_FILE_SECTION_TOOL: dict[str, Any] = {
    "name": "read_file_section",
    "description": (
        "Read a range of lines from a file in the repo. Use when the ODIS "
        "context didn't include the code you need to see."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path relative to the repo root.",
            },
            "start_line": {
                "type": "integer",
                "description": "1-indexed start line (inclusive).",
            },
            "end_line": {
                "type": "integer",
                "description": "1-indexed end line (inclusive).",
            },
        },
        "required": ["path", "start_line", "end_line"],
    },
}

AST_SEARCH_TOOL: dict[str, Any] = {
    "name": "ast_search",
    "description": (
        "Structural code search via ast-grep. Pattern uses code syntax with "
        "$VAR for a single node and $$$ for a sequence. Examples: "
        "`add($$$)` (any call to add); `def $NAME($$$): $$$` (any function "
        "definition); `class $X($Foo): $$$` (any class inheriting from Foo). "
        "Returns up to 30 matches with file:line:col. "
        "For non-trivial patterns, read `shared/skills/ast_grep.md` first."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "ast-grep pattern; uses $VAR and $$$.",
            },
            "language": {
                "type": "string",
                "enum": ["python", "javascript", "typescript", "go", "rust", "java"],
                "default": "python",
            },
        },
        "required": ["pattern"],
    },
}

GREP_TOOL: dict[str, Any] = {
    "name": "grep",
    "description": (
        "Plain extended-regex search via `git grep -E`. Use for non-AST "
        "queries (comments, error strings, configs). Returns up to 50 lines "
        "as `path:line: text`."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "POSIX extended regex.",
            },
            "path_glob": {
                "type": "string",
                "description": "Optional pathspec, e.g. `*.py` or `src/*`.",
                "default": "",
            },
        },
        "required": ["pattern"],
    },
}

BASH_TOOL: dict[str, Any] = {
    "name": "bash",
    "description": (
        "Run a shell command inside the repo. cwd is locked to the repo "
        "directory; 15-second timeout. Use this for anything the typed "
        "wrappers don't fit: composed pipelines, `git log`/`git show`, "
        "`find`, `head`/`tail`, `jq`, `python -c`, running scripts you "
        "wrote with write_file, etc. Returns combined stdout+stderr "
        "(stderr labeled). Output truncated past 8000 chars."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to run (passed to `bash -c`).",
            },
        },
        "required": ["command"],
    },
}

WRITE_FILE_TOOL: dict[str, Any] = {
    "name": "write_file",
    "description": (
        "Write text content to a file relative to the repo root. Creates "
        "parent directories as needed. Use for scratch notes (track what "
        "you've checked between turns) or to write a script you'll then "
        "execute via bash. Filesystem-as-memory pattern."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path relative to the repo root.",
            },
            "content": {
                "type": "string",
                "description": "Full file content (overwrites if exists).",
            },
        },
        "required": ["path", "content"],
    },
}

BUILD_REVIEW_CONTEXT_TOOL: dict[str, Any] = {
    "name": "build_review_context",
    "description": (
        "Build a curated review context for a git diff: the unified diff "
        "plus one-hop callers and callees of the changed symbols (the "
        "ODIS algorithm). HIGHLY RECOMMENDED as your first action — "
        "cheap (~1-5 KB), surfaces most boundary bugs (signature changes "
        "with un-updated callers) immediately. Pass the refs from the "
        "user prompt."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "base_ref": {
                "type": "string",
                "description": "Git ref before the change (e.g. 'HEAD~1' or 'main').",
            },
            "head_ref": {
                "type": "string",
                "description": "Git ref after the change (e.g. 'HEAD').",
            },
        },
        "required": ["base_ref", "head_ref"],
    },
}

INVESTIGATION_TOOLS: list[dict[str, Any]] = [
    BUILD_REVIEW_CONTEXT_TOOL,   # listed first — recommended first step
    BASH_TOOL,
    READ_FILE_SECTION_TOOL,
    AST_SEARCH_TOOL,
    GREP_TOOL,
    WRITE_FILE_TOOL,
]
