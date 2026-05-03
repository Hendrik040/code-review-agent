"""Finding dataclass + JSON serialization.

A Finding is what a reviewer (Client SDK or Agent SDK) emits per detected
bug. The shape is identical across both implementations so compare.py and
the Phase 3 evaluator can treat their outputs interchangeably.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

CATEGORIES: tuple[str, ...] = (
    "contract-mismatch",
    "logic",
    "concurrency",
    "resource",
    "error",
    "security",
    "other",
)

SEVERITIES: tuple[str, ...] = ("high", "medium", "low")


@dataclass(frozen=True)
class Finding:
    file: str            # path relative to repo root
    line: int            # primary line; 1-indexed
    category: str        # one of CATEGORIES
    severity: str        # one of SEVERITIES
    summary: str         # one-line headline
    detail: str          # 2-4 sentences explaining the bug
    line_end: int | None = None
    suggested_fix: str = ""  # diff-format snippet; may be empty


def to_json(findings: list[Finding]) -> str:
    return json.dumps([asdict(f) for f in findings], indent=2)


def from_json(text: str) -> list[Finding]:
    return [Finding(**item) for item in json.loads(text)]


def to_dict_list(findings: list[Finding]) -> list[dict[str, Any]]:
    return [asdict(f) for f in findings]
