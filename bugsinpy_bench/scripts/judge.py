"""LLM-judge scorer for a BugsInPy bench sweep.

For every entry in a sweep_<id>/ directory, asks a Claude Sonnet model
TWO yes/no questions PER FINDING:

  matches_maintainer_bug : did this finding identify the same root
                           cause the maintainer fixed in bug_patch.txt?
                           Drives target recall and strict precision.

  is_real_bug            : independent of whether it matches the
                           maintainer's bug, is this finding describing
                           an actual bug (vs a hallucination or a
                           non-issue)? Drives broad recall (the
                           "ansible#9 case" — agent found 2 real Py3
                           compat bugs that weren't the maintainer's
                           target) and plausibility precision.

Reads the new sweep-aware layout (Phase 6):
    bugsinpy_bench/results/<sweep_id>/
      meta.json
      suite.md
      runs/<sdk>_<effort>_<project>_<bugid>.txt    (header + JSON tail)

Writes:
    bugsinpy_bench/results/<sweep_id>/judged.json   per-finding verdicts

Usage:
    uv run python bugsinpy_bench/scripts/judge.py \\
        bugsinpy_bench/results/sweep_2026-05-04_agent_low
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from anthropic import Anthropic  # noqa: E402

JUDGE_MODEL = "claude-sonnet-4-5-20250929"
BUGSINPY_PROJECTS = PROJECT_ROOT / "bugsinpy_bench" / "dataset" / "bugsinpy" / "projects"


# ----------------------------------------------------------------- types --


@dataclass
class FindingVerdict:
    finding_index: int
    matches_maintainer_bug: bool
    is_real_bug: bool
    confidence: float
    reasoning: str
    error: Optional[str] = None


@dataclass
class BugVerdict:
    label: str  # e.g. "pandas#6"
    sdk: str
    effort: str
    source: str
    run_filename: str
    findings_count: int
    matches_count: int  # count of findings where matches_maintainer_bug=True
    real_count: int     # count of findings where is_real_bug=True
    target_recall: bool  # = (matches_count >= 1)
    broad_recall: bool   # = (real_count >= 1)
    findings: list[FindingVerdict] = field(default_factory=list)


# --------------------------------------------------------- per-bug parser --


def _split_run_file(run_path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Read sweep-style run file. Returns (header_kvs, findings_list)."""
    text = run_path.read_text()
    header: dict[str, str] = {}
    if text.startswith("# === BENCH RUN ==="):
        body_split = text.split("# === END BENCH ===\n", 1)
        for line in body_split[0].splitlines():
            m = re.match(r"^# (\w+): (.*)$", line)
            if m:
                header[m.group(1)] = m.group(2).strip()
        rest = body_split[1] if len(body_split) > 1 else ""
    else:
        rest = text

    findings: list[dict[str, Any]] = []
    if "# ---" in rest:
        json_part = rest.split("# ---", 1)[1].strip()
        try:
            findings = json.loads(json_part)
        except json.JSONDecodeError:
            findings = []
    return header, findings


def _read_bug_patch(project: str, bug_id: int) -> str:
    p = BUGSINPY_PROJECTS / project / "bugs" / str(bug_id) / "bug_patch.txt"
    return p.read_text(errors="replace") if p.is_file() else ""


# -------------------------------------------------------- judge prompt --


def _build_prompt(
    bug_patch: str,
    findings: list[dict[str, Any]],
    source: str,
) -> str:
    findings_blob = json.dumps(findings, indent=2) if findings else "(no findings)"
    source_note = (
        "The agent reviewed the actual historical commit that introduced "
        "the bug (real-PR-shaped diff with surrounding noise)."
        if source == "blame"
        else
        "The agent reviewed a synthetic diff that re-introduces the bug "
        "on top of the fixed code."
    )

    return f"""You are evaluating an AI code-review tool. The tool received a PR-shaped diff and emitted a list of findings. We have the maintainer's actual fix patch (= the canonical bug). Your job is to judge EACH finding on TWO independent criteria:

# Maintainer's fix patch (= the bug we're testing for)

```diff
{bug_patch.strip()}
```

# Methodology note

{source_note}

# Findings emitted by the tool

```json
{findings_blob}
```

# Your task

For EACH finding, answer two yes/no questions independently:

1. **matches_maintainer_bug**: does THIS finding describe the same root cause as the maintainer's fix? Be lenient on wording, file-path prefixes, and line numbers; be strict on substance — a finding about a different bug at a nearby line does NOT match.

2. **is_real_bug**: independent of (1), is THIS finding describing a legitimate bug or code quality issue worth flagging? A finding can be `is_real_bug: true` AND `matches_maintainer_bug: false` (the agent found a different real bug). A finding describing something that isn't actually a bug — or hallucinating an issue that doesn't exist — should be `is_real_bug: false`.

Respond with ONLY a JSON array, one element per finding, in the same order:

[
  {{"finding_index": 0, "matches_maintainer_bug": <bool>, "is_real_bug": <bool>, "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}},
  {{"finding_index": 1, ...}}
]

If there are no findings, respond with an empty array `[]`."""


def _judge_findings(
    client: Anthropic,
    bug_patch: str,
    findings: list[dict[str, Any]],
    source: str,
) -> list[FindingVerdict]:
    if not findings:
        return []
    prompt = _build_prompt(bug_patch, findings, source)
    try:
        resp = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip() if resp.content else ""
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("expected list, got " + type(data).__name__)
        out: list[FindingVerdict] = []
        for item in data:
            out.append(FindingVerdict(
                finding_index=int(item.get("finding_index", len(out))),
                matches_maintainer_bug=bool(item.get("matches_maintainer_bug", False)),
                is_real_bug=bool(item.get("is_real_bug", False)),
                confidence=float(item.get("confidence", 0.0)),
                reasoning=str(item.get("reasoning", "")),
            ))
        return out
    except Exception as e:  # noqa: BLE001
        return [FindingVerdict(
            finding_index=i,
            matches_maintainer_bug=False, is_real_bug=False,
            confidence=0.0,
            reasoning=f"judge error: {e!s}"[:200],
            error=str(e)[:200],
        ) for i in range(len(findings))]


# -------------------------------------------------------------- main --


def _judge_sweep(sweep_dir: Path) -> dict[str, Any]:
    meta_path = sweep_dir / "meta.json"
    if not meta_path.is_file():
        sys.exit(f"missing meta.json in {sweep_dir}")
    meta = json.loads(meta_path.read_text())
    runs_dir = sweep_dir / "runs"
    if not runs_dir.is_dir():
        sys.exit(f"missing runs/ in {sweep_dir}")

    client = Anthropic()
    bugs: list[BugVerdict] = []
    print(f"Judging {sweep_dir.name} with {JUDGE_MODEL}…")

    for run_file in sorted(runs_dir.iterdir()):
        if not run_file.is_file():
            continue
        header, findings = _split_run_file(run_file)
        label = header.get("bug", "")
        if not label:
            continue
        try:
            project, bug_str = label.split("#", 1)
            bug_id = int(bug_str.strip())
        except (ValueError, IndexError):
            continue
        bug_patch = _read_bug_patch(project, bug_id)
        verdicts = _judge_findings(
            client,
            bug_patch=bug_patch,
            findings=findings,
            source=header.get("bug_source", "blame"),
        )
        matches = sum(1 for v in verdicts if v.matches_maintainer_bug)
        real = sum(1 for v in verdicts if v.is_real_bug)
        bv = BugVerdict(
            label=label,
            sdk=header.get("sdk", "").replace("_sdk", ""),
            effort=header.get("effort", ""),
            source=header.get("bug_source", ""),
            run_filename=run_file.name,
            findings_count=len(findings),
            matches_count=matches,
            real_count=real,
            target_recall=matches >= 1,
            broad_recall=real >= 1,
            findings=verdicts,
        )
        bugs.append(bv)
        marker_t = "✓" if bv.target_recall else "✗"
        marker_b = "✓" if bv.broad_recall else "✗"
        print(f"  T:{marker_t} B:{marker_b}  {label:<22}  "
              f"findings={len(findings)} matches={matches} real={real}")

    n = len(bugs)
    target_recall = sum(1 for b in bugs if b.target_recall)
    broad_recall = sum(1 for b in bugs if b.broad_recall)
    total_findings = sum(b.findings_count for b in bugs)
    total_matches = sum(b.matches_count for b in bugs)
    total_real = sum(b.real_count for b in bugs)

    summary = {
        "sweep_id": meta.get("sweep_id"),
        "sdk": meta.get("sdk"),
        "effort": meta.get("effort"),
        "judge_model": JUDGE_MODEL,
        "n_bugs": n,
        "target_recall": round(target_recall / n, 4) if n else 0.0,
        "broad_recall": round(broad_recall / n, 4) if n else 0.0,
        "precision_strict": round(total_matches / total_findings, 4) if total_findings else None,
        "precision_plausible": round(total_real / total_findings, 4) if total_findings else None,
        "total_findings": total_findings,
        "total_matches": total_matches,
        "total_real": total_real,
        "verdicts": [asdict(b) for b in bugs],
    }
    out_path = sweep_dir / "judged.json"
    out_path.write_text(json.dumps(summary, indent=2))

    print()
    print(f"  target_recall   (matches maintainer):    "
          f"{target_recall}/{n} = {summary['target_recall']:.1%}")
    print(f"  broad_recall    (caught a real bug):     "
          f"{broad_recall}/{n} = {summary['broad_recall']:.1%}")
    if total_findings:
        print(f"  precision_strict     (matches/findings): "
              f"{total_matches}/{total_findings} = {summary['precision_strict']:.1%}")
        print(f"  precision_plausible  (real/findings):    "
              f"{total_real}/{total_findings} = {summary['precision_plausible']:.1%}")
    print(f"\nSaved: {out_path}")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sweep", help="Path to sweep_<id>/ directory (or a suite_NNN.md for back-compat)")
    args = ap.parse_args()
    p = Path(args.sweep)
    if p.is_dir():
        _judge_sweep(p)
    else:
        sys.exit(f"not a directory: {p}\n(legacy suite_NNN.md mode is no longer supported)")


if __name__ == "__main__":
    main()
