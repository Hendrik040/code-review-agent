"""Which bench entries get a different context under impact selection?

For every BugsInPy entry (pilot30 + rest70) and Martian PR, materialize the
repo exactly as the sweeps do, run `odis_cli collect`, and ask
`impact_select.decide` in cap mode (no Jev, no spend) whether the context
would change: tiers set (impact section over budget) or drop_changed.
Writes bench_impact/affected.json.
"""
from __future__ import annotations

import dataclasses
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bugsinpy_bench" / "scripts"))

from shared import impact_select  # noqa: E402
from shared.fixtures import materialize_pr, materialize_upstream  # noqa: E402


def probe(repo, base, head) -> dict:
    tok = secrets.token_hex(8)
    r = repo.exec(f"python -m shared.odis_cli collect {tok} {base}..{head}", timeout=600)
    repo.exec(f"rm -rf .git/odis", timeout=30)
    if not r.ok:
        return {"error": r.stderr.strip()[-300:]}
    doc = json.loads(r.stdout.rstrip().splitlines()[-1])
    cfg = dataclasses.replace(impact_select.load_config(), mode="cap")
    dec, log = impact_select.decide(doc, cfg)
    sizes = sum(c["size"] for c in doc["candidates"])
    return {
        "candidates": len(doc["candidates"]), "impact_chars": sizes,
        "diff_chars": len(doc["diff"]), "changed_chars": doc["changed_chars"],
        "affected": dec["tiers"] is not None or dec["drop_changed"],
        "drop_changed": dec["drop_changed"], "tiers": log["tiers"],
    }


def main() -> None:
    out_path = ROOT / "bench_impact" / "affected.json"
    out = json.loads(out_path.read_text()) if out_path.exists() else {}
    jobs = []
    for f in ("prepared_pilot30.json", "prepared_rest70.json"):
        d = json.loads((ROOT / "bugsinpy_bench/dataset" / f).read_text())
        for e in d["entries"] if isinstance(d, dict) else d:
            jobs.append(("bugsinpy", f"{e['project']}#{e['bug_id']}", e))
    m = json.loads((ROOT / "martian_bench/dataset/prepared_martian.json").read_text())
    for e in m["entries"] if isinstance(m, dict) else m:
        jobs.append(("martian", e["pr_url"], e))
    for bench, label, e in jobs:
        key = f"{bench}:{label}"
        if key in out:
            continue
        try:
            if bench == "bugsinpy":
                head = e["introducing_commit"] if e["source"] == "blame" else e["fixed_commit"]
                patch = None
                if e["source"] == "synthetic_revert":
                    patch = (ROOT / "bugsinpy_bench/dataset/bugsinpy/projects" / e["project"]
                             / "bugs" / str(e["bug_id"]) / "bug_patch.txt").read_text()
                cm = materialize_upstream(e["github_url"], head, reverse_patch=patch,
                                          name=f"scan-{e['project']}-{e['bug_id']}")
            else:
                cm = materialize_pr(e["github_url"], e["base_sha"], e["head_sha"], name="scan-martian")
            with cm as (repo, base, head_ref):
                out[key] = probe(repo, base, head_ref)
        except Exception as ex:  # noqa: BLE001
            out[key] = {"error": f"{type(ex).__name__}: {ex}"[:300]}
        out_path.write_text(json.dumps(out, indent=1))
        print(key, out[key].get("affected", out[key].get("error")), flush=True)


if __name__ == "__main__":
    main()
