"""Pick the latest run per fixture per SDK, apply the current matcher,
and emit the head-to-head comparison table.

The suite_*.md history is fragmented across partial sweeps and one-off
re-runs (e.g. when sentry_80528's v1 baseline was patched, that fixture
got a fresh run while others didn't). This script extracts the canonical
"latest run per fixture" view from the per-run JSON in
\`<sdk>_sdk/results/run_NNN.txt\`, applies the current category-aware
matcher (`scripts/run_suite.py:_expected_match`), and writes a single
side-by-side markdown table.

Usage:
    uv run python scripts/headtohead.py
    uv run python scripts/headtohead.py --line-tolerance 5
    uv run python scripts/headtohead.py --output docs/headtohead.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_suite import _expected_match  # noqa: E402
from shared.findings import Finding  # noqa: E402
from shared.fixtures import ALL_FIXTURES  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SDKS = ("client", "agent")
_FIX_RE = re.compile(r"fixture-(?P<name>[^-]+(?:_[^-]+)*)-")


def _latest_run_for(sdk: str, fixture_name: str) -> Path | None:
    """Return the highest-numbered run_NNN.txt that materialized this fixture.

    Each run_NNN.txt has a `# repo: /tmp/.../fixture-<name>-<rand>` header
    we use to associate runs with fixtures.
    """
    runs_dir = PROJECT_ROOT / f"{sdk}_sdk" / "results"
    candidates: list[tuple[int, Path]] = []
    for path in runs_dir.glob("run_*.txt"):
        m = re.match(r"run_(\d+)\.txt$", path.name)
        if not m:
            continue
        # Cheap header read.
        try:
            head = path.read_text().splitlines()[:5]
        except OSError:
            continue
        for line in head:
            if line.startswith("# repo:") and f"fixture-{fixture_name}-" in line:
                candidates.append((int(m.group(1)), path))
                break
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1][1]


def _parse_run(path: Path) -> dict | None:
    """Pull turns / cost / findings out of a run_NNN.txt."""
    text = path.read_text()
    head, _, tail = text.partition("# ---")

    def _hdr(prefix: str) -> str | None:
        for line in head.splitlines():
            if line.startswith(prefix):
                return line.split(":", 1)[1].strip()
        return None

    turns = _hdr("# turns:")
    # Cost line names differ between SDKs:
    # Client SDK: "# cost (USD, API rate):"
    # Agent  SDK: "# cost (USD, harness-reported):"
    cost_str = None
    for line in head.splitlines():
        if line.startswith("# cost ") and cost_str is None:
            cost_str = line.split(":", 1)[1].strip()
    findings: list[Finding] = []
    if tail.strip():
        try:
            for item in json.loads(tail.strip()):
                findings.append(Finding(**item))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    return {
        "run_id": int(re.match(r"run_(\d+)", path.stem).group(1)),
        "num_turns": int(turns) if turns and turns.isdigit() else 0,
        "cost_usd": float(cost_str) if cost_str else 0.0,
        "findings": findings,
    }


def _row_for(fixture_name: str, sdk: str, line_tolerance: int) -> dict:
    fixture = next((f for f in ALL_FIXTURES if f.name == fixture_name), None)
    path = _latest_run_for(sdk, fixture_name)
    if fixture is None or path is None:
        return {
            "sdk": sdk,
            "run_id": None,
            "num_turns": 0,
            "cost_usd": 0.0,
            "num_findings": 0,
            "file_hit": False,
            "line_hit": False,
        }
    parsed = _parse_run(path)
    file_hit, line_hit = _expected_match(
        parsed["findings"], fixture.expected, line_tolerance
    )
    return {
        "sdk": sdk,
        "run_id": parsed["run_id"],
        "num_turns": parsed["num_turns"],
        "cost_usd": parsed["cost_usd"],
        "num_findings": len(parsed["findings"]),
        "file_hit": file_hit,
        "line_hit": line_hit,
    }


def _hit_str(file_hit: bool, line_hit: bool) -> str:
    return f"{'Y' if file_hit else 'N'}/{'Y' if line_hit else 'N'}"


def _markdown(line_tolerance: int) -> str:
    lines: list[str] = [
        "# Client SDK vs Agent SDK — head-to-head",
        "",
        f"Latest run per fixture, current category-aware matcher, "
        f"line tolerance ±{line_tolerance}. Hit format: file_hit / line_hit.",
        "",
        "| fixture | client turns | client cost | client F/L | agent turns | agent cost | agent F/L |",
        "|---|---:|---:|:---:|---:|---:|:---:|",
    ]
    totals = {sdk: {"cost": 0.0, "turns": 0, "file": 0, "line": 0} for sdk in SDKS}
    n_fixtures = 0
    for fx in ALL_FIXTURES:
        client = _row_for(fx.name, "client", line_tolerance)
        agent = _row_for(fx.name, "agent", line_tolerance)
        n_fixtures += 1
        for sdk_row, sdk in [(client, "client"), (agent, "agent")]:
            totals[sdk]["cost"] += sdk_row["cost_usd"]
            totals[sdk]["turns"] += sdk_row["num_turns"]
            totals[sdk]["file"] += int(sdk_row["file_hit"])
            totals[sdk]["line"] += int(sdk_row["line_hit"])
        lines.append(
            f"| {fx.name} | "
            f"{client['num_turns']} | ${client['cost_usd']:.4f} | "
            f"{_hit_str(client['file_hit'], client['line_hit'])} | "
            f"{agent['num_turns']} | ${agent['cost_usd']:.4f} | "
            f"{_hit_str(agent['file_hit'], agent['line_hit'])} |"
        )
    lines.append(
        f"| **Totals** | **{totals['client']['turns']}** | "
        f"**${totals['client']['cost']:.4f}** | "
        f"**{totals['client']['file']}/{n_fixtures} f, "
        f"{totals['client']['line']}/{n_fixtures} l** | "
        f"**{totals['agent']['turns']}** | "
        f"**${totals['agent']['cost']:.4f}** | "
        f"**{totals['agent']['file']}/{n_fixtures} f, "
        f"{totals['agent']['line']}/{n_fixtures} l** |"
    )
    cost_delta = (
        100.0
        * (totals["agent"]["cost"] - totals["client"]["cost"])
        / max(totals["client"]["cost"], 1e-6)
    )
    lines.append("")
    lines.append(
        f"**Cost delta:** Agent SDK total = ${totals['agent']['cost']:.4f} vs "
        f"Client SDK total = ${totals['client']['cost']:.4f} "
        f"({cost_delta:+.1f}%)."
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--line-tolerance", type=int, default=10)
    ap.add_argument(
        "--output",
        default="",
        help="Write to this path. Default: stdout.",
    )
    args = ap.parse_args()
    out = _markdown(args.line_tolerance)
    if args.output:
        Path(args.output).write_text(out)
        print(f"Wrote {args.output}")
    else:
        print(out)


if __name__ == "__main__":
    main()
