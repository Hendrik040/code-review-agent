# Block-level Jev Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure whether Jev, given Haiku-extracted per-block facts and 11 focused questions, routes BugsInPy and Martian PRs to the right reviewer tier better than the current router, comparing facts only (arm A) with facts plus Haiku's complexity score (arm B).

**Architecture:** Four scripts under `bugsinpy_bench/scripts/`. `block_summaries.py` asks Haiku 5.5 (effort high) for one record per changed code block, cached by diff hash. `route_blocks.py` asks Jev 7 questions per block (one call per block) and 4 per PR, and stores the raw probabilities. `block_rules.py` holds the pure decision rule, AUC and threshold sweep. `score_blocks.py` scores routes against the stored per-model results; no new reviews.

**Tech Stack:** Python 3.11 in the repo's `.venv`, `anthropic` SDK, `typesafe_sdk` 0.7.6 (`TypeSafeClient.system_one`), pytest.

**Spec:** `docs/superpowers/specs/2026-11-27-jev-block-routing-design.md`

## Global Constraints

- Branch `bench/model-tiers-pilot-local`, repo `/Users/hendrikkrack/Projects/triage-smoke-test`. Run Python as `.venv/bin/python`.
- No change to `shared/routing.py`, `agent_sdk/reviewer.py` or the context builder. No new review sweeps.
- Keys come from the git-ignored `.env` (`ANTHROPIC_API_KEY`, `TYPESAFE_API_KEY`). Never print or commit them. Before each commit, scan staged files: `git diff --cached | grep -E "sk-ant-|TYPESAFE_API_KEY=."` must print nothing.
- Haiku model `claude-haiku-5-5`, effort high. Check how effort is passed on the Messages API in the claude-api skill (`python/` docs) before writing the call; do not guess the parameter.
- The tier names `light`/`standard`/`deep` map to `haiku55_medium`/`sonnet55_high`/`opus55_high`, as in `score_full.py`'s `TIER_ARM`.
- The decision rule is fixed before scoring: deep if P(`high_stakes`) >= 0.5 or `block_risk` >= T; else from `change_kind` probs p[0..3]: light if p[2]+p[3] <= 0.15, standard if p[3] <= 0.15, else deep. Report T = 0.5 and a sweep T = 0.00, 0.05, ..., 1.00.
- `block_risk` = max over blocks of max(P(Q1..Q5 yes), P(Q7 top level)). Question wording below is copied into code verbatim.
- Arms: A sends block facts without `complexity_1_10`; B sends the same facts with it. Both arms use the same cached Haiku output.
- Two Jev passes per arm on BugsInPy (`p1`, `p2`); one pass per arm on Martian.
- Martian is held out: do not change questions or the rule after looking at Martian results.
- Record cost: Haiku from response usage at $0.10/$0.50 per MTok in/out; Jev from `response.usage` token counts (price unknown, report tokens and call counts).

### Question wording (verbatim)

Block questions (state = one block record plus the PR title):

| id | type | instructions |
|---|---|---|
| `precision_logic` | noul | Does the changed code in `block` contain logic where a one-character or boundary mistake changes behavior, such as a regular expression, slicing or index arithmetic, a comparison operator, range bounds, or a format string? |
| `state_tracking` | noul | Does the changed code in `block` change how state is carried across loop iterations or calls, such as counters, stacks, depth tracking, caches, flags, or mutable default values? |
| `error_path` | noul | Does the changed code in `block` add, remove or change exception handling, return codes, early returns, or cleanup on failure? |
| `contract_change` | noul | Does the changed code in `block` change a function's signature, its return value or return type, or the meaning of a value that existing callers rely on? |
| `value_domain` | noul | Does the changed code in `block` assume a particular input type or value range (for example int versus datetime, str versus bytes, NumPy scalars versus Python ints, or None) that some caller could violate? |
| `async_flow` | noul | Does the changed code in `block` involve callbacks, futures, threads, processes, or asynchronous control flow? |
| `verify_effort` | score | How much reasoning does a reviewer need to verify the changed code in `block` is correct? Criteria, in order: "Reading the changed lines of this block alone is enough." / "The reviewer must trace one or two related functions or callers." / "The reviewer must reason about several interacting cases, states or invariants across calls." |

PR questions (state = title, per-file line counts, all block records):

| id | type | instructions |
|---|---|---|
| `change_kind` | score | What kind of change does this pull request make? Criteria, in order: "Only documentation, comments, tests or type hints change; no runtime behavior changes." / "A runtime change that cannot alter control flow or results, such as log text, messages, constants or configuration defaults." / "A small logic change a reader can verify from the changed lines alone." / "A logic change whose correctness depends on edge cases, state, error paths or code outside the diff." |
| `beyond_title` | noul | Does the diff change behavior that the pull request title does not describe? |
| `tests_exercise_change` | noul | Do the test changes in this pull request exercise the changed runtime behavior, including its edge cases? |
| `high_stakes` | noul | Does this change touch authentication, authorization, secrets, payments, data deletion or migration, or concurrency primitives? |

## Review Focus

1. A diff for which Haiku returns zero blocks (deletions only, binary or non-code files): routing must still produce a tier from the PR questions, with `block_risk` 0.0.
2. Non-Python changed files (YAML, docs, setup.cfg): described as blocks of kind `config` or `other`, not dropped (unlike `router_inputs.is_source`).
3. A Jev error or timeout on one block: record `error`, treat that block's risk as 1.0 (fail toward deep, like the current router), count errors in the output.
4. A very large PR (Martian Sentry diffs): keep at most 40 blocks per PR, largest by lines added + removed, and record `blocks_dropped`.
5. `score` answers whose probabilities come keyed by int or str, or miss a level: normalize to a fixed-length list; if the sum is off 1.0 by more than 0.1, treat as an error (risk 1.0 for a block; `change_kind` error routes deep).

---

### Task 1: Pure decision logic

**Files:**
- Create: `bugsinpy_bench/scripts/block_rules.py`
- Test: `tests/test_block_rules.py`

**Interfaces:**
- Produces:
  - `norm_levels(raw: dict, n: int) -> list[float] | None` (raw probabilities keyed by int or str level; None if sum off by > 0.1)
  - `block_risk(blocks: list[dict]) -> float`, where each block dict is `{"answers": {"precision_logic": float, ..., "async_flow": float, "verify_effort": list[float]} }` or `{"error": str}`
  - `decide(entry: dict, T: float) -> str` returning `"light" | "standard" | "deep"`; `entry = {"blocks": [...], "pr": {"change_kind": list[float] | None, "high_stakes": float | None, ...}}`
  - `auc(pos: list[float], neg: list[float]) -> float` (ties count 0.5; `float("nan")` if either list is empty)
  - `sweep(entries: dict[str, dict], outcomes: dict[str, dict], Ts: list[float]) -> list[dict]` where `outcomes[label][tier] = {"found": bool, "cost_usd": float}` for each tier; returns `[{"T", "found", "cost_usd", "tiers": {"light": n, "standard": n, "deep": n}}]`

- [ ] **Step 1: Write the failing tests** in `tests/test_block_rules.py` (add `bugsinpy_bench/scripts` to `sys.path` at the top):

```python
def test_norm_levels_int_and_str_keys():
    assert norm_levels({0: 0.1, "1": 0.9}, 3) == [0.1, 0.9, 0.0]
    assert norm_levels({0: 0.2, 1: 0.2}, 2) is None

def test_block_risk_max_over_blocks_and_questions():
    a = {"answers": {"precision_logic": 0.1, "state_tracking": 0.7, "error_path": 0.0,
                     "contract_change": 0.0, "value_domain": 0.0, "async_flow": 0.9,
                     "verify_effort": [0.5, 0.3, 0.2]}}
    b = {"answers": {"precision_logic": 0.2, "state_tracking": 0.0, "error_path": 0.0,
                     "contract_change": 0.0, "value_domain": 0.0, "async_flow": 0.0,
                     "verify_effort": [0.0, 0.2, 0.8]}}
    assert block_risk([a, b]) == 0.8          # async_flow is NOT in Q1-Q5
    assert block_risk([]) == 0.0
    assert block_risk([{"error": "timeout"}]) == 1.0

def test_decide_rule():
    low = {"blocks": [], "pr": {"change_kind": [0.9, 0.05, 0.05, 0.0], "high_stakes": 0.1}}
    assert decide(low, 0.5) == "light"
    std = {"blocks": [], "pr": {"change_kind": [0.0, 0.2, 0.7, 0.1], "high_stakes": 0.1}}
    assert decide(std, 0.5) == "standard"
    deep_ck = {"blocks": [], "pr": {"change_kind": [0.0, 0.1, 0.6, 0.3], "high_stakes": 0.1}}
    assert decide(deep_ck, 0.5) == "deep"
    risky = {"blocks": [{"error": "x"}], "pr": {"change_kind": [0.9, 0.1, 0, 0], "high_stakes": 0.0}}
    assert decide(risky, 0.5) == "deep"
    hs = {"blocks": [], "pr": {"change_kind": [1, 0, 0, 0], "high_stakes": 0.5}}
    assert decide(hs, 0.5) == "deep"
    broken = {"blocks": [], "pr": {"change_kind": None, "high_stakes": 0.0}}
    assert decide(broken, 0.5) == "deep"

def test_auc():
    assert auc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert auc([0.5], [0.5]) == 0.5
    assert math.isnan(auc([], [0.1]))

def test_sweep_counts_found_and_cost():
    entries = {"x#1": {"blocks": [{"error": "e"}], "pr": {"change_kind": [1, 0, 0, 0], "high_stakes": 0}},
               "x#2": {"blocks": [], "pr": {"change_kind": [1, 0, 0, 0], "high_stakes": 0}}}
    outcomes = {"x#1": {"light": {"found": False, "cost_usd": 0.01}, "standard": {"found": False, "cost_usd": 0.05},
                        "deep": {"found": True, "cost_usd": 0.2}},
                "x#2": {"light": {"found": True, "cost_usd": 0.01}, "standard": {"found": True, "cost_usd": 0.05},
                        "deep": {"found": True, "cost_usd": 0.2}}}
    (r,) = sweep(entries, outcomes, [0.5])
    assert r == {"T": 0.5, "found": 2, "cost_usd": 0.21, "tiers": {"light": 1, "standard": 0, "deep": 1}}
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_block_rules.py -v`
Expected: FAIL (ImportError: `block_rules`).

- [ ] **Step 3: Implement the five functions in `bugsinpy_bench/scripts/block_rules.py`** per the Interfaces block and Global Constraints. Round `cost_usd` in `sweep` to 4 decimals.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_block_rules.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add bugsinpy_bench/scripts/block_rules.py tests/test_block_rules.py
git commit -m "bench: block routing decision rule, AUC and sweep"
```

### Task 2: Haiku block extraction

**Files:**
- Create: `bugsinpy_bench/scripts/block_summaries.py`
- Test: `tests/test_block_summaries.py`

**Interfaces:**
- Consumes: `router_inputs.fetch_diff(e) -> str`, `router_inputs.split_files(diff) -> dict[str, str]` (BugsInPy); Martian diffs fetched as in `martian_bench/scripts/route_martian.py` (`git diff --unified=3 --no-color base..head` after a depth-1 fetch of both SHAs).
- Produces:
  - `KINDS = ["data_structure", "function", "method", "class", "config", "test", "call_site", "import", "other"]`
  - `numstat(diff: str) -> list[dict]` with `{"path", "added", "removed"}` per file
  - `extract_file(client, title: str, path: str, file_diff: str) -> tuple[list[dict], dict]` (blocks, usage `{"input_tokens", "output_tokens"}`); each block `{"block_id", "file", "kind", "symbol", "lines_added", "lines_removed", "before", "after", "callers_or_users_touched": list[str], "constructs": list[str], "complexity_1_10": int}`; `block_id` = `f"{path}::{symbol}::{i}"`
  - `get_blocks(client, title: str, diff: str, *, cache_dir: Path) -> dict` returning `{"blocks": [...], "blocks_dropped": int, "usage": {...}, "cached": bool}`; cache file `cache_dir / f"{sha256(diff)}.json"`; keeps at most 40 blocks (largest `lines_added + lines_removed`)
  - CLI: `block_summaries.py --set bugsinpy|martian` writes the cache under `bugsinpy_bench/router_inputs/blocks/` and appends totals to `bugsinpy_bench/router_inputs/blocks/_cost.json`

- [ ] **Step 1: Write the failing tests** with a fake client whose `messages.create(**kw)` returns an object with `.content=[SimpleNamespace(type="text", text=json.dumps({"blocks": [...]}))]` and `.usage=SimpleNamespace(input_tokens=100, output_tokens=50)`:

```python
def test_numstat_counts_per_file():
    d = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1,2 @@\n-x\n+y\n+z\n"
    assert numstat(d) == [{"path": "a.py", "added": 2, "removed": 1}]

def test_get_blocks_caches_by_diff_hash(tmp_path):
    client = FakeClient(blocks_per_call=2)
    r1 = get_blocks(client, "t", TWO_FILE_DIFF, cache_dir=tmp_path)
    r2 = get_blocks(client, "t", TWO_FILE_DIFF, cache_dir=tmp_path)
    assert client.calls == 2 and r1["cached"] is False and r2["cached"] is True
    assert len(r2["blocks"]) == 4

def test_non_python_files_are_described(tmp_path):
    client = FakeClient(blocks_per_call=1)
    r = get_blocks(client, "t", YAML_AND_PY_DIFF, cache_dir=tmp_path)
    assert {b["file"] for b in r["blocks"]} == {"conf/app.yaml", "pkg/mod.py"}

def test_zero_blocks_is_valid(tmp_path):
    r = get_blocks(FakeClient(blocks_per_call=0), "t", TWO_FILE_DIFF, cache_dir=tmp_path)
    assert r["blocks"] == [] and r["blocks_dropped"] == 0

def test_cap_keeps_40_largest(tmp_path):
    r = get_blocks(FakeClient(blocks_per_call=25), "t", TWO_FILE_DIFF, cache_dir=tmp_path)
    assert len(r["blocks"]) == 40 and r["blocks_dropped"] == 10
```

(`FakeClient` gives block `i` `lines_added = i` so the cap keeps the largest.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_block_summaries.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement `block_summaries.py`.** System prompt: Haiku describes each changed code block (kinds above), states `before` and `after` behavior factually, lists callers or users the change touches that are visible in the diff, picks `constructs` from a fixed list (`regex, slicing, comparison, range_bound, format_string, loop, recursion, counter_or_stack, cache, flag, mutable_default, exception, early_return, return_value, signature, type_conversion, none_handling, numeric, string_bytes, datetime, async, callback, thread_or_process, io, sql_or_query, config_value, logging, test_assertion`), and gives `complexity_1_10` (1 = trivial, 10 = hardest to verify). It must never say whether the code is correct. Use structured JSON output (`output_config` format with a JSON schema, as `router_inputs.summarize` does) and effort high, `max_tokens=6000`. One call per file diff; a file diff over 24,000 characters is split at `@@` hunk boundaries into chunks of at most 24,000 characters.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_block_summaries.py -v`
Expected: 5 passed.

- [ ] **Step 5: Smoke on 3 real bugs** (`cookiecutter#4`, `thefuck#1`, `pandas#95`)

Run: `.venv/bin/python bugsinpy_bench/scripts/block_summaries.py --set bugsinpy --only cookiecutter#4,thefuck#1,pandas#95`
Expected: 3 cache files; each has at least one block whose `file` is the changed source file; printed cost below $0.05. Read the cookiecutter#4 output and check `before`/`after` describe the hook return-code change.

- [ ] **Step 6: Commit** (code, tests and the 3 cache files)

### Task 3: Jev routing per arm and pass

**Files:**
- Create: `bugsinpy_bench/scripts/route_blocks.py`
- Test: `tests/test_route_blocks.py`

**Interfaces:**
- Consumes: `block_summaries.get_blocks`, `block_summaries.numstat`, `block_rules.norm_levels`.
- Produces:
  - `BLOCK_QUESTIONS: dict[str, dict]`, `PR_QUESTIONS: dict[str, dict]` with the verbatim wording from Global Constraints (score criteria as an ordered list)
  - `block_state(title: str, block: dict, arm: str) -> dict` returning `{"pr_title": title, "block": {...}}`; arm `"A"` removes `complexity_1_10`, arm `"B"` keeps it; any other arm raises `ValueError`
  - `pr_state(title: str, files: list[dict], blocks: list[dict], arm: str) -> dict` returning `{"pr_title", "files_changed", "blocks"}` with the same arm rule per block
  - `route_entry(label: str, title: str, diff: str, arm: str, *, jev_client=None, haiku_client=None, cache_dir: Path) -> dict` returning `{"label", "arm", "blocks": [{"block_id", "answers"} | {"block_id", "error"}], "pr": {"change_kind": list[float] | None, "beyond_title": float | None, "tests_exercise_change": float | None, "high_stakes": float | None, "error": str | None}, "blocks_dropped": int, "jev_calls": int, "jev_usage": {...}}`
  - CLI: `route_blocks.py --set bugsinpy|martian --arm A|B --pass 1|2 [--only labels] [--workers 8]` writes `bugsinpy_bench/routing/blocks/routes_{set}_{arm}_p{pass}.json` and resumes by skipping labels already in that file

- [ ] **Step 1: Write the failing tests** with a fake Jev client whose `system_one(state, questions)` returns an object with `.answers[name]` (`.noul` for nouls, `.probabilities` for scores) and `.usage`:

```python
def test_arm_A_hides_complexity_arm_B_shows_it():
    b = {"block_id": "f::g::0", "complexity_1_10": 7, "before": "x", "after": "y"}
    assert "complexity_1_10" not in block_state("t", b, "A")["block"]
    assert block_state("t", b, "B")["block"]["complexity_1_10"] == 7

def test_question_ids_are_the_eleven_from_the_spec():
    assert list(BLOCK_QUESTIONS) == ["precision_logic", "state_tracking", "error_path",
        "contract_change", "value_domain", "async_flow", "verify_effort"]
    assert list(PR_QUESTIONS) == ["change_kind", "beyond_title", "tests_exercise_change", "high_stakes"]

def test_one_jev_call_per_block_plus_one_per_pr(tmp_path):
    jev = FakeJev()
    e = route_entry("x#1", "t", TWO_FILE_DIFF, "A", jev_client=jev,
                    haiku_client=FakeHaiku(blocks_per_call=2), cache_dir=tmp_path)
    assert e["jev_calls"] == 5 and len(e["blocks"]) == 4
    assert len(e["pr"]["change_kind"]) == 4

def test_block_error_is_recorded_not_raised(tmp_path):
    e = route_entry("x#1", "t", TWO_FILE_DIFF, "A", jev_client=FakeJev(fail_blocks=True),
                    haiku_client=FakeHaiku(blocks_per_call=1), cache_dir=tmp_path)
    assert all("error" in b for b in e["blocks"]) and e["pr"]["error"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_route_blocks.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement `route_blocks.py`.** Real Jev client: `typesafe_sdk.TypeSafeClient(timeout=20, retry=RetryPolicy(max_retries=1))`, one shared client per worker thread. Record only the exception class name in `error` (SDK errors can carry request bodies). Sum `usage` fields across calls.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_route_blocks.py tests/test_block_rules.py tests/test_block_summaries.py -v`
Expected: 14 passed.

- [ ] **Step 5: Smoke on the 3 cached bugs, both arms**

Run: `.venv/bin/python bugsinpy_bench/scripts/route_blocks.py --set bugsinpy --arm A --pass 1 --only cookiecutter#4,thefuck#1,pandas#95` and the same with `--arm B`.
Expected: no errors; each entry has `change_kind` of length 4; printed Jev calls and token totals.

- [ ] **Step 6: Checkpoint with the user.** Report the smoke's Haiku cost per bug and Jev tokens and calls per bug, and the projected totals for 100 BugsInPy bugs × 2 arms × 2 passes plus 10 Martian PRs × 2 arms. Continue only on the user's go-ahead.

- [ ] **Step 7: Commit**

### Task 4: Scoring

**Files:**
- Create: `bugsinpy_bench/scripts/score_blocks.py`
- Test: `tests/test_score_blocks.py`

**Interfaces:**
- Consumes: `block_rules.decide/block_risk/auc/sweep`; route files from Task 3; `bugsinpy_bench/routing/full_scores.json` (`per_bug[i][model] = {"found", "cost_usd"}`); Martian `judged.json` and `suite.md` of `sweep_2026-11-27_martian_{haiku55_medium,sonnet55_high,opus55_high}` with `_tail` replacements as in `score_full.martian()`.
- Produces:
  - `bugsinpy_outcomes() -> dict[str, dict]` keyed by label, then tier `light|standard|deep`, giving `{"found", "cost_usd"}`
  - `martian_outcomes() -> dict[str, dict]` keyed by label, then tier, giving `{"matched_goldens", "n_goldens", "matched_candidates", "n_candidates", "cost_usd"}`
  - `opus_needed_split(outcomes) -> tuple[list[str], list[str]]`: (deep found and light missed; light found)
  - CLI writes `bugsinpy_bench/routing/blocks_scores.json` and prints, per arm and pass, the AUC, the result at T = 0.5 and the sweep; plus the AUC of the per-bug max `complexity_1_10` alone and of the current router's P(deep) (from `routes_pilot30.json` + `routes_rest70.json`)

- [ ] **Step 1: Write the failing tests**

```python
def test_opus_needed_split_matches_step_10():
    pos, neg = opus_needed_split(bugsinpy_outcomes())
    assert len(pos) == 14 and len(neg) == 35

def test_current_router_auc_is_0_27():
    assert round(current_router_auc(), 2) == 0.27

def test_martian_outcomes_cover_10_prs_and_31_goldens():
    m = martian_outcomes()
    assert len(m) == 10
    assert sum(v["deep"]["n_goldens"] for v in m.values()) == 31
    assert sum(v["deep"]["matched_goldens"] for v in m.values()) == 9
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_score_blocks.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement `score_blocks.py`** (`current_router_auc() -> float` included). Martian F1 at a threshold: micro recall = sum matched_goldens / 31, precision = sum matched_candidates / sum n_candidates over each PR's chosen tier.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass (17 existing + 17 new).

- [ ] **Step 5: Commit**

### Task 5: Full run, write-up

**Files:**
- Modify: `bugsinpy_bench/EXPERIMENT_LOG.md` (new step 11, timeline row, spend row)
- Add: cache files, `bugsinpy_bench/routing/blocks/*.json`, `bugsinpy_bench/routing/blocks_scores.json`

- [ ] **Step 1: Extract blocks for everything**

Run: `.venv/bin/python bugsinpy_bench/scripts/block_summaries.py --set bugsinpy` then `--set martian`.
Expected: 100 + 10 cache files; no errors; total cost printed.

- [ ] **Step 2: Route** (run in the background; arms and passes can run in parallel because each writes its own file)

Run: `route_blocks.py --set bugsinpy --arm {A,B} --pass {1,2}` and `--set martian --arm {A,B} --pass 1`.
Expected: 6 files; error count per file printed; any file with more than 5% of blocks erroring is rerun for those labels only.

- [ ] **Step 3: Score**

Run: `.venv/bin/python bugsinpy_bench/scripts/score_blocks.py`
Expected: AUC per arm and pass, T = 0.5 results, sweeps, and Martian results written to `blocks_scores.json`.

- [ ] **Step 4: Write step 11** in the experiment log: setup, question wording reference (point to `route_blocks.py`), AUC table (current router 0.27, arm A p1/p2, arm B p1/p2, Haiku complexity alone), T = 0.5 table on BugsInPy against triage (42, $14.15) and all-Opus 5.5 (42, $16.33), Martian held-out table, pass-to-pass agreement (share of bugs routed to the same tier), costs (Haiku dollars, Jev tokens and calls), and the limits (no clean PRs; 14 positives).

- [ ] **Step 5: Key scan, commit, push**

Run: `git diff --cached | grep -E "sk-ant-|TYPESAFE_API_KEY=."` (expect no output), then commit and `git push origin bench/model-tiers-pilot-local`.
