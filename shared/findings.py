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


# --------------------------------------------------------------------------- #
# Canonical `submit_findings` tool — shape used by both reviewers.
# Client SDK wraps this in `tools=[{name, description, input_schema}]`.
# Agent SDK wraps it via `@tool(name, description, input_types_dict)`.
# Keep the schema in sync with the Finding dataclass above.
# --------------------------------------------------------------------------- #

SUBMIT_FINDINGS_TOOL_NAME = "submit_findings"

SUBMIT_FINDINGS_TOOL_DESCRIPTION = (
    "Submit your list of bug findings. Call this exactly once at the end "
    "of your review. Pass an empty list if you found no real bugs."
)

SUBMIT_FINDINGS_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "description": "Bug findings. Empty list if no bugs found.",
            "items": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Path of the changed file containing the bug, relative to repo root.",
                    },
                    "line": {
                        "type": "integer",
                        "description": "1-indexed line in the changed file where the bug occurs.",
                    },
                    "line_end": {
                        "type": ["integer", "null"],
                        "description": "Optional end line for multi-line bugs. Null if single line.",
                    },
                    "category": {
                        "type": "string",
                        "enum": list(CATEGORIES),
                    },
                    "severity": {
                        "type": "string",
                        "enum": list(SEVERITIES),
                    },
                    "summary": {"type": "string"},
                    "detail": {"type": "string"},
                    "suggested_fix": {
                        "type": "string",
                        "description": "Short unified diff snippet if you have a concrete fix; empty string otherwise.",
                    },
                },
                "required": [
                    "file", "line", "category", "severity",
                    "summary", "detail", "suggested_fix",
                ],
            },
        },
    },
    "required": ["findings"],
}
