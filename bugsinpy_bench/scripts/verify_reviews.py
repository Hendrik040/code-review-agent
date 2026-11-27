"""Ask Jev three yes/no questions about a finished review (offline cascade test).

Design, fixed before any answer existed:
docs/superpowers/specs/2026-11-27-jev-review-verifier-design.md

One Jev call per stored review. The state holds only what the reviewer itself
produced (its findings and its closing message) plus the PR title and the
changed files. Jev does not see the diff, the judge's verdict, or any other
model's review.

Usage:
    .venv/bin/python bugsinpy_bench/scripts/verify_reviews.py --arm haiku --pass 1 [--only a#1,b#2]
Writes bugsinpy_bench/routing/verifier/answers_{arm}_p{pass}.json (resumes by label).
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT_DIR = ROOT / "bugsinpy_bench" / "routing" / "verifier"
MAX_SUMMARY = 300
MAX_CLOSING = 6000
FINDING_FIELDS = ("file", "line", "severity", "category", "summary")


def _noul(text: str) -> dict:
    return {"type": "noul", "instructions": text}


QUESTIONS: dict[str, dict] = {
    "unfiled_issue": _noul(
        "Does `closing_message` describe a defect, risk or questionable behaviour in the changed "
        "code that is not covered by any entry in `findings`?"),
    "dismissed_as_intended": _noul(
        "Does `closing_message` say the reviewer noticed a behaviour change or problem but did not "
        "report it because it looks intentional, pre-existing, out of scope or low impact?"),
    "could_not_verify": _noul(
        "Does `closing_message` say the reviewer was unable to run, test or otherwise confirm "
        "something about the changed code?"),
}


def review_state(title: str, files: list[dict], review: dict) -> dict:
    findings = []
    for f in review["findings"]:
        row = {k: f.get(k) for k in FINDING_FIELDS}
        row["summary"] = str(row["summary"] or "")[:MAX_SUMMARY]
        findings.append(row)
    return {
        "pull_request_title": title,
        "files_changed": files,
        "findings": findings,
        "closing_message": review["closing_message"][:MAX_CLOSING],
    }


def is_verifiable(review: dict) -> bool:
    """False for a review that never submitted or whose trace is missing; such a
    review always gets a second look (flag 1.0 in score_cascade.flag_score)."""
    return review["exit_reason"] == "submit_findings" and bool(review.get("has_trace", True))


def verify(state: dict, client) -> dict:
    """{"answers": {question: P(yes)}, "usage": {...}} or {"error": class name}."""
    try:
        resp = client.system_one(state=state, questions=QUESTIONS)
        answers = {name: float(resp.answers[name].noul) for name in QUESTIONS}
        usage = {"input_tokens": int(getattr(resp.usage, "input_tokens", 0) or 0),
                 "output_tokens": int(getattr(resp.usage, "output_tokens", 0) or 0)}
        return {"answers": answers, "usage": usage}
    except Exception as e:  # noqa: BLE001 — recorded; scored as a flag of 1.0
        return {"error": type(e).__name__}  # class name only: SDK errors can carry request bodies


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["haiku", "sonnet", "opus"])
    ap.add_argument("--pass", dest="pass_", required=True, type=int, choices=[1, 2])
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    from block_summaries import load_entries, numstat
    from review_digest import load_reviews

    entries = {e["label"]: e for e in load_entries("bugsinpy")}
    reviews = load_reviews(args.arm)
    labels = sorted(reviews)
    if args.only:
        labels = [lb for lb in labels if lb in set(args.only.split(","))]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"answers_{args.arm}_p{args.pass_}.json"
    done = {r["label"]: r for r in json.loads(out.read_text())["reviews"]} if out.exists() else {}
    local = threading.local()
    lock = threading.Lock()

    def client():
        if not hasattr(local, "c"):
            local.c = TypeSafeClient(timeout=20, retry=RetryPolicy(max_retries=1))
        return local.c

    def save() -> None:
        out.write_text(json.dumps({"arm": args.arm, "pass": args.pass_, "questions": QUESTIONS,
                                   "reviews": sorted(done.values(), key=lambda r: r["label"])}, indent=1) + "\n")

    def one(label: str) -> None:
        rv, e = reviews[label], entries[label]
        rec = {"label": label, "submitted": is_verifiable(rv),
               "n_findings": len(rv["findings"]), "num_turns": rv["num_turns"],
               "closing_chars": len(rv["closing_message"]),
               **verify(review_state(e["title"], numstat(e["diff"]), rv), client())}
        with lock:
            done[label] = rec
            save()

    with ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(one, [lb for lb in labels if lb not in done]))
    rs = list(done.values())
    print(f"{args.arm} p{args.pass_}: reviews={len(rs)} errors={sum('error' in r for r in rs)} "
          f"not_submitted={sum(not r['submitted'] for r in rs)} empty_closing={sum(r['closing_chars'] == 0 for r in rs)} "
          f"jev_in={sum(r.get('usage', {}).get('input_tokens', 0) for r in rs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
