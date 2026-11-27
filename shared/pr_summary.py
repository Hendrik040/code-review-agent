"""Machine summary of what a PR changes (Phase 9, host side, opt-in).

One Haiku call per changed non-test Python file, told to describe the
change and never judge it, merged per PR into
{files, what_changed, behavior_before_after, interfaces_touched,
data_touched, error_handling_changes, usage}. Lifted from
bugsinpy_bench/scripts/router_inputs.py so the reviewer's context and
the router can share one summary per PR (`get` caches by diff).

The review context shows it first, framed as orientation that may be
wrong: on BugsInPy Haiku sometimes described the wrong mechanism, and a
reviewer that trusts it could inherit the error.

Off unless REVIEW_PR_SUMMARY is 1/true/yes/on, so earlier sweeps stay
reproducible. Fail-open: any error (no key, API failure, timeout,
malformed answer) means no summary, never a failed review.

Host only: talks to the Anthropic API; not in _HOST_SHARED_FILES.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("shared.pr_summary")

SUMMARY_MODEL = "claude-haiku-5-5"
MAX_FILES = 10
MAX_FILE_DIFF_CHARS = 24_000
MAX_SECTION_CHARS = 4_000
TIMEOUT_S = 30.0
FRAMING = "What this PR changes (machine summary, may be wrong; verify against the diff)"

SYSTEM = (
    "You describe code changes for a routing system. Describe only what the "
    "diff changes. Never judge it: do not mention bugs, risk, quality, "
    "correctness, style, or whether the change is good or bad. Be concrete "
    "and brief. Use empty lists when a category does not apply."
)

_LIST_KEYS = ("behavior_before_after", "interfaces_touched", "data_touched", "error_handling_changes")

SCHEMA = {
    "type": "object",
    "properties": {
        "what_changed": {"type": "string"},
        **{k: {"type": "array", "items": {"type": "string"}} for k in _LIST_KEYS},
    },
    "required": ["what_changed", *_LIST_KEYS],
    "additionalProperties": False,
}

USER_TEMPLATE = """File: {path}

Diff of this file:
<diff>
{diff}
</diff>

Fill the fields:
- what_changed: 1 or 2 plain sentences.
- behavior_before_after: one "before → after" string per behavior change.
- interfaces_touched: changed function signatures, endpoints, CLI flags or schemas.
- data_touched: stored data read or written differently.
- error_handling_changes: exceptions raised or caught differently."""

_cache: dict[str, dict] = {}


def enabled() -> bool:
    return os.environ.get("REVIEW_PR_SUMMARY", "").strip().lower() in {"1", "true", "yes", "on"}


def clear_cache() -> None:
    _cache.clear()


def split_files(diff: str) -> dict[str, str]:
    """Per-file chunks of a unified diff, keyed by the new path."""
    files: dict[str, str] = {}
    for chunk in re.split(r"(?m)^(?=diff --git )", diff):
        m = re.match(r"diff --git a/(\S+) b/(\S+)", chunk)
        if m:
            files[m.group(2)] = chunk
    return files


def is_source(path: str) -> bool:
    """Non-test Python file."""
    if not path.endswith(".py"):
        return False
    parts = path.split("/")
    name = parts[-1]
    return not (
        {"tests", "test", "testing"} & set(parts)
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def _one_file(client: Any, path: str, file_diff: str, timeout: float) -> tuple[dict, int, int]:
    resp = client.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=1500,
        system=SYSTEM,
        messages=[{"role": "user", "content": USER_TEMPLATE.format(
            path=path, diff=file_diff[:MAX_FILE_DIFF_CHARS])}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        timeout=timeout,
    )
    s = json.loads("".join(b.text for b in resp.content if b.type == "text"))
    if not isinstance(s.get("what_changed"), str) or not all(
        isinstance(s.get(k), list) and all(isinstance(x, str) for x in s[k]) for k in _LIST_KEYS
    ):
        raise ValueError("summary does not match the schema")
    return s, resp.usage.input_tokens, resp.usage.output_tokens


def summarize(diff: str, *, client: Any = None, timeout: float = TIMEOUT_S) -> dict | None:
    """Merged summary of the changed source files, or None (no source
    files, or any failure). Never raises."""
    try:
        src = [(p, d) for p, d in split_files(diff).items() if is_source(p)]
        if not src:
            return None
        if client is None:
            from anthropic import Anthropic
            client = Anthropic()
        deadline = time.monotonic() + timeout
        merged: dict[str, Any] = {"files": [p for p, _ in src], "what_changed": "",
                                  **{k: [] for k in _LIST_KEYS}}
        parts, tin, tout = [], 0, 0
        for path, fd in src[:MAX_FILES]:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"summary missed the {timeout:g}s deadline")
            s, i, o = _one_file(client, path, fd, left)
            tin, tout = tin + i, tout + o
            parts.append(f"{path}: {s['what_changed']}")
            for k in _LIST_KEYS:
                merged[k].extend(s[k])
        if len(src) > MAX_FILES:
            parts.append(f"({len(src) - MAX_FILES} more changed source files not summarized)")
        merged["what_changed"] = "\n".join(parts)
        merged["usage"] = {"calls": min(len(src), MAX_FILES), "input_tokens": tin, "output_tokens": tout}
        return merged
    except Exception as e:  # noqa: BLE001 — the summary must never fail the review
        log.warning("pr_summary: no summary (%s: %s)", type(e).__name__, e)
        return None


def get(diff: str, *, client: Any = None, timeout: float = TIMEOUT_S) -> dict | None:
    """`summarize`, computed once per diff: cached in process and, when
    REVIEW_PR_SUMMARY_CACHE_DIR is set, in <dir>/<sha256>.summary.json so
    the router and the reviewer share it. Failures are not cached."""
    key = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    if key in _cache:
        return _cache[key]
    cache_dir = os.environ.get("REVIEW_PR_SUMMARY_CACHE_DIR", "").strip()
    path = Path(cache_dir) / f"{key}.summary.json" if cache_dir else None
    if path and path.exists():
        try:
            _cache[key] = json.loads(path.read_text())
            return _cache[key]
        except (OSError, ValueError):
            log.warning("pr_summary: unreadable cache file %s; recomputing", path)
    s = summarize(diff, client=client, timeout=timeout)
    if s is not None:
        _cache[key] = s
        if path:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n")
            except OSError:
                log.warning("pr_summary: could not write cache file %s", path)
    return s


def for_repo(repo: Any, base_ref: str, head_ref: str, *, client: Any = None) -> dict | None:
    """Summary of base..head in a sandbox repo, from the same diff ODIS shows."""
    import shlex
    try:
        r = repo.exec(
            f"git diff --unified=3 --no-color {shlex.quote(base_ref)}..{shlex.quote(head_ref)}",
            timeout=60,
        )
        if not r.ok:
            log.warning("pr_summary: git diff failed; no summary")
            return None
        return get(r.stdout, client=client)
    except Exception as e:  # noqa: BLE001
        log.warning("pr_summary: no summary (%s: %s)", type(e).__name__, e)
        return None


def render(s: dict) -> str:
    """The context section. `<` is escaped so summary text cannot close a tag."""
    lines = [s.get("what_changed", "")]
    labels = {"behavior_before_after": "Behavior before → after",
              "interfaces_touched": "Interfaces touched",
              "data_touched": "Data touched",
              "error_handling_changes": "Error handling changes"}
    for k, label in labels.items():
        if s.get(k):
            lines.append(f"{label}:")
            lines.extend(f"- {x}" for x in s[k])
    body = "\n".join(lines).replace("<", "&lt;")
    if len(body) > MAX_SECTION_CHARS:
        body = body[:MAX_SECTION_CHARS] + "\n… (summary truncated)"
    return f"## 0. {FRAMING}\n\n<pr_summary>\n{body}\n</pr_summary>\n"


_TITLE = "# Code Review Context\n"


def prepend(context: str, s: dict) -> str:
    """Insert the section right after the context title (or at the very top)."""
    section = render(s)
    if context.startswith(_TITLE):
        return f"{_TITLE}\n{section}{context[len(_TITLE):]}"
    return f"{section}\n{context}"


def trace_lines(s: dict | None) -> list[str]:
    """What the reviewer trace records about the summary."""
    if s is None:
        return ["--- PR summary (REVIEW_PR_SUMMARY): unavailable, review proceeds without it ---"]
    return ["--- PR summary (REVIEW_PR_SUMMARY, shown first in build_review_context) ---",
            json.dumps(s, indent=2, ensure_ascii=False)]
