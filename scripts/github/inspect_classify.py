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
