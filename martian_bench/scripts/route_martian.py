"""Route Martian's 10 Sentry PRs with Jev, using the same router code as BugsInPy.

The router (shared/routing.py at ROUTING_REV on claude/jev-model-routing) is
loaded by bugsinpy_bench/scripts/route_and_score.py. Martian entries are real
PRs, so Jev sees `git diff base_sha..head_sha` and the PR title.

Usage:
    uv run python martian_bench/scripts/route_martian.py
Writes martian_bench/routing/routes_martian.json.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "bugsinpy_bench" / "scripts"))

import route_and_score as R  # noqa: E402

PREPARED = ROOT / "martian_bench" / "dataset" / "prepared_martian.json"
OUT = ROOT / "martian_bench" / "routing" / "routes_martian.json"


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    routing = R.load_router()
    default = routing.Tier("deep", "claude-opus-4-7", "max")
    rows = []
    for e in json.loads(PREPARED.read_text()):
        base, head = e["base_sha"], e["head_sha"]
        with tempfile.TemporaryDirectory(prefix="route-martian-") as d:
            subprocess.run(
                "git init -q && "
                f"git remote add origin {shlex.quote(e['github_url'])} && "
                f"git -c protocol.version=2 fetch -q --depth 1 --no-tags origin {shlex.quote(base)} {shlex.quote(head)} && "
                f"git checkout -q {shlex.quote(head)}",
                shell=True, cwd=d, check=True, capture_output=True, timeout=1200,
            )
            dec = routing.route(R._Checkout(d), base, head, default=default, title=e.get("title"))
        label = f"{e['repo_slug']}#{e['pr_number']}"
        row = {
            "label": label,
            "title": e.get("title"),
            "tier": dec.tier.name,
            "source": dec.source,
            "reason": dec.reason,
            "depth_probs": [round(p, 4) for p in dec.depth_probs],
            "high_stakes": None if dec.high_stakes is None else round(dec.high_stakes, 4),
        }
        rows.append(row)
        print(f"{label:48s} {row['tier']:9s} {row['reason']}", flush=True)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"routing_rev": R.ROUTING_REV, "deep_default": "claude-opus-4-7:max",
                               "risk": 0.15, "routes": rows}, indent=2) + "\n")
    print("TIERS", dict(Counter(r["tier"] for r in rows)), "sources", dict(Counter(r["source"] for r in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
