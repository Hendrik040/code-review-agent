"""Write one reading bundle per missed bug: the reviewed diff, the maintainer's
fix (buggy..fixed, non-test files), the oracle and the ODIS candidates with the
tier Jev impact selection gives them. bench_impact/missed/bundles/<label>.md"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from shared import impact, impact_select, odis  # noqa: E402

CLONES = ROOT / "bugsinpy_bench/dataset/upstream_clones"
OUT = Path(__file__).parent / "bundles"


def sh(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True).stdout


def bundle(e):
    label = f"{e['project']}#{e['bug_id']}"
    repo = CLONES / e["project"]
    intro = e["introducing_commit"]
    oracle = e["oracle"] if isinstance(e["oracle"], list) else ast.literal_eval(e["oracle"])
    fix_files = sorted({o["file"] for o in oracle})
    fix = sh(repo, "diff", "--unified=5", "--no-color", e["buggy_commit"], e["fixed_commit"], "--", *fix_files)
    with tempfile.TemporaryDirectory(prefix="bundle-") as tmp:
        wt = Path(tmp) / "wt"
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(wt), intro], check=True, capture_output=True)
        try:
            col = odis.collect(wt, intro + "^", intro)
            sizes = {c.id: len(c.text) for c in col.candidates}
            doc = {"diff": col.diff, "changed_chars": 0, "candidates": [
                {"id": c.id, "size": sizes[c.id], "summary": impact.summary(c),
                 "facts": {k: getattr(c, k) for k in ("same_file_as_change", "imported_by_changed_file", "is_test")}}
                for c in col.candidates]}
            decisions, rec = impact_select.decide(doc, impact_select.load_config())
            tiers = decisions["tiers"] or {c.id: "full" for c in col.candidates}
            cands = [(c, tiers.get(c.id, "duplicate")) for c in col.candidates]
        finally:
            subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], capture_output=True)
    shown = [(c, t) for c, t in cands if t in ("full", "signature")]
    lines = [f"# {label}", "", f"Commit message of the reviewed change: {e.get('introducer_message','')}", "",
             f"Oracle (fix location at buggy_commit): {oracle}", "",
             "## Reviewed diff (introducing commit)", "```diff", col.diff[:30000], "```", "",
             "## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)", "```diff", fix[:15000], "```", "",
             f"## ODIS candidates: {len(cands)} total, path={rec['path']}, tiers={rec['tiers']}",
             "Shown to the reviewer (full = whole snippet, signature = one line):"]
    for c, t in shown[:40]:
        lines.append(f"- [{t}] {c.role} {c.file}:{c.line} {c.symbol} | {c.line_text.strip()[:140]}")
        if t == "full":
            lines += ["```python", c.text[:2500], "```"]
    counted = [c for c, t in cands if t == "counted"]
    if counted:
        lines.append(f"Counted only ({len(counted)}), first 15:")
        lines += [f"- {c.role} {c.file}:{c.line} {c.symbol}" for c in counted[:15]]
    OUT.mkdir(exist_ok=True)
    (OUT / f"{label.replace('#', '_')}.md").write_text("\n".join(lines) + "\n")
    return label


def main():
    missed = set(json.loads(Path(sys.argv[1]).read_text())["never_any"])
    P = []
    for f in ("prepared_pilot30.json", "prepared_rest70.json"):
        P += json.loads((ROOT / "bugsinpy_bench/dataset" / f).read_text())
    entries = [e for e in P if f"{e['project']}#{e['bug_id']}" in missed]
    # one worker per project: git worktree add is not safe in parallel on one repo
    by_proj = {}
    for e in entries:
        by_proj.setdefault(e["project"], []).append(e)
    with ThreadPoolExecutor(8) as ex:
        for labels in ex.map(lambda es: [bundle(e) for e in es], by_proj.values()):
            print(*labels)


if __name__ == "__main__":
    main()
