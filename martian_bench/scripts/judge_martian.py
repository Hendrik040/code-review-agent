"""LLM-judge for the Martian Sentry sweep — using Martian's exact prompt.

For each PR in a martian sweep, evaluates every (golden, candidate)
pair using Martian's verbatim JUDGE_PROMPT (from
offline/code_review_benchmark/step3_judge_comments.py). Then:

  - golden is "found" if any candidate matched it
  - candidate is "TP" if it matched any golden

Per-PR:
  recall_pr     = matched_goldens / total_goldens
  precision_pr  = matched_candidates / total_candidates
  f1_pr         = 2 * P * R / (P + R)

Sweep aggregates: micro-averaged precision/recall/F1, plus per-PR.

We use Sonnet 4.5 (`claude-sonnet-4-5-20250929`) — the same judge
Martian's published `offline/results/anthropic_claude-sonnet-4-5-*`
column was scored with — so our number is directly comparable to
their leaderboard's Sonnet column.

Usage:
    uv run python martian_bench/scripts/judge_martian.py \\
        martian_bench/results/sweep_2026-05-04_martian_agent_xhigh_001
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

# Verbatim copy of Martian's JUDGE_PROMPT from
# offline/code_review_benchmark/step3_judge_comments.py — matters that
# this is identical so our numbers are comparable to their leaderboard.
JUDGE_PROMPT = """You are evaluating AI code review tools.
Determine if the candidate issue matches the golden (expected) comment.

Golden Comment (the issue we're looking for):
{golden_comment}

Candidate Issue (from the tool's review):
{candidate}

Instructions:
- Determine if the candidate identifies the SAME underlying issue as the golden comment
- Accept semantic matches - different wording is fine if it's the same problem
- Focus on whether they point to the same bug, concern, or code issue

Respond with ONLY a JSON object:
{{"reasoning": "brief explanation", "match": true/false, "confidence": 0.0-1.0}}"""


@dataclass
class PairVerdict:
    golden_idx: int
    candidate_idx: int
    match: bool
    confidence: float
    reasoning: str
    error: Optional[str] = None


@dataclass
class PRVerdict:
    label: str
    pr_url: str
    sdk: str
    effort: str
    n_goldens: int
    n_candidates: int
    matched_goldens: int
    matched_candidates: int
    recall: float
    precision: Optional[float]
    f1: float
    pairs: list[PairVerdict] = field(default_factory=list)


# --- helpers ---


def _split_run_file(p: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    text = p.read_text()
    header: dict[str, str] = {}
    body = text
    if text.startswith("# === MARTIAN RUN ==="):
        parts = text.split("# === END MARTIAN ===\n", 1)
        for line in parts[0].splitlines():
            m = re.match(r"^# (\w+): (.*)$", line)
            if m:
                header[m.group(1)] = m.group(2).strip()
        body = parts[1] if len(parts) > 1 else ""
    findings: list[dict[str, Any]] = []
    if "# ---" in body:
        json_part = body.split("# ---", 1)[1].strip()
        try:
            findings = json.loads(json_part)
        except json.JSONDecodeError:
            findings = []
    return header, findings


def _candidate_str(f: dict[str, Any]) -> str:
    """One-paragraph rendering of a candidate finding for the judge."""
    parts = []
    if f.get("file"):
        parts.append(f"File: {f['file']}")
    if f.get("line"):
        parts.append(f"Line: {f['line']}")
    if f.get("severity"):
        parts.append(f"Severity: {f['severity']}")
    if f.get("summary"):
        parts.append(f"Summary: {f['summary']}")
    if f.get("detail"):
        parts.append(f"Detail: {f['detail']}")
    return "\n".join(parts)


def _golden_str(g: dict[str, Any]) -> str:
    severity = g.get("severity", "")
    body = g.get("comment", g.get("text", ""))
    return f"Severity: {severity}\n{body}" if severity else body


def _judge_pair(client: Anthropic, golden: dict, candidate: dict) -> PairVerdict:
    prompt = JUDGE_PROMPT.format(
        golden_comment=_golden_str(golden),
        candidate=_candidate_str(candidate),
    )
    try:
        resp = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip() if resp.content else ""
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        data = json.loads(text)
        return PairVerdict(
            golden_idx=-1, candidate_idx=-1,  # set by caller
            match=bool(data.get("match", False)),
            confidence=float(data.get("confidence", 0.0)),
            reasoning=str(data.get("reasoning", "")),
        )
    except Exception as e:  # noqa: BLE001
        return PairVerdict(-1, -1, False, 0.0, f"judge error: {e!s}"[:200], error=str(e)[:200])


def _judge_pr(
    client: Anthropic,
    label: str, pr_url: str,
    sdk: str, effort: str,
    goldens: list[dict],
    candidates: list[dict],
) -> PRVerdict:
    pairs: list[PairVerdict] = []
    matched_goldens: set[int] = set()
    matched_candidates: set[int] = set()
    for gi, g in enumerate(goldens):
        for ci, c in enumerate(candidates):
            v = _judge_pair(client, g, c)
            v.golden_idx = gi
            v.candidate_idx = ci
            pairs.append(v)
            if v.match:
                matched_goldens.add(gi)
                matched_candidates.add(ci)
    n_g = len(goldens)
    n_c = len(candidates)
    recall = round(len(matched_goldens) / n_g, 4) if n_g else 0.0
    precision = round(len(matched_candidates) / n_c, 4) if n_c else None
    f1 = (
        round(2 * precision * recall / (precision + recall), 4)
        if (precision and recall and (precision + recall) > 0) else 0.0
    )
    return PRVerdict(
        label=label, pr_url=pr_url, sdk=sdk, effort=effort,
        n_goldens=n_g, n_candidates=n_c,
        matched_goldens=len(matched_goldens),
        matched_candidates=len(matched_candidates),
        recall=recall, precision=precision, f1=f1,
        pairs=pairs,
    )


# --- main ---


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sweep", help="Path to sweep_<id>/ directory")
    args = ap.parse_args()
    sweep_dir = Path(args.sweep)
    if not sweep_dir.is_dir():
        sys.exit(f"not a directory: {sweep_dir}")
    meta = json.loads((sweep_dir / "meta.json").read_text())
    runs_dir = sweep_dir / "runs"
    if not runs_dir.is_dir():
        sys.exit(f"missing runs/ in {sweep_dir}")

    # Need goldens — load prepared.json referenced in meta.
    prepared_path = Path(meta.get("prepared_path", ""))
    if not prepared_path.is_absolute():
        prepared_path = PROJECT_ROOT / prepared_path
    prepared = json.loads(prepared_path.read_text())
    by_label = {f"{e['repo_slug'].replace('/', '_')}#{e['pr_number']}": e for e in prepared}

    client = Anthropic()
    print(f"Judging {sweep_dir.name} with {JUDGE_MODEL} (Martian prompt)…")
    pr_verdicts: list[PRVerdict] = []
    for run_file in sorted(runs_dir.iterdir()):
        if not run_file.is_file():
            continue
        header, candidates = _split_run_file(run_file)
        label = header.get("pr", "")
        spec = by_label.get(label)
        if spec is None:
            print(f"  warning: no prepared entry for {label}", file=sys.stderr)
            continue
        v = _judge_pr(
            client,
            label=label, pr_url=spec.get("pr_url", ""),
            sdk=meta["sdk"], effort=meta["effort"],
            goldens=spec.get("goldens", []),
            candidates=candidates,
        )
        pr_verdicts.append(v)
        rstr = f"{v.recall:.0%}"
        pstr = f"{v.precision:.0%}" if v.precision is not None else "—"
        print(f"  {label:<32}  goldens={v.n_goldens} cands={v.n_candidates}  "
              f"matched_g={v.matched_goldens}/{v.n_goldens}  "
              f"R={rstr} P={pstr} F1={v.f1:.0%}")

    # Sweep micro-averaged
    total_goldens = sum(v.n_goldens for v in pr_verdicts)
    total_candidates = sum(v.n_candidates for v in pr_verdicts)
    total_matched_g = sum(v.matched_goldens for v in pr_verdicts)
    total_matched_c = sum(v.matched_candidates for v in pr_verdicts)
    micro_r = round(total_matched_g / total_goldens, 4) if total_goldens else 0.0
    micro_p = round(total_matched_c / total_candidates, 4) if total_candidates else None
    micro_f1 = (
        round(2 * micro_p * micro_r / (micro_p + micro_r), 4)
        if (micro_p and micro_r and (micro_p + micro_r) > 0) else 0.0
    )

    summary = {
        "sweep_id": meta["sweep_id"],
        "sdk": meta["sdk"], "effort": meta["effort"],
        "judge_model": JUDGE_MODEL,
        "judge_prompt_source": "Martian step3_judge_comments.py JUDGE_PROMPT",
        "n_prs": len(pr_verdicts),
        "total_goldens": total_goldens,
        "total_candidates": total_candidates,
        "total_matched_goldens": total_matched_g,
        "total_matched_candidates": total_matched_c,
        "micro_recall": micro_r,
        "micro_precision": micro_p,
        "micro_f1": micro_f1,
        "macro_recall": round(sum(v.recall for v in pr_verdicts) / len(pr_verdicts), 4) if pr_verdicts else 0.0,
        "macro_f1": round(sum(v.f1 for v in pr_verdicts) / len(pr_verdicts), 4) if pr_verdicts else 0.0,
        "verdicts": [asdict(v) for v in pr_verdicts],
    }
    out_path = sweep_dir / "judged.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print()
    print(f"  micro recall:    {micro_r:.1%}  ({total_matched_g}/{total_goldens} goldens)")
    print(f"  micro precision: {micro_p:.1%} ({total_matched_c}/{total_candidates} candidates)" if micro_p is not None else "  micro precision: — (no candidates)")
    print(f"  micro F1:        {micro_f1:.1%}")
    print(f"  macro recall:    {summary['macro_recall']:.1%}  (avg per-PR)")
    print(f"  macro F1:        {summary['macro_f1']:.1%}")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
