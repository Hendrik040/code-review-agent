"""Investigation tools the reviewer can call when ODIS context isn't enough.

Three thin wrappers, each importable as a Python function (called from the
reviewer's tool-loop handler) AND as a tool schema dict (passed in
`messages.create(tools=[...])`):

- read_file_section: pure I/O — read N lines of a file
- ast_search: structural code search via the `ast-grep` CLI (must be
  installed; `brew install ast-grep` on macOS, `cargo install ast-grep`
  elsewhere)
- grep: regex search via `git grep` for non-AST queries (comments,
  configs, error strings)

Both reviewers (Client SDK and Agent SDK) use the same implementations.
The Client SDK wraps the schemas in `tools=[{name, description,
input_schema}]`; the Agent SDK in Phase 2.x wraps via the @tool decorator.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

# Cap output at sane sizes so a chatty grep doesn't blow context.
_MAX_AST_MATCHES = 30
_MAX_GREP_LINES = 50
_MAX_BASH_OUTPUT_CHARS = 8000
_AST_TIMEOUT_S = 15
_GREP_TIMEOUT_S = 10
_BASH_TIMEOUT_S = 15


def read_file_section(repo: Path, path: str, start_line: int, end_line: int) -> str:
    """Read [start_line, end_line] (1-indexed, inclusive) from repo/path.

    Returns line-numbered text or a short error string. Never raises — the
    agent loop should never crash because the model passed a bad path.
    """
    target = repo / path
    if not target.exists() or not target.is_file():
        return f"Error: file not found: {path}"
    try:
        rows = target.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        return f"Error reading {path}: {e}"
    start = max(1, start_line) - 1
    end = min(len(rows), max(start_line, end_line))
    if start >= end:
        return f"(empty range {start_line}-{end_line} in {path}; file has {len(rows)} lines)"
    return "\n".join(f"{i:>4}  {rows[i - 1]}" for i in range(start + 1, end + 1))


def ast_search(
    repo: Path,
    pattern: str,
    language: str = "python",
) -> str:
    """Run `ast-grep run -p <pattern> --lang <language>` in the repo.

    Returns a compact text summary of matches (capped at 30) or an error
    string. Pattern syntax: `$VAR` matches a single AST node, `$$$` matches
    any sequence. E.g. `add($$$)` finds every call to `add` regardless of
    arity or whitespace.
    """
    try:
        proc = subprocess.run(
            ["ast-grep", "run", "-p", pattern, "--lang", language, "--json=stream"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=_AST_TIMEOUT_S,
        )
    except FileNotFoundError:
        return "Error: `ast-grep` not installed. macOS: `brew install ast-grep`."
    except subprocess.TimeoutExpired:
        return f"Error: ast-grep timed out after {_AST_TIMEOUT_S}s."

    if proc.returncode not in (0, 1):
        return f"Error: ast-grep exit {proc.returncode}: {proc.stderr.strip()[:400]}"

    matches: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
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


def grep(repo: Path, pattern: str, path_glob: str = "") -> str:
    """Plain regex grep via `git grep -E` — searches the working tree.

    Cap on output to avoid blowing the agent's context. Returns "no matches"
    cleanly rather than as an error.
    """
    cmd = ["git", "grep", "-n", "-E", pattern]
    if path_glob:
        cmd.extend(["--", path_glob])
    try:
        proc = subprocess.run(
            cmd, cwd=repo, capture_output=True, text=True, timeout=_GREP_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return f"Error: git grep timed out after {_GREP_TIMEOUT_S}s."

    if proc.returncode == 1:
        return f"No matches for pattern {pattern!r}."
    if proc.returncode != 0:
        return f"Error: git grep exit {proc.returncode}: {proc.stderr.strip()[:400]}"

    lines = proc.stdout.splitlines()
    if len(lines) > _MAX_GREP_LINES:
        return (
            "\n".join(lines[:_MAX_GREP_LINES])
            + f"\n... and {len(lines) - _MAX_GREP_LINES} more (truncated)"
        )
    return proc.stdout.rstrip("\n")


def bash(repo: Path, command: str, timeout_s: int = _BASH_TIMEOUT_S) -> str:
    """Run a shell command in the repo. cwd locked to `repo`, timeout-bounded.

    The general-purpose escape hatch — covers anything the typed
    wrappers (read_file_section / ast_search / grep / write_file) don't
    fit. Composes pipelines, runs `git`, `find`, `head`/`tail`, `jq`,
    `python -c`, and so on.

    Locked to the materialized fixture's temp directory in tests. For
    Phase 4 (Daytona) this is replaced by a sandbox call; for Phase 5
    (real PRs) the cwd is the cloned repo. The blast radius today is
    one throwaway temp dir per run.
    """
    try:
        proc = subprocess.run(
            ["bash", "-c", command],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return f"Error: bash timed out after {timeout_s}s."

    parts: list[str] = []
    if proc.stdout:
        parts.append(proc.stdout.rstrip("\n"))
    if proc.stderr:
        parts.append(f"--- stderr ---\n{proc.stderr.rstrip(chr(10))}")
    out = "\n".join(parts) if parts else f"(no output, exit={proc.returncode})"
    if proc.returncode != 0:
        out = f"[exit {proc.returncode}]\n" + out
    if len(out) > _MAX_BASH_OUTPUT_CHARS:
        out = out[:_MAX_BASH_OUTPUT_CHARS] + (
            f"\n... (truncated; total {len(out):,} chars)"
        )
    return out


def write_file(repo: Path, path: str, content: str) -> str:
    """Write content to repo/path. Creates parent directories.

    Used as scratch space (notes the agent wants to remember between
    turns) or to write a script the agent then executes via bash. The
    filesystem-as-context pattern from Manus / Lance Martin.
    """
    target = repo / path
    if target.is_absolute() and not str(target).startswith(str(repo)):
        return f"Error: write_file path must be relative to repo root."
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as e:
        return f"Error writing {path}: {e}"
    return f"Wrote {len(content):,} chars to {path}"


def build_review_context(repo: Path, base_ref: str, head_ref: str) -> str:
    """ODIS-as-a-tool: same algorithm as `shared.odis.build_context`,
    exposed for the agent to call when it wants the curated slice.

    Recommended as the first investigation step in the user prompt — it
    surfaces boundary bugs (signature changes with un-updated callers)
    in 1-5 KB of context for typical PRs.
    """
    # Local import to avoid circular-import paranoia at module load.
    from shared.odis import build_context
    return build_context(repo, base_ref, head_ref)


# --------------------------------------------------------------------------- #
# Tool schemas for the Anthropic Client SDK (`tools=[...]`).
# Agent SDK (Phase 2.x) wraps the same callables via the @tool decorator.
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
