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
