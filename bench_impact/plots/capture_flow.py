"""Capture how the context builder decides, for the flow page (flow.html).

For each example bug: check out the reviewed commit in a temporary worktree,
collect ODIS candidates, ask Jev exactly as shared/impact_select.decide does
(same question, batches, thresholds), and record every step: candidates,
Jev's answer per candidate, the tier rule, and the rendered context.
Writes bench_impact/plots/flow_data.json. Needs TYPESAFE_API_KEY (.env).

Usage: .venv/bin/python bench_impact/plots/capture_flow.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from shared import impact, impact_select, odis  # noqa: E402

CLONES = ROOT / "bugsinpy_bench/dataset/upstream_clones"
EXAMPLES = [  # label, repo, introducing commit
    ("PySnooper#3", "PySnooper", "621a4865cc05326fb3f892df2e7c455912860481"),
    ("thefuck#7", "thefuck", "e658f35bd978d39fb4d580c3c62286ab7ec69ec9"),
    ("thefuck#26", "thefuck", "004c0d06ebc875685115d74371fc9cba0ba6df4b"),
    ("luigi#5", "luigi", "be88a318dce06254a66303a1c398ec28f89c60d7"),
]


def capture(label: str, repo: str, commit: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="flow-") as tmp:
        wt = Path(tmp) / "wt"
        subprocess.run(["git", "-C", str(CLONES / repo), "worktree", "add", "-q", "--detach", str(wt), commit], check=True)
        try:
            base, head = commit + "^", commit
            col = odis.collect(wt, base, head)
            untiered = odis.render_markdown(col)
            cands = col.candidates
            sizes = {c.id: len(c.text) for c in cands}
            doc = {"diff": col.diff, "changed_chars": 0, "candidates": [
                {"id": c.id, "size": sizes[c.id], "summary": impact.summary(c),
                 "facts": {k: getattr(c, k) for k in ("same_file_as_change", "imported_by_changed_file", "is_test")}}
                for c in cands]}
            cfg = impact_select.load_config()
            out = {"label": label, "commit": commit[:7], "diff": col.diff, "diff_chars": len(col.diff),
                   "candidates_total": len(cands), "candidate_chars": sum(sizes.values()),
                   "untiered_chars": len(untiered),
                   "config": {"keep": cfg.keep, "mention": cfg.mention, "budget": cfg.budget,
                              "max_signatures": cfg.max_signatures, "context_max": cfg.context_max,
                              "timeout": cfg.timeout, "max_diff_chars": impact_select._MAX_DIFF_CHARS,
                              "max_request_chars": impact_select._MAX_REQUEST_CHARS},
                   "question": impact_select.QUESTION}
            if sum(sizes.values()) <= cfg.budget:
                decisions, record = impact_select.decide(doc, cfg)
                out.update(path="small", scores={}, tiers={c.id: impact.FULL for c in cands}, requests=0, jev_ms=0,
                           deduped=len(cands), note="")
            else:
                objs = impact.dedupe([impact_select._as_candidate(c) for c in doc["candidates"]])
                live = [c for c in doc["candidates"] if c["id"] in {o.id for o in objs}]
                t0 = time.monotonic()
                scores, requests, error = impact_select.score(doc["diff"], live, timeout=cfg.timeout)
                jev_ms = int((time.monotonic() - t0) * 1000)
                tiers = impact.assign_tiers(objs, sizes, scores or None, keep=cfg.keep, mention=cfg.mention,
                                            budget=cfg.budget, max_signatures=cfg.max_signatures)
                note = impact.not_shown_note(objs, tiers, ranked=bool(scores))
                decisions = {"tiers": tiers, "note": note, "drop_changed": False}
                out.update(path="jev" if scores else "fallback", scores=scores, tiers=tiers, requests=requests,
                           jev_ms=jev_ms, error=error, deduped=len(objs), note=note,
                           example_state={"diff": col.diff[:cfg.budget and impact_select._MAX_DIFF_CHARS],
                                          "candidates": {c["id"]: c["summary"] for c in live[:3]}})
            rendered = odis.render_markdown(col, tiers=decisions["tiers"], note=decisions["note"],
                                            drop_changed=decisions["drop_changed"])
            out["rendered"] = rendered
            out["rendered_chars"] = len(rendered)
            # candidates: every scored or shown one, plus the facts the fallback order uses
            keep_ids = set(out["scores"]) | {i for i, t in out["tiers"].items() if t != impact.COUNTED}
            out["candidates"] = [
                {"id": c.id, **impact.summary(c), "size": sizes[c.id],
                 "same_file": c.same_file_as_change, "imported": c.imported_by_changed_file, "is_test": c.is_test,
                 "score": out["scores"].get(c.id), "tier": out["tiers"].get(c.id, "duplicate")}
                for c in cands if c.id in keep_ids or len(cands) <= 60]
            return out
        finally:
            subprocess.run(["git", "-C", str(CLONES / repo), "worktree", "remove", "--force", str(wt)], check=False)


def slim(d: dict, top: int = 24) -> dict:
    """Keep what the page shows: the top-scored candidates, every shown one,
    a score histogram over all scored candidates, and shortened texts."""
    cands = d["candidates"]
    shown = [c for c in cands if c["tier"] in ("full", "signature")]
    ranked = sorted((c for c in cands if c["score"] is not None), key=lambda c: -c["score"])
    keep = {c["id"] for c in shown} | {c["id"] for c in ranked[:top]}
    for c in cands:
        c["line_text"] = (c.get("line_text") or "")[:160]
    bins = [0] * 10
    for c in ranked:
        bins[min(int(c["score"] * 10), 9)] += 1
    counts = {t: list(d["tiers"].values()).count(t) for t in ("full", "signature", "counted")}
    return {**{k: v for k, v in d.items() if k not in ("candidates", "scores", "tiers")},
            "diff": d["diff"][:6000], "rendered": d["rendered"][:12000],
            "tier_counts": counts, "score_histogram": bins, "scored": len(ranked),
            "candidates": sorted((c for c in cands if c["id"] in keep),
                                 key=lambda c: -(c["score"] if c["score"] is not None else -1))}


def main() -> int:
    data = [capture(*e) for e in EXAMPLES]
    for d in data:
        print(d["label"], d["path"], d["candidates_total"], "cands", d["candidate_chars"], "chars ->",
              d["rendered_chars"], "rendered; untiered", d["untiered_chars"], {t: list(d["tiers"].values()).count(t) for t in ("full", "signature", "counted")})
    (Path(__file__).parent / "flow_data.json").write_text(json.dumps([slim(d) for d in data], indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
