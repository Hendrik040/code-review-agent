"""Route the pilot bugs with Jev and score triage against all-Opus.

Routing uses shared/routing.py and shared/jev.py exactly as committed on
claude/jev-model-routing (ROUTING_REV below), loaded with `git show`, so
this branch needs no router code of its own. The diff Jev sees is built by
that code from the bug's introducing commit, with the commit subject as
the pull request title.

Scoring needs no new reviews: every bug already has a stored result for
every tier, so a routed setup takes, per bug, the result and cost of the
tier it was routed to.

  light    -> Haiku 5.5 medium sweep
  standard -> Sonnet 5.5 high sweep
  deep     -> stored May Opus 4.7 sweep (max, and high as a variant)

Both pilot runs are scored: this branch's sweeps ("local") and the run
pushed to bench/model-tiers-pilot ("cloud", CLOUD_REV below).

Usage:
    uv pip install "typesafe-sdk>=0.7.0"     # Jev client, Python 3.11+
    uv run python bugsinpy_bench/scripts/route_and_score.py           # route + score
    uv run python bugsinpy_bench/scripts/route_and_score.py --score-only

Writes bugsinpy_bench/routing/routes_pilot30.json and triage_scores.json.
Needs TYPESAFE_API_KEY (in .env) for routing; --score-only does not.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shlex
import subprocess
import sys
import tempfile
import types
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BENCH = ROOT / "bugsinpy_bench"
OUT = BENCH / "routing"
PREPARED = BENCH / "dataset" / "prepared_pilot30.json"
RESULTS = BENCH / "results"

ROUTING_REV = "3e69e01"  # claude/jev-model-routing, router code used
CLOUD_REV = "332fe11"  # bench/model-tiers-pilot, the other pilot run

GROUPS = {
    "found_low": "keras#13 scrapy#4 luigi#2 matplotlib#25 pandas#104 PySnooper#3 "
    "cookiecutter#4 thefuck#9 tornado#13 tqdm#4",
    "found_high_or_max": "pandas#26 keras#3 thefuck#1 tqdm#2 luigi#5 matplotlib#23 "
    "sanic#1 scrapy#37 pandas#30 keras#32",
    "never_found": "pandas#6 scrapy#2 thefuck#7 black#1 keras#4 luigi#4 matplotlib#6 "
    "tornado#4 ansible#3 fastapi#8",
}
GROUP_OF = {label: g for g, s in GROUPS.items() for label in s.split()}


def _git_show(rev: str, path: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{rev}:{path}"],
        check=True, capture_output=True, text=True,
    ).stdout


def load_router():
    """Import shared.routing from ROUTING_REV without touching this tree."""
    pkg = types.ModuleType("shared")
    pkg.__path__ = []
    saved = sys.modules.get("shared")
    sys.modules["shared"] = pkg
    try:
        for name in ("jev", "routing"):
            spec = importlib.util.spec_from_loader(f"shared.{name}", loader=None)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[f"shared.{name}"] = mod
            setattr(pkg, name, mod)
            exec(_git_show(ROUTING_REV, f"shared/{name}.py"), mod.__dict__)
        return sys.modules["shared.routing"]
    finally:
        if saved is not None:
            sys.modules["shared"] = saved


@dataclass
class _Res:
    exit_code: int
    stdout: str
    stderr: str


class _Checkout:
    """The two-method slice of sandbox.repo.Repo that routing.build_state uses."""

    def __init__(self, path: str):
        self.path = path

    def exec(self, cmd: str, timeout: int = 60) -> _Res:
        p = subprocess.run(cmd, shell=True, cwd=self.path, capture_output=True,
                           text=True, timeout=timeout)
        return _Res(p.returncode, p.stdout, p.stderr)


def route_all() -> list[dict]:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    routing = load_router()
    default = routing.Tier("deep", "claude-opus-4-7", "max")
    rows = []
    for e in json.loads(PREPARED.read_text()):
        head = e["introducing_commit"]
        msg = (e.get("introducer_message") or "").strip()
        title = msg.splitlines()[0] if msg else None
        with tempfile.TemporaryDirectory(prefix="route-") as d:
            subprocess.run(
                "git init -q && "
                f"git remote add origin {shlex.quote(e['github_url'])} && "
                f"git -c protocol.version=2 fetch -q --depth 2 --no-tags origin {shlex.quote(head)} && "
                f"git checkout -q {shlex.quote(head)}",
                shell=True, cwd=d, check=True, capture_output=True,
            )
            dec = routing.route(_Checkout(d), f"{head}^", head, default=default, title=title)
        row = {
            "label": f"{e['project']}#{e['bug_id']}",
            "title": title,
            "tier": dec.tier.name,
            "source": dec.source,
            "reason": dec.reason,
            "depth_probs": [round(p, 4) for p in dec.depth_probs],
            "high_stakes": None if dec.high_stakes is None else round(dec.high_stakes, 4),
        }
        rows.append(row)
        print(f"{row['label']:16s} {row['tier']:9s} {row['reason']}", flush=True)
    return rows


def _sweep(suite_md: str, judged_json: str) -> dict[str, tuple[bool, float]]:
    cost = {}
    for line in suite_md.splitlines():
        c = [x.strip() for x in line.split("|")]
        if len(c) > 10 and "#" in c[1] and c[1] != "entry":
            cost[c[1]] = float(c[4].lstrip("$"))
    hit = {v["label"]: bool(v["target_recall"]) for v in json.loads(judged_json)["verdicts"]}
    return {label: (hit[label], cost[label]) for label in cost}


def _local(name: str):
    d = RESULTS / name
    return _sweep((d / "suite.md").read_text(), (d / "judged.json").read_text())


def _cloud(name: str):
    p = f"bugsinpy_bench/results/{name}"
    return _sweep(_git_show(CLOUD_REV, f"{p}/suite.md"), _git_show(CLOUD_REV, f"{p}/judged.json"))


def score(routes: list[dict]) -> dict:
    tier = {r["label"]: r["tier"] for r in routes}
    labels = list(tier)
    arms = {
        "opus_max": _local("sweep_2026-05-04_agent_max"),
        "opus_high": _local("sweep_2026-05-04_agent_high"),
    }
    for run, load in (("local", _local), ("cloud", _cloud)):
        arms[f"sonnet_{run}"] = load("sweep_2026-11-26_sonnet55_high_pilot30")
        arms[f"haiku_{run}"] = load("sweep_2026-11-26_haiku55_medium_pilot30")

    def total(pick) -> dict:
        found = sum(arms[pick(lb)][lb][0] for lb in labels)
        cost = sum(arms[pick(lb)][lb][1] for lb in labels)
        return {"found": found, "of": len(labels), "cost_usd": round(cost, 4)}

    setups = {
        "all_opus_max": total(lambda lb: "opus_max"),
        "all_opus_high": total(lambda lb: "opus_high"),
    }
    for run in ("local", "cloud"):
        setups[f"all_sonnet_{run}"] = total(lambda lb, r=run: f"sonnet_{r}")
        setups[f"all_haiku_{run}"] = total(lambda lb, r=run: f"haiku_{r}")
        for deep in ("max", "high"):
            setups[f"triage_deep_opus_{deep}_{run}"] = total(
                lambda lb, r=run, dp=deep: {
                    "light": f"haiku_{r}", "standard": f"sonnet_{r}", "deep": f"opus_{dp}"
                }[tier[lb]]
            )

    per_bug = []
    for lb in labels:
        row = {"label": lb, "group": GROUP_OF[lb], "tier": tier[lb]}
        for arm, res in arms.items():
            row[arm] = {"found": res[lb][0], "cost_usd": res[lb][1]}
        per_bug.append(row)

    counts = {t: sum(1 for lb in labels if tier[lb] == t) for t in ("light", "standard", "deep")}
    return {
        "routing_rev": ROUTING_REV,
        "cloud_rev": CLOUD_REV,
        "tier_counts": counts,
        "cost_note": "Review costs only. Jev's own cost was not measured.",
        "setups": setups,
        "per_bug": per_bug,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--score-only", action="store_true", help="reuse routes_pilot30.json")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    routes_path = OUT / "routes_pilot30.json"
    if args.score_only:
        routes = json.loads(routes_path.read_text())["routes"]
    else:
        routes = route_all()
        routes_path.write_text(json.dumps(
            {"routing_rev": ROUTING_REV, "deep_default": "claude-opus-4-7:max",
             "risk": 0.15, "routes": routes}, indent=2) + "\n")
    result = score(routes)
    (OUT / "triage_scores.json").write_text(json.dumps(result, indent=2) + "\n")
    for name, s in result["setups"].items():
        print(f"{name:32s} found {s['found']:2d}/{s['of']}  ${s['cost_usd']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
