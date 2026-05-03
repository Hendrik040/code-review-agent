"""Low-level text helpers shared by trace_extract.py.

Extracted to keep trace_extract.py under the 200-LOC budget when
extract_trail_for_finding was added (per-finding attribution heuristic).
"""

from __future__ import annotations

import re

# Matches internal absolute paths that should not leak into user-visible text.
ABS_PATH_RE = re.compile(
    r"(?:/Users/[^\s]*/|/tmp/(?:[^\s]*/)?|/var/[^\s]*/)([^\s/]+)"
)


def sanitize_bash_cmd(cmd: str, *, max_len: int = 80) -> str:
    """Replace internal absolute paths with <…>/basename; truncate to max_len."""
    sanitized = ABS_PATH_RE.sub(r"<…>/\1", cmd)
    return sanitized if len(sanitized) <= max_len else sanitized[:max_len - 1] + "…"
