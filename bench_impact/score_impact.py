"""Before vs after the new context builder (Jev impact selection), per model and with triage.

Before = the model-tiers sweeps from bench/model-tiers-pilot-local (copied into
bench_impact/baseline/, judged by claude-sonnet-4-5-20250929). After = the same
results, except that the bugs/PRs whose context changes under impact selection
(bench_impact/affected.json) take the result of this branch's reruns. On every
other entry the context is byte-identical, so the stored result is reused.

Scoring follows bugsinpy_bench/scripts/score_full.py: BugsInPy "found" is the
judge's target_recall, cost comes from suite.md; triage takes per bug the result
of the tier Jev routed it to (light = Haiku 5.5 medium, standard = Sonnet 5.5
high, deep = Opus 5.5 high). Martian is micro recall / precision / F1; a `_tail`
sweep replaces its parent's rows. "Context error" counts reviews whose
build_review_context call returned the Agent SDK's "exceeds maximum allowed
tokens" error instead of a context.

Usage: .venv/bin/python bench_impact/score_impact.py [--traces-before DIR]
Writes bench_impact/impact_scores.json.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "bench_impact" / "baseline"
NEW_B = ROOT / "bugsinpy_bench" / "results"
NEW_M = ROOT / "martian_bench" / "results"
MODELS = ("haiku55_medium", "sonnet55_high", "opus55_high")
TIER = {"light": "haiku55_medium", "standard": "sonnet55_high", "deep": "opus55_high"}
CTX_ERR = "exceeds maximum allowed tokens"


def suite_costs(path: Path) -> dict[str, float]:
    out = {}
    for line in path.read_text().splitlines():
        c = [x.strip() for x in line.split("|")]
        if len(c) > 6 and "#" in c[1] and c[1] != "entry":
            out[c[1]] = float(next(x for x in c[2:] if x.startswith("$")).lstrip("$"))
    return out


def run_ids(sweep: Path) -> dict[str, int]:
    ids = {}
    for f in (sweep / "runs").glob("*.txt"):
        t = f.read_text(errors="ignore")
        lab = re.search(r"^# (?:bug|pr): (.+)$", t, re.M)
        rid = re.search(r"reviewer run (\d+)", t)
        if lab and rid:
            ids[lab.group(1).strip()] = int(rid.group(1))
    return ids


def ctx_error(trace_dir: Path, rid: int | None) -> bool | None:
    if rid is None:
        return None
    p = trace_dir / f"run_{rid:03d}.txt"
    if not p.exists():
        return None
    t = p.read_text(errors="ignore")
    i = t.find("for: mcp__reviewer__build_review_context")
    # Trace previews wrap long lines ("exceeds maximum all\n│ owed tokens"),
    # so compare with whitespace and box-drawing characters removed.
    squashed = re.sub(r"[\s│]+", "", t[i:i + 1500]) if i >= 0 else ""
    return CTX_ERR.replace(" ", "") in squashed if i >= 0 else None


def bugsinpy_arm(sweeps: list[Path], traces: Path) -> dict[str, dict]:
    res = {}
    for s in sweeps:
        cost = suite_costs(s / "suite.md")
        ids = run_ids(s)
        for v in json.loads((s / "judged.json").read_text())["verdicts"]:
            lb = v["label"]
            res[lb] = {"found": bool(v["target_recall"]), "cost_usd": cost[lb],
                       "ctx_error": ctx_error(traces, ids.get(lb))}
    return res


def martian_arm(sweep: Path, traces: Path) -> dict[str, dict]:
    res = {}
    for s in (sweep, sweep.with_name(sweep.name + "_tail")):
        if not s.exists():
            continue
        cost = suite_costs(s / "suite.md")
        ids = run_ids(s)
        for v in json.loads((s / "judged.json").read_text())["verdicts"]:
            lb = v["label"]
            res[lb] = {**{k: v[k] for k in ("n_goldens", "matched_goldens", "n_candidates", "matched_candidates")},
                       "cost_usd": cost[lb], "ctx_error": ctx_error(traces, ids.get(lb))}
    return res


def pr_label(url: str) -> str:
    """https://github.com/<owner>/<repo>/pull/<n> -> <owner>_<repo>#<n> (run_martian's label)."""
    owner, repo, _, n = url.rstrip("/").split("/")[-4:]
    return f"{owner}_{repo}#{n}"


def micro(rows: dict[str, dict]) -> dict:
    g = sum(r["n_goldens"] for r in rows.values()); mg = sum(r["matched_goldens"] for r in rows.values())
    c = sum(r["n_candidates"] for r in rows.values()); mc = sum(r["matched_candidates"] for r in rows.values())
    r, p = (mg / g if g else 0.0), (mc / c if c else 0.0)
    return {"recall": round(r, 4), "precision": round(p, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
            "matched_goldens": mg, "goldens": g, "cost_usd": round(sum(x["cost_usd"] for x in rows.values()), 4),
            "ctx_errors": sum(bool(x["ctx_error"]) for x in rows.values())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces-before", type=Path, required=True,
                    help="agent_sdk/traces of the checkout that ran the baseline sweeps")
    a = ap.parse_args()
    traces_new = ROOT / "agent_sdk" / "traces"
    affected = json.loads((ROOT / "bench_impact" / "affected.json").read_text())
    aff_b = {k.split(":", 1)[1] for k, v in affected.items() if k.startswith("bugsinpy:") and v.get("affected")}
    aff_m_urls = {k.split(":", 1)[1] for k, v in affected.items() if k.startswith("martian:") and v.get("affected")}

    routes = {}
    for f in ("routes_pilot30.json", "routes_rest70.json"):
        for r in json.loads((BASE / "routing" / f).read_text())["routes"]:
            routes[r["label"]] = r["tier"]
    labels = sorted(routes)

    bd = BASE / "bugsinpy"
    before = {m: bugsinpy_arm(sorted(bd.glob(f"sweep_*_{m}_*")), a.traces_before) for m in MODELS}
    after_runs = {m: bugsinpy_arm([NEW_B / f"sweep_2026-11-27_impactsel_{m}_aff16"], traces_new) for m in MODELS}
    rep2 = bugsinpy_arm([NEW_B / "sweep_2026-11-27_impactsel_opus55_high_aff16_rep2"], traces_new)
    aff_run = sorted(set(after_runs["opus55_high"]))  # affected bugs that run_bench reviewed (blame only)
    after = {m: {lb: (after_runs[m][lb] if lb in after_runs[m] else before[m][lb]) for lb in labels} for m in MODELS}

    def total(arm_of, data, subset) -> dict:
        rows = [data[arm_of(lb)][lb] for lb in subset]
        return {"found": sum(r["found"] for r in rows), "of": len(rows),
                "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
                "ctx_errors": sum(bool(r["ctx_error"]) for r in rows)}

    bugsinpy = {"n_bugs": len(labels), "affected_reviewed": aff_run,
                "affected_not_in_sweeps": sorted(aff_b - set(aff_run)), "all": {}, "affected": {}}
    for scope, subset in (("all", labels), ("affected", aff_run)):
        out = bugsinpy[scope]
        for m in MODELS:
            out[f"{m}_before"] = total(lambda lb, m=m: m, before, subset)
            out[f"{m}_after"] = total(lambda lb, m=m: m, after, subset)
        out["triage_before"] = total(lambda lb: TIER[routes[lb]], before, subset)
        out["triage_after"] = total(lambda lb: TIER[routes[lb]], after, subset)
    rep_after2 = {lb: rep2.get(lb, after_runs["opus55_high"][lb]) for lb in aff_run}
    bugsinpy["affected"]["opus55_high_after_rep2"] = {
        "found": sum(rep_after2[lb]["found"] for lb in aff_run), "of": len(aff_run),
        "cost_usd": round(sum(rep_after2[lb]["cost_usd"] for lb in aff_run), 4),
        "ctx_errors": sum(bool(rep_after2[lb]["ctx_error"]) for lb in aff_run)}
    bugsinpy["per_bug_affected"] = [
        {"label": lb, "tier": routes[lb],
         **{f"{m}_before": before[m][lb]["found"] for m in MODELS},
         **{f"{m}_after": after_runs[m][lb]["found"] for m in MODELS},
         "opus55_high_after_rep2": rep2[lb]["found"] if lb in rep2 else None,
         "ctx_error_before": {m: before[m][lb]["ctx_error"] for m in MODELS}}
        for lb in aff_run]

    md = BASE / "martian"
    martian = {}
    for m in MODELS:
        b = martian_arm(md / f"sweep_2026-11-27_martian_{m}", a.traces_before)
        n = martian_arm(NEW_M / f"sweep_2026-11-27_impactsel_martian_{m}_aff6", traces_new)
        aff_labels = {pr_label(u) for u in aff_m_urls} & set(b)
        merged = {lb: (n[lb] if lb in aff_labels and lb in n else b[lb]) for lb in b}
        martian[f"{m}_before"] = micro(b)
        martian[f"{m}_after"] = micro(merged)
        martian[f"{m}_affected_before"] = micro({lb: b[lb] for lb in aff_labels})
        martian[f"{m}_affected_after"] = micro({lb: n[lb] for lb in aff_labels if lb in n})
        martian["affected_labels"] = sorted(aff_labels)
    result = {"bugsinpy": bugsinpy, "martian": martian}
    (ROOT / "bench_impact" / "impact_scores.json").write_text(json.dumps(result, indent=2) + "\n")

    for scope in ("all", "affected"):
        print(f"BugsInPy ({scope}):")
        for k, s in bugsinpy[scope].items():
            print(f"  {k:26s} found {s['found']:3d}/{s['of']:<3d} ${s['cost_usd']:7.2f}  ctx errors {s['ctx_errors']}")
    print("Martian:")
    for k, s in martian.items():
        if isinstance(s, dict):
            print(f"  {k:32s} R {s['recall']:.3f} P {s['precision']:.3f} F1 {s['f1']:.3f}  ${s['cost_usd']:.2f}  ctx errors {s['ctx_errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
