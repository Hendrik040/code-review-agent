"""Ask Jev the block-routing questions (design section 2) and store the raw answers.

Per PR: one Jev call per block record (7 questions about that block) plus one
call for the PR (4 questions over the title, per-file line counts and all
block records). typesafe_sdk 0.7.6 has no batch `items` call, so each block
is its own call. Arm A sends block records without Haiku's complexity score,
arm B with it; everything else is identical.

Usage:
    .venv/bin/python bugsinpy_bench/scripts/route_blocks.py --set bugsinpy --arm A --pass 1 [--only a#1,b#2]
Writes bugsinpy_bench/routing/blocks/routes_{set}_{arm}_p{pass}.json (resumes by label).
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

from block_rules import norm_levels  # noqa: E402
from block_summaries import CACHE_DIR, MAX_FILES, get_blocks, load_entries, numstat  # noqa: E402

OUT_DIR = ROOT / "bugsinpy_bench" / "routing" / "blocks"
ARMS = ("A", "B")


def _noul(text: str) -> dict:
    return {"type": "noul", "instructions": text}


BLOCK_QUESTIONS: dict[str, dict] = {
    "precision_logic": _noul(
        "Does the changed code in `block` contain logic where a one-character or boundary mistake "
        "changes behavior, such as a regular expression, slicing or index arithmetic, a comparison "
        "operator, range bounds, or a format string?"),
    "state_tracking": _noul(
        "Does the changed code in `block` change how state is carried across loop iterations or "
        "calls, such as counters, stacks, depth tracking, caches, flags, or mutable default values?"),
    "error_path": _noul(
        "Does the changed code in `block` add, remove or change exception handling, return codes, "
        "early returns, or cleanup on failure?"),
    "contract_change": _noul(
        "Does the changed code in `block` change a function's signature, its return value or return "
        "type, or the meaning of a value that existing callers rely on?"),
    "value_domain": _noul(
        "Does the changed code in `block` assume a particular input type or value range (for example "
        "int versus datetime, str versus bytes, NumPy scalars versus Python ints, or None) that some "
        "caller could violate?"),
    "async_flow": _noul(
        "Does the changed code in `block` involve callbacks, futures, threads, processes, or "
        "asynchronous control flow?"),
    "verify_effort": {
        "type": "score",
        "instructions": "How much reasoning does a reviewer need to verify the changed code in `block` is correct?",
        "criteria": [
            "Reading the changed lines of this block alone is enough.",
            "The reviewer must trace one or two related functions or callers.",
            "The reviewer must reason about several interacting cases, states or invariants across calls.",
        ],
    },
}

PR_QUESTIONS: dict[str, dict] = {
    "change_kind": {
        "type": "score",
        "instructions": "What kind of change does this pull request make?",
        "criteria": [
            "Only documentation, comments, tests or type hints change; no runtime behavior changes.",
            "A runtime change that cannot alter control flow or results, such as log text, messages, "
            "constants or configuration defaults.",
            "A small logic change a reader can verify from the changed lines alone.",
            "A logic change whose correctness depends on edge cases, state, error paths or code outside the diff.",
        ],
    },
    "beyond_title": _noul("Does the diff change behavior that the pull request title does not describe?"),
    "tests_exercise_change": _noul(
        "Do the test changes in this pull request exercise the changed runtime behavior, including its edge cases?"),
    "high_stakes": _noul(
        "Does this change touch authentication, authorization, secrets, payments, data deletion or "
        "migration, or concurrency primitives?"),
}


def _for_arm(block: dict, arm: str) -> dict:
    if arm not in ARMS:
        raise ValueError(f"arm must be A or B, got {arm!r}")
    b = {k: v for k, v in block.items() if k != "block_id"}
    if arm == "A":
        b.pop("complexity_1_10", None)
    return b


def block_state(title: str, block: dict, arm: str) -> dict:
    return {"pr_title": title, "block": _for_arm(block, arm)}


def pr_state(title: str, files: list[dict], blocks: list[dict], arm: str, files_dropped: int = 0) -> dict:
    return {"pr_title": title, "files_changed": files, "files_dropped": files_dropped,
            "blocks": [_for_arm(b, arm) for b in blocks]}


def _parse(resp, questions: dict) -> dict:
    out = {}
    for name, q in questions.items():
        a = resp.answers[name]
        if q["type"] == "noul":
            out[name] = float(a.noul)
        else:
            levels = norm_levels(dict(a.probabilities), len(q["criteria"]))
            if levels is None:
                raise ValueError(f"{name} probabilities do not sum to 1")
            out[name] = levels
    return out


def route_entry(label: str, title: str, diff: str, arm: str, *, jev_client=None,
                haiku_client=None, cache_dir: Path = CACHE_DIR) -> dict:
    rec = get_blocks(haiku_client, title, diff, cache_dir=cache_dir)
    usage = {"input_tokens": 0, "output_tokens": 0}
    calls = 0

    def ask(state, questions):
        nonlocal calls
        calls += 1
        resp = jev_client.system_one(state=state, questions=questions)
        usage["input_tokens"] += int(getattr(resp.usage, "input_tokens", 0) or 0)
        usage["output_tokens"] += int(getattr(resp.usage, "output_tokens", 0) or 0)
        return _parse(resp, questions)

    blocks = []
    for b in rec["blocks"]:
        try:
            blocks.append({"block_id": b["block_id"], "answers": ask(block_state(title, b, arm), BLOCK_QUESTIONS)})
        except Exception as e:  # noqa: BLE001 — recorded, scored as risk 1.0
            blocks.append({"block_id": b["block_id"], "error": type(e).__name__})
    # Same files block extraction described: the MAX_FILES with the most changed lines.
    stats = sorted(numstat(diff), key=lambda f: f["added"] + f["removed"], reverse=True)
    files, files_dropped = stats[:MAX_FILES], max(0, len(stats) - MAX_FILES)
    try:
        pr = {**ask(pr_state(title, files, rec["blocks"], arm, files_dropped), PR_QUESTIONS), "error": None}
    except Exception as e:  # noqa: BLE001
        pr = {"change_kind": None, "beyond_title": None, "tests_exercise_change": None,
              "high_stakes": None, "error": type(e).__name__}
    return {"label": label, "arm": arm, "blocks": blocks, "pr": pr,
            "blocks_dropped": rec["blocks_dropped"], "files_dropped": files_dropped, "jev_calls": calls, "jev_usage": usage}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True, choices=["bugsinpy", "martian"])
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--pass", dest="pass_", required=True, type=int, choices=[1, 2])
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from anthropic import Anthropic
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    haiku = Anthropic()
    local = threading.local()

    def jev():
        if not hasattr(local, "c"):
            local.c = TypeSafeClient(timeout=20, retry=RetryPolicy(max_retries=1))
        return local.c

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"routes_{args.set}_{args.arm}_p{args.pass_}.json"
    done = {r["label"]: r for r in json.loads(out.read_text())["routes"]} if out.exists() else {}
    entries = load_entries(args.set)
    if args.only:
        keep = set(args.only.split(","))
        entries = [e for e in entries if e["label"] in keep]
    todo = [e for e in entries if e["label"] not in done]
    lock = threading.Lock()

    def save():
        out.write_text(json.dumps({"set": args.set, "arm": args.arm, "pass": args.pass_,
                                   "routes": sorted(done.values(), key=lambda r: r["label"])}, indent=1) + "\n")

    def one(e):
        r = route_entry(e["label"], e["title"], e["diff"], args.arm, jev_client=jev(), haiku_client=haiku)
        errs = sum("error" in b for b in r["blocks"]) + (r["pr"]["error"] is not None)
        with lock:
            done[e["label"]] = r
            save()
        print(f"{e['label']:48s} blocks={len(r['blocks']):3d} calls={r['jev_calls']:3d} errors={errs} "
              f"jev_tok={r['jev_usage']['input_tokens']}/{r['jev_usage']['output_tokens']}", flush=True)
        return r

    with ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(one, todo))
    rs = list(done.values())
    print(f"TOTAL routes={len(rs)} calls={sum(r['jev_calls'] for r in rs)} "
          f"jev_in={sum(r['jev_usage']['input_tokens'] for r in rs)} "
          f"jev_out={sum(r['jev_usage']['output_tokens'] for r in rs)} "
          f"block_errors={sum('error' in b for r in rs for b in r['blocks'])} "
          f"pr_errors={sum(r['pr']['error'] is not None for r in rs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
