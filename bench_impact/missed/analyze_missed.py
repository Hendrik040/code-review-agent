"""Could the impact context have helped on the bugs every reviewer missed?

For each bug no model found in any run (BugsInPy, all sweeps on this branch),
locate the maintainer's fix (the oracle lines at buggy_commit) relative to the
reviewed change (introducing commit), and check whether ODIS's caller/callee
candidates at the reviewed commit contain the fixed function, and what tier
Jev impact selection gave it.

Classes:
  in_changed_function   the fix is in a function the reviewed diff changed
  in_changed_file       same file as the diff, but a function the diff did not touch
  outside_diff          a file the diff did not touch

Usage: .venv/bin/python bench_impact/missed/analyze_missed.py MISSED_JSON
Writes bench_impact/missed/missed_analysis.json.
"""
from __future__ import annotations

import ast
import json
import re
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


def sh(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout


def enclosing(source: str, line: int) -> str:
    """Qualified name of the innermost def/class containing `line`, '' if module level."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    best, span = "", None

    def walk(node, prefix):
        nonlocal best, span
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{ch.name}"
                end = getattr(ch, "end_lineno", ch.lineno)
                if ch.lineno <= line <= end and (span is None or end - ch.lineno < span):
                    best, span = name, end - ch.lineno
                walk(ch, name + ".")
            else:
                walk(ch, prefix)
    walk(tree, "")
    return best


def changed_functions(repo: Path, commit: str) -> dict[str, set[str]]:
    """file -> qualified names of functions whose lines the commit touched (at the commit)."""
    out: dict[str, set[str]] = {}
    diff = sh(repo, "diff", "--unified=0", "--no-color", f"{commit}^", commit)
    cur = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
            if cur:
                out.setdefault(cur, set())
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if m and cur and cur.endswith(".py"):
            start, n = int(m.group(1)), int(m.group(2) or 1)
            src = sh(repo, "show", f"{commit}:{cur}")
            for ln in range(start, start + max(n, 1)):
                f = enclosing(src, ln)
                if f:
                    out[cur].add(f)
    return out


def analyze(e: dict) -> dict:
    label = f"{e['project']}#{e['bug_id']}"
    repo = CLONES / e["project"]
    intro, buggy = e["introducing_commit"], e["buggy_commit"]
    oracle = e["oracle"] if isinstance(e["oracle"], list) else []
    fixes = []
    for o in oracle:
        src = sh(repo, "show", f"{buggy}:{o['file']}")
        fixes.append({**o, "function": enclosing(src, o["line_start"]) if src else ""})
    changed = changed_functions(repo, intro)
    for f in fixes:
        fn = f["function"]
        if f["file"] in changed and fn and fn in changed[f["file"]]:
            f["class"] = "in_changed_function"
        elif f["file"] in changed:
            f["class"] = "in_changed_file"
        else:
            f["class"] = "outside_diff"
    # ODIS + Jev at the reviewed commit
    with tempfile.TemporaryDirectory(prefix="missed-") as tmp:
        wt = Path(tmp) / "wt"
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(wt), intro], check=True,
                       capture_output=True)
        try:
            col = odis.collect(wt, intro + "^", intro)
            sizes = {c.id: len(c.text) for c in col.candidates}
            doc = {"diff": col.diff, "changed_chars": 0, "candidates": [
                {"id": c.id, "size": sizes[c.id], "summary": impact.summary(c),
                 "facts": {k: getattr(c, k) for k in ("same_file_as_change", "imported_by_changed_file", "is_test")}}
                for c in col.candidates]}
            cfg = impact_select.load_config()
            decisions, record = impact_select.decide(doc, cfg)
            tiers = decisions["tiers"] or {c.id: impact.FULL for c in col.candidates}
        finally:
            subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], capture_output=True)
    for f in fixes:
        if f["class"] == "in_changed_function":
            continue
        short = f["function"].split(".")[-1] if f["function"] else ""
        hits = []
        for c in col.candidates:
            bare = c.symbol[len("call to "):] if c.symbol.startswith("call to ") else c.symbol
            if c.file == f["file"] and short and (bare == short or (c.inside_function or "").split(".")[-1] == short):
                hits.append({"id": c.id, "role": c.role, "line": c.line, "symbol": c.symbol,
                             "inside_function": c.inside_function, "tier": tiers.get(c.id, "duplicate")})
        f["candidates"] = hits
    return {"label": label, "fixes": fixes, "diff_files": sorted(changed), "n_candidates": len(col.candidates),
            "path": record["path"], "tiers": record["tiers"], "intro_message": e.get("introducer_message", ""),
            "fix_patch_lines": e.get("fix_patch_lines"), "introducer_lines": e.get("introducer_lines")}


def main() -> int:
    missed = set(json.loads(Path(sys.argv[1]).read_text())["never_any"])
    P = []
    for f in ("prepared_pilot30.json", "prepared_rest70.json"):
        P += json.loads((ROOT / "bugsinpy_bench/dataset" / f).read_text())
    entries = [e for e in P if f"{e['project']}#{e['bug_id']}" in missed]
    for e in entries:
        if isinstance(e["oracle"], str):
            e["oracle"] = ast.literal_eval(e["oracle"])
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(lambda e: _safe(e), entries))
    (Path(__file__).parent / "missed_analysis.json").write_text(json.dumps(res, indent=1) + "\n")
    from collections import Counter
    cls = Counter()
    for r in res:
        if "error" in r:
            print(r["label"], "ERROR", r["error"]); continue
        kinds = {f["class"] for f in r["fixes"]}
        k = "in_changed_function" if "in_changed_function" in kinds else ("in_changed_file" if "in_changed_file" in kinds else "outside_diff")
        cls[k] += 1
        extra = [(f["file"], f["function"], f["class"], [(h["role"], h["tier"]) for h in f.get("candidates", [])]) for f in r["fixes"] if f["class"] != "in_changed_function"]
        print(f"{r['label']:14s} {k:20s} cands {r['n_candidates']:4d} {r['path']:6s} {extra if k != 'in_changed_function' else ''}")
    print(cls)
    return 0


def _safe(e):
    try:
        return analyze(e)
    except Exception as ex:  # noqa: BLE001
        return {"label": f"{e['project']}#{e['bug_id']}", "error": f"{type(ex).__name__}: {ex}"}


if __name__ == "__main__":
    raise SystemExit(main())
