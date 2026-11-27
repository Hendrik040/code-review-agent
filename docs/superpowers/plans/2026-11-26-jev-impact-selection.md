# Jev Impact Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the "Impact Code" section of `build_review_context` bounded, and when it would overflow, let Jev choose which callers and callees the reviewer sees.

**Architecture:** ODIS is split into *collect* (find candidates, sandbox-side) and *render* (print markdown from a tier per candidate, sandbox-side). The host tool calls collect, decides tiers (Jev, or a fixed order when Jev is unavailable), uploads the decisions, and calls render. Pure tiering logic lives in a stdlib-only module both sides import; everything that talks to Jev lives in a host-only module.

**Tech Stack:** Python 3.10+, stdlib `ast`/`json`/`concurrent.futures`, `shared/jev.py` (typesafe-sdk), pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-11-26-jev-impact-selection-design.md` (approved 2026-11-26, keep threshold 0.5).

## Global Constraints

- Branch `claude/jev-impact-selection`, stacked on `claude/jev-model-routing`. Never commit to `main`; never push without the owner's go-ahead.
- Byte-identical output to today's `build_context` when every candidate fits the impact budget and the whole context is under `CONTEXT_MAX_CHARS`, in all three modes.
- Config (env, read at call time): `IMPACT_SELECT` = `jev` | `cap` | `off` (default `jev` if `TYPESAFE_API_KEY` is set, else `cap`; any other value → `cap` with a logged warning), `IMPACT_KEEP=0.5`, `IMPACT_MENTION=0.2`, `IMPACT_MAX_CHARS=12000`, `IMPACT_MAX_SIGNATURES=20`, `CONTEXT_MAX_CHARS=60000`, `IMPACT_SELECT_TIMEOUT=10` (seconds, overall).
- Jev: diff sent truncated to 24,000 characters; batches sized so `len(json(state)) + len(json(questions))` ≤ 72,000 characters (≈ 24,000 tokens at chars / 3); Jev is never called from inside the sandbox; the TypeSafe key never leaves the host.
- Sandbox-side modules import only the stdlib and other sandbox-side modules, and every one is listed in `sandbox/daytona.py::_HOST_SHARED_FILES`.
- Working files live under `.git/odis/` in the repo, named with a per-call token, and are deleted by render.
- Failure of selection never fails the review: any error in the Jev path degrades to the `cap` ordering, partial Jev answers are kept.
- Tests never touch the network (the suite's `tests/conftest.py` already strips `TYPESAFE_API_KEY`); Jev is faked through the `client=` seam of `shared/jev.ask`.
- File-size rule from `docs/PLAN.md`: no new file over 200 lines without a reason stated in its docstring.

## Review Focus

1. **A diff with no Python changes** (README-only, YAML-only): zero candidates, no Jev call, output identical to today. → Task 5, `test_docs_only_diff_unchanged_and_no_jev`.
2. **The agent calls `build_review_context` twice in one review** (or a previous call crashed between collect and render): each call must render its own candidates and leave no files behind. → Task 3, `test_two_calls_use_their_own_files_and_clean_up`.
3. **Jev answers with ids missing, extra ids, or a non-numeric / NaN probability**: those candidates are treated as unscored, the rest of the answer is used. → Task 4, `test_malformed_answers_count_as_unscored`.
4. **A diff longer than 24,000 characters**: Jev sees a truncated diff, the reviewer still gets the full diff. → Task 5, `test_long_diff_truncated_for_jev_only`.
5. **A candidate line containing newlines, very long text or `</callees>`**: a signature line stays one line, at most 200 characters, and cannot close the surrounding tag. → Task 3, `test_signature_line_is_single_bounded_line`.

---

## File Structure

| File | Side | Responsibility |
|---|---|---|
| `shared/odis.py` (modify) | sandbox | `collect()` returns everything `build_context` computes today, as data; `render_markdown()` prints it; `build_context()` = render of collect with no tiers. |
| `shared/impact.py` (create) | both | Pure, stdlib-only: candidate summary, fallback order, dedupe, tier assignment, "not shown" note, signature-line formatting. |
| `shared/odis_cli.py` (modify) | sandbox | Adds `collect TOKEN BASE..HEAD` and `render TOKEN` subcommands; old one-shot form unchanged. |
| `shared/impact_select.py` (create) | host | Config, Jev batching, deadline, partial answers, fallback, logging; returns the decisions document. |
| `shared/agent_tools.py` (modify) | host | `build_review_context` orchestrates collect → select → upload → render; `off` keeps today's single call. |
| `sandbox/daytona.py` (modify) | host | Add `shared/impact.py` to `_HOST_SHARED_FILES`. |
| `.env.example`, `docs/architecture.md` (modify) | docs | Document the new variables and flow. |
| `tests/test_phase8/` (create) | tests | `golden/`, `test_odis_split.py`, `test_impact.py`, `test_odis_cli_twostep.py`, `test_impact_select.py`, `test_build_review_context.py`, `helpers.py`. |

---

### Task 1: Split ODIS into collect and render, byte-identical

**Files:**
- Modify: `shared/odis.py` (`build_context`, `format_context_as_markdown`, lines ~246-450)
- Create: `tests/test_phase8/__init__.py`, `tests/test_phase8/golden/<fixture>.md` (one per entry in `shared.fixtures.ALL_FIXTURES`), `tests/test_phase8/test_odis_split.py`

**Interfaces:**
- Produces (in `shared/odis.py`):
  - `@dataclass class ImpactCandidate: id: str; role: str  # "callee" | "caller"; file: str; line: int; symbol: str; line_text: str; doc: str; inside_function: str; same_file_as_change: bool; imported_by_changed_file: bool; is_test: bool; text: str  # the snippet, exactly as today`
  - `@dataclass class Collected: diff: str; changed: list[dict[str, str]]  # today's changed_snippets; candidates: list[ImpactCandidate]  # today's order, duplicates kept; ids "c0", "c1", ...`
  - `def collect(repo: pathlib.Path, base_ref: str, head_ref: str) -> Collected`
  - `def render_markdown(c: Collected, tiers: dict[str, str] | None = None, note: str = "", drop_changed: bool = False) -> str` — `tiers=None` means every candidate full; Task 3 defines the other tiers.
  - `build_context(repo, base_ref, head_ref) -> str` keeps its signature and returns `render_markdown(collect(...))`.

- [ ] **Step 1: Create the environment and record goldens from the unmodified code**

Run: `uv sync && uv run python -c "from shared.fixtures import ALL_FIXTURES, materialize; from shared import odis; import pathlib
for f in ALL_FIXTURES:
    with materialize(f) as m: pathlib.Path(f'tests/test_phase8/golden/{f.name}.md').write_text(odis.build_context(m.repo.path, m.base_ref, m.head_ref))"`
(create `tests/test_phase8/golden/` first). Expected: one `.md` per fixture, each starting with `# Code Review Context`.

- [ ] **Step 2: Write the failing tests**

```python
@pytest.mark.parametrize("fx", ALL_FIXTURES, ids=lambda f: f.name)
def test_build_context_matches_golden(fx):
    with materialize(fx) as m:
        out = odis.build_context(m.repo.path, m.base_ref, m.head_ref)
    assert out == (GOLDEN / f"{fx.name}.md").read_text()

@pytest.mark.parametrize("fx", ALL_FIXTURES, ids=lambda f: f.name)
def test_collect_then_render_matches_golden(fx):
    with materialize(fx) as m:
        c = odis.collect(m.repo.path, m.base_ref, m.head_ref)
    assert odis.render_markdown(c) == (GOLDEN / f"{fx.name}.md").read_text()
    assert [x.id for x in c.candidates] == [f"c{i}" for i in range(len(c.candidates))]

def test_candidate_facts_on_contract_mismatch():
    with materialize(CONTRACT_MISMATCH) as m:
        c = odis.collect(m.repo.path, m.base_ref, m.head_ref)
    callee = next(x for x in c.candidates if x.role == "callee")
    assert callee.line_text.lstrip().startswith(("def ", "class "))
    assert callee.is_test is False
    assert all(x.text for x in c.candidates)
```

- [ ] **Step 3: Run to verify the split tests fail**

Run: `uv run pytest tests/test_phase8/test_odis_split.py -v`
Expected: golden tests PASS, `test_collect_then_render_matches_golden` and `test_candidate_facts_on_contract_mismatch` FAIL with `AttributeError: module 'shared.odis' has no attribute 'collect'`.

- [ ] **Step 4: Implement `collect`, `render_markdown`, `ImpactCandidate`, `Collected` in `shared/odis.py`**

Move the body of `build_context` into `collect`, appending `ImpactCandidate`s where it appends `impact_snippets` today (same order, same duplicates). Facts: `line_text` = the source line at `line` (the `def`/`class` line for callees, the call line for callers), stripped; `doc` = first line of `ast.get_docstring` for callees, else `""`; `inside_function` = name of the innermost enclosing function for callers, else `""`; `same_file_as_change` = file is in the diff; `imported_by_changed_file` = any changed `.py` file imports this file's module (by `ImportFrom.module` last component, imported name, or `Import` last component); `is_test` = a path part equal to `tests` or `test`, or basename matching `test_*.py` / `*_test.py`. `render_markdown` replaces `format_context_as_markdown` and must emit the exact same text for `tiers=None`. Fix the stale `/opt/code-review-agent` wording in `shared/agent_tools.py` docstrings while here.

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: `test_phase8` passes; no other test changes status versus the routing branch (`tests/test_phase6/test_ast_chunker.py` has 10 known environment failures).

- [ ] **Step 6: Commit**

```bash
git add shared/odis.py shared/agent_tools.py tests/test_phase8
git commit -m "refactor(odis): split build_context into collect and render"
```

---

### Task 2: Tier assignment, fallback order and the "not shown" note

**Files:**
- Create: `shared/impact.py`
- Test: `tests/test_phase8/test_impact.py`

**Interfaces:**
- Consumes: `ImpactCandidate` fields from Task 1 (by duck typing: `impact.py` must not import `shared.odis`).
- Produces (all in `shared/impact.py`, stdlib only):
  - `FULL, SIGNATURE, COUNTED = "full", "signature", "counted"`
  - `def summary(c) -> dict` — keys `role, file, line, symbol, line_text`, plus `docstring_first_line` / `inside_function` only when non-empty. This is exactly what Jev sees per candidate.
  - `def fallback_key(c) -> tuple` — `(not same_file_as_change, not imported_by_changed_file, is_test, file, line)`.
  - `def dedupe(cands: list) -> list` — first occurrence per `(role, file, line, symbol)`.
  - `def assign_tiers(cands: list, sizes: dict[str, int], scores: dict[str, float] | None, *, keep: float, mention: float, budget: int, max_signatures: int) -> dict[str, str]`
  - `def not_shown_note(cands: list, tiers: dict[str, str], *, ranked: bool) -> str`
  - `def signature_line(c) -> str`

- [ ] **Step 1: Write the failing tests**

```python
def C(i, role="callee", file="a.py", symbol="f", same=False, imp=False, test=False):
    return SimpleNamespace(id=f"c{i}", role=role, file=file, line=i + 1, symbol=symbol,
        line_text=f"def {symbol}():", doc="", inside_function="",
        same_file_as_change=same, imported_by_changed_file=imp, is_test=test)

def test_scores_map_to_tiers_at_thresholds():
    cs = [C(0), C(1), C(2), C(3)]
    t = impact.assign_tiers(cs, {c.id: 10 for c in cs}, {"c0": 0.5, "c1": 0.49, "c2": 0.2, "c3": 0.19},
                            keep=0.5, mention=0.2, budget=1000, max_signatures=20)
    assert t == {"c0": "full", "c1": "signature", "c2": "signature", "c3": "counted"}

def test_budget_demotes_lowest_full_and_skips_oversize():
    cs = [C(0), C(1), C(2)]
    t = impact.assign_tiers(cs, {"c0": 600, "c1": 900, "c2": 300}, {"c0": 0.9, "c1": 0.8, "c2": 0.7},
                            keep=0.5, mention=0.2, budget=1000, max_signatures=20)
    assert t == {"c0": "full", "c1": "signature", "c2": "full"}

def test_signature_cap_overflow_is_counted():
    cs = [C(i) for i in range(25)]
    t = impact.assign_tiers(cs, {c.id: 10 for c in cs}, {c.id: 0.3 for c in cs},
                            keep=0.5, mention=0.2, budget=1000, max_signatures=20)
    assert list(t.values()).count("signature") == 20 and list(t.values()).count("counted") == 5

def test_fallback_order_fills_budget_then_signatures():
    cs = [C(0, file="z.py"), C(1, file="b.py", imp=True), C(2, file="a.py", same=True), C(3, file="t.py", test=True, imp=True)]
    t = impact.assign_tiers(cs, {c.id: 400 for c in cs}, None, keep=0.5, mention=0.2, budget=800, max_signatures=1)
    assert t == {"c2": "full", "c1": "full", "c3": "signature", "c0": "counted"}

def test_partial_scores_put_unscored_after_scored():
    cs = [C(0), C(1, same=True)]
    t = impact.assign_tiers(cs, {"c0": 10, "c1": 10}, {"c0": 0.9}, keep=0.5, mention=0.2, budget=1000, max_signatures=20)
    assert t == {"c0": "full", "c1": "signature"}

def test_dedupe_keeps_first():
    a, b = C(0), C(0); b.id = "c1"
    assert [x.id for x in impact.dedupe([a, b])] == ["c0"]

def test_note_wording_ranked_and_unranked():
    cs = [C(0, symbol="match"), C(1, symbol="match"), C(2, role="caller", symbol="match")]
    tiers = {"c0": "full", "c1": "counted", "c2": "counted"}
    assert impact.not_shown_note(cs, tiers, ranked=True) == (
        "Not shown: 1 other definition of `match` and 1 other call site, judged unrelated "
        "to this change. Use grep or read_file_section if you need one.")
    assert "not ranked for relevance" in impact.not_shown_note(cs, tiers, ranked=False)
    assert impact.not_shown_note(cs, {k: "full" for k in tiers}, ranked=True) == ""
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_phase8/test_impact.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shared.impact'`.

- [ ] **Step 3: Implement `shared/impact.py`**

`assign_tiers`: with scores, candidates scored ≥ `keep` are full-candidates in descending score; scored ≥ `mention` and unscored are signature-candidates (scored by descending score first, then unscored by `fallback_key`); the rest counted. Without scores, every candidate is a full-candidate in `fallback_key` order. Fill the budget walking full-candidates in order, skipping any whose size does not fit and continuing; the ones that did not fit join the front of the signature-candidates. Take `max_signatures` signature-candidates in order; the rest are counted. Note copy, fixed: `"Not shown: {n} other definition(s) of {names} and {m} other call site(s), {why}. Use grep or read_file_section if you need one."` where `{names}` is up to five distinct symbols in backticks joined by `", "`, then `", …"`; a clause with a zero count is omitted (with its `" and "`); `{why}` is `"judged unrelated to this change"` when `ranked`, else `"not ranked for relevance"`; empty string when nothing is counted. `signature_line(c)`: `f"{c.file}:{c.line}  {text}"` where `text` is `line_text` with whitespace runs collapsed to one space, `<` replaced by `&lt;`, cut to 200 characters total.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_phase8/test_impact.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/impact.py tests/test_phase8/test_impact.py
git commit -m "feat(odis): tier assignment and fallback order for impact candidates"
```

---

### Task 3: Two-step CLI and tiered rendering

**Files:**
- Modify: `shared/odis.py` (`render_markdown`), `shared/odis_cli.py`, `sandbox/daytona.py:52-56`
- Create: `tests/test_phase8/helpers.py`, `tests/test_phase8/test_odis_cli_twostep.py`

**Interfaces:**
- Consumes: `collect`, `render_markdown`, `Collected`, `ImpactCandidate` (Task 1); `FULL/SIGNATURE/COUNTED`, `signature_line` (Task 2).
- Produces:
  - `render_markdown(c, tiers, note, drop_changed)` semantics: candidates absent from `tiers` are omitted (only duplicates are); `full` renders exactly as today; `signature` candidates render after the full ones inside the same `<callees>`/`<callers>` block as `<signature>{signature_line(c)}</signature>`, one per line; `counted` renders nothing; a non-empty `note` is printed after `</callers>` as `<not_shown>{note}</not_shown>` followed by a blank line; `drop_changed=True` replaces the body of section 2 with the single line `(Omitted to fit the context budget; the diff above shows every changed line.)`. An empty block still prints `None`.
  - CLI: `python -m shared.odis_cli collect TOKEN BASE..HEAD` → writes `.git/odis/TOKEN.collected.json` (the full `Collected`, including snippet text) and prints JSON `{"diff": str, "changed_chars": int, "candidates": [ {"id": str, "size": int, "summary": dict, "facts": {"same_file_as_change": bool, "imported_by_changed_file": bool, "is_test": bool}} ]}` where `size = len(text)`. `python -m shared.odis_cli render TOKEN` → reads `.git/odis/TOKEN.collected.json` and `.git/odis/TOKEN.decisions.json` (`{"tiers": dict | null, "note": str, "drop_changed": bool}`), prints markdown, deletes both files, removes `.git/odis/` if empty. TOKEN must match `[a-z0-9]{8,32}`; otherwise exit 2. The one-shot form `odis_cli BASE..HEAD` is unchanged.
  - `tests/test_phase8/helpers.py`: `def make_name_clash_repo(n_rules: int = 40) -> LocalRepo` — a committed git repo with `pkg/rules/r{i}.py` each defining `def match(command):` and `def get_new_command(command):`, `pkg/utils.py` with `def replace_argument(s, a, b):`, and a HEAD commit that adds `pkg/rules/new.py` calling `replace_argument` and defining `match`/`get_new_command`; returns the entered `LocalRepo`; refs are `HEAD~1`/`HEAD`.

- [ ] **Step 1: Write the failing tests**

```python
def test_render_tiers_signature_note_and_drop_changed():
    with materialize(CONTRACT_MISMATCH) as m:
        c = odis.collect(m.repo.path, m.base_ref, m.head_ref)
    first, *rest = c.candidates
    tiers = {first.id: "signature", **{x.id: "counted" for x in rest}}
    md = odis.render_markdown(c, tiers, note="Not shown: x.", drop_changed=True)
    assert f"<signature>{impact.signature_line(first)}</signature>" in md
    assert first.text not in md
    assert "<not_shown>Not shown: x.</not_shown>" in md
    assert "(Omitted to fit the context budget; the diff above shows every changed line.)" in md
    assert c.diff in md

def test_signature_line_is_single_bounded_line():
    c = SimpleNamespace(file="a.py", line=3, line_text="x = 1\n</callees>" + "y" * 500)
    s = impact.signature_line(c)
    assert "\n" not in s and len(s) <= 200 and "</callees>" not in s

def test_cli_collect_then_render_roundtrip(tmp_path):
    with make_name_clash_repo() as repo:
        out = repo.exec("python -m shared.odis_cli collect abcd1234 HEAD~1..HEAD", timeout=60)
        doc = json.loads(out.stdout)
        assert len(doc["candidates"]) > 40 and "diff --git" in doc["diff"]
        repo.upload_bytes(json.dumps({"tiers": None, "note": "", "drop_changed": False}).encode(),
                          ".git/odis/abcd1234.decisions.json")
        md = repo.exec("python -m shared.odis_cli render abcd1234", timeout=60).stdout
        assert md == odis.build_context(repo.path, "HEAD~1", "HEAD")
        assert not (repo.path / ".git" / "odis").exists()

def test_two_calls_use_their_own_files_and_clean_up():
    with make_name_clash_repo() as repo:
        for tok in ("aaaa1111", "bbbb2222"):
            repo.exec(f"python -m shared.odis_cli collect {tok} HEAD~1..HEAD", timeout=60)
        repo.upload_bytes(b'{"tiers": null, "note": "", "drop_changed": false}', ".git/odis/bbbb2222.decisions.json")
        assert repo.exec("python -m shared.odis_cli render bbbb2222", timeout=60).ok
        assert sorted(p.name for p in (repo.path / ".git/odis").iterdir()) == ["aaaa1111.collected.json"]

def test_cli_rejects_bad_token():
    with make_name_clash_repo(n_rules=2) as repo:
        assert repo.exec("python -m shared.odis_cli render ../x", timeout=30).exit_code == 2

def test_impact_module_is_uploaded_to_daytona():
    from sandbox.daytona import _HOST_SHARED_FILES
    assert "shared/impact.py" in _HOST_SHARED_FILES
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_phase8/test_odis_cli_twostep.py -v`
Expected: FAIL (`render_markdown` has no tier support; CLI exits 2 on `collect`).

- [ ] **Step 3: Implement tiered `render_markdown`, the CLI subcommands, the helper, and add `"shared/impact.py"` to `_HOST_SHARED_FILES`**

Serialize `Collected` with `dataclasses.asdict`; rebuild with `ImpactCandidate(**d)`. Create `.git/odis/` with `exist_ok=True`.

- [ ] **Step 4: Run Task 1-3 tests**

Run: `uv run pytest tests/test_phase8 -v`
Expected: all PASS, goldens still byte-identical.

- [ ] **Step 5: Commit**

```bash
git add shared/odis.py shared/odis_cli.py sandbox/daytona.py tests/test_phase8
git commit -m "feat(odis): two-step collect/render CLI with tiered impact rendering"
```

---

### Task 4: Host-side selection with Jev

**Files:**
- Create: `shared/impact_select.py`
- Test: `tests/test_phase8/test_impact_select.py`
- Modify: `tests/test_phase8/helpers.py` (add `FakeJev`, shown below, so Task 5 can import it)

**Interfaces:**
- Consumes: the collect JSON document (Task 3); `impact.assign_tiers`, `impact.not_shown_note`, `impact.dedupe`, `impact.FULL` (Task 2) — rebuild each candidate as `SimpleNamespace(id=d["id"], **d["summary"], **d["facts"])` (missing optional summary keys default to `""`) so `fallback_key`, `dedupe` and the note work on it; `shared.jev.ask(state, questions, *, timeout, client)` and `shared.jev.has_key()`.
- Produces:
  - `@dataclass class Config: mode: str; keep: float; mention: float; budget: int; max_signatures: int; context_max: int; timeout: float` and `def load_config() -> Config` (env names and defaults from Global Constraints).
  - `QUESTION = "Candidate `candidates.{cid}` was found by name matching. Is it the actual definition or call site that the changed code in `diff` refers to, so that a reviewer needs to see it to judge whether the change is correct?"` — exact copy.
  - `def score(diff: str, candidates: list[dict], *, timeout: float, client=None) -> dict[str, float]` — one entry per candidate Jev answered validly; never raises.
  - `def decide(doc: dict, cfg: Config, *, client=None) -> tuple[dict, dict]` — returns `(decisions, log)` where `decisions = {"tiers": dict | None, "note": str, "drop_changed": bool}` and `log = {"path": "small"|"jev"|"fallback"|"off", "reason": str, "candidates": int, "tiers": {"full": n, "signature": n, "counted": n}, "jev_ms": int, "requests": int}`.

- [ ] **Step 1: Write the failing tests**

```python
class FakeJev:
    def __init__(self, probs=None, error=None, drop=(), delay=0.0):
        self.probs, self.error, self.drop, self.delay, self.calls = probs or {}, error, set(drop), delay, []
    def system_one(self, state, questions):
        self.calls.append((state, questions)); time.sleep(self.delay)
        if self.error: raise self.error
        return SimpleNamespace(nouls={q: SimpleNamespace(noul=self.probs.get(q, 0.03)) for q in questions if q not in self.drop})

def doc(n, size=1000, diff="diff --git a/x.py b/x.py\n+x\n"):
    return {"diff": diff, "changed_chars": 100, "candidates": [
        {"id": f"c{i}", "size": size, "facts": {"same_file_as_change": False, "imported_by_changed_file": False, "is_test": False},
         "summary": {"role": "callee", "file": f"r{i}.py", "line": 1, "symbol": "match", "line_text": "def match(command):"}}
        for i in range(n)]}

CFG = Config(mode="jev", keep=0.5, mention=0.2, budget=12000, max_signatures=20, context_max=60000, timeout=10)

def test_small_case_skips_jev():
    jev = FakeJev()
    d, log = decide(doc(5), CFG, client=jev)
    assert d == {"tiers": None, "note": "", "drop_changed": False} and log["path"] == "small" and jev.calls == []

def test_jev_path_tiers_and_note():
    d, log = decide(doc(40), CFG, client=FakeJev({"c3": 0.9, "c7": 0.3}))
    assert d["tiers"]["c3"] == "full" and d["tiers"]["c7"] == "signature" and d["tiers"]["c0"] == "counted"
    assert "judged unrelated" in d["note"] and log["path"] == "jev"

def test_question_copy_and_state_shape():
    jev = FakeJev(); decide(doc(40), CFG, client=jev)
    state, questions = jev.calls[0]
    assert set(state) == {"diff", "candidates"}
    assert questions["c0"] == {"type": "noul", "instructions": QUESTION.format(cid="c0")}

def test_batches_respect_size_limit():
    jev = FakeJev(); decide(doc(600, diff="+" * 24000), CFG, client=jev)
    assert len(jev.calls) > 1
    assert all(len(json.dumps(s)) + len(json.dumps(q)) <= 72000 for s, q in jev.calls)
    assert sum(len(q) for _, q in jev.calls) == 600

def test_jev_error_falls_back_to_cap_order():
    d, log = decide(doc(40), CFG, client=FakeJev(error=RuntimeError("down")))
    assert log["path"] == "fallback" and "down" in log["reason"]
    assert "not ranked for relevance" in d["note"]

def test_malformed_answers_count_as_unscored():
    jev = FakeJev({"c1": float("nan"), "c2": 0.9}, drop={"c0"})
    d, _ = decide(doc(40), CFG, client=jev)
    assert d["tiers"]["c2"] == "full" and d["tiers"]["c0"] in ("signature", "counted") and d["tiers"]["c1"] in ("signature", "counted")

def test_deadline_bounds_the_wait():
    cfg = replace(CFG, timeout=0.5)
    slow = FakeJev(delay=2.0)
    d, log = decide(doc(600, diff="+" * 24000), cfg, client=slow)
    assert log["path"] == "fallback" and log["jev_ms"] < 1500

def test_no_key_means_cap(monkeypatch):
    monkeypatch.delenv("IMPACT_SELECT", raising=False)
    assert load_config().mode == "cap"
    monkeypatch.setenv("IMPACT_SELECT", "bogus"); assert load_config().mode == "cap"

def test_total_guard_drops_changed_section():
    big = doc(5); big["changed_chars"] = 70000
    d, _ = decide(big, CFG)
    assert d["drop_changed"] is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_phase8/test_impact_select.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shared.impact_select'`.

- [ ] **Step 3: Implement `shared/impact_select.py`**

`decide`: `off` mode is never passed here (Task 5 handles it). Small case = `sum(size) ≤ budget` → `tiers=None`. Otherwise dedupe, then `jev` mode calls `score` (with `client=None` and no key → fallback reason `"no TYPESAFE_API_KEY"`), `cap` mode skips it; `ranked = bool(scores)`. `drop_changed` = `len(diff) + changed_chars + rendered impact size > context_max`, where rendered impact size is the sum of full-tier sizes plus 200 per signature plus `len(note)`. `score`: diff cut to 24,000 chars; greedily pack candidates into batches under the 72,000-char limit; run `jev.ask(state, questions, timeout=cfg.timeout, client=client)` per batch in a `ThreadPoolExecutor`; `concurrent.futures.wait(..., timeout=cfg.timeout)`; collect `resp.nouls[cid].noul` where present and finite in `[0, 1]`; `executor.shutdown(wait=False, cancel_futures=True)`. Log one line via `logging.getLogger("shared.impact_select")`: `impact_select path=%s reason=%s candidates=%d full=%d signature=%d counted=%d jev_ms=%d requests=%d`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_phase8/test_impact_select.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/impact_select.py tests/test_phase8/test_impact_select.py
git commit -m "feat(odis): Jev-ranked impact selection with cap fallback"
```

---

### Task 5: Wire into `build_review_context`, document, verify end to end

**Files:**
- Modify: `shared/agent_tools.py:196-219`, `.env.example`, `docs/architecture.md`
- Test: `tests/test_phase8/test_build_review_context.py`

**Interfaces:**
- Consumes: CLI subcommands and helper (Task 3); `load_config`, `decide` (Task 4).
- Produces: `build_review_context(repo: Repo, base_ref: str, head_ref: str, *, jev_client=None) -> str` — same return contract and error-string format as today; `jev_client` is a test seam only. Both reviewers keep calling it without the new keyword.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("mode", ["jev", "cap", "off"])
def test_small_fixture_identical_in_every_mode(mode, monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", mode)
    with materialize(CONTRACT_MISMATCH) as m:
        assert build_review_context(m.repo, m.base_ref, m.head_ref, jev_client=FakeJev()) == \
               (GOLDEN / "contract_mismatch.md").read_text()

def test_name_clash_repo_is_bounded_and_annotated(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "jev"); monkeypatch.setenv("IMPACT_MAX_CHARS", "2000")
    with make_name_clash_repo(n_rules=200) as repo:
        full = odis.build_context(repo.path, "HEAD~1", "HEAD")
        out = build_review_context(repo, "HEAD~1", "HEAD", jev_client=FakeJev({}))
        assert len(out) < len(full) / 5 and "<not_shown>" in out
        assert not (repo.path / ".git" / "odis").exists()

def test_docs_only_diff_unchanged_and_no_jev(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "jev")
    with make_name_clash_repo(n_rules=2) as repo:
        repo.exec("echo hi >> README.md && git add -A && git commit -qm docs", timeout=30)
        jev = FakeJev()
        assert build_review_context(repo, "HEAD~1", "HEAD", jev_client=jev) == odis.build_context(repo.path, "HEAD~1", "HEAD")
        assert jev.calls == []

def test_long_diff_truncated_for_jev_only(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "jev"); monkeypatch.setenv("IMPACT_MAX_CHARS", "2000")
    with make_name_clash_repo(n_rules=200) as repo:
        repo.exec("python - <<'E'\nopen('pkg/rules/new.py','a').write('\\n' + '# pad\\n' * 6000)\nE\ngit add -A && git commit -qm pad", timeout=30)
        jev = FakeJev(); out = build_review_context(repo, "HEAD~2", "HEAD", jev_client=jev)
        assert all(len(s["diff"]) <= 24000 for s, _ in jev.calls) and out.count("# pad") >= 6000

def test_collect_failure_keeps_todays_error_format(monkeypatch):
    monkeypatch.setenv("IMPACT_SELECT", "jev")
    with make_name_clash_repo(n_rules=2) as repo:
        assert build_review_context(repo, "nope", "HEAD").startswith("Error: build_review_context failed (exit ")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_phase8/test_build_review_context.py -v`
Expected: FAIL with `TypeError: build_review_context() got an unexpected keyword argument 'jev_client'`.

- [ ] **Step 3: Implement the orchestration in `shared/agent_tools.py`**

`cfg = load_config()`; `off` → today's single CLI call, untouched. Otherwise: `token = secrets.token_hex(8)`; run `collect` (failure → today's error string); `decisions, log = decide(doc, cfg, client=jev_client)`; `repo.upload_bytes(json.dumps(decisions).encode(), f".git/odis/{token}.decisions.json")`; run `render` (failure → today's error string, prefixed the same way); return its stdout. Any exception from `decide` → log it and retry once with `decide(doc, dataclasses.replace(cfg, mode="cap"))`; if that or the upload also fails, upload `{"tiers": null, "note": "", "drop_changed": false}` (today's output) so the review still gets a context.

- [ ] **Step 4: Document**

`.env.example`: an "Optional — impact selection" block listing the seven variables with their defaults and one line each. `docs/architecture.md`: in the ODIS section, a 6-10 line description of collect → select (host, Jev) → render, the three tiers, and the fallback.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: all `test_phase8` PASS; no other test changes status versus the routing branch.

- [ ] **Step 6: Live check against real Jev (host only, no Anthropic spend)**

Run (key exported from the main checkout's `.env`, never printed): `IMPACT_SELECT=jev IMPACT_MAX_CHARS=2000 uv run python -c "import logging; logging.basicConfig(level=logging.INFO); from tests.test_phase8.helpers import make_name_clash_repo; from shared.agent_tools import build_review_context
with make_name_clash_repo(200) as r: print(build_review_context(r, 'HEAD~1', 'HEAD')[-1500:])"`
Expected: the log line shows `path=jev`, `requests=` at least 1 and `jev_ms` under 10000; the `replace_argument` callee from `pkg/utils.py` is rendered in full; the output ends with a `<not_shown>` note saying "judged unrelated".

- [ ] **Step 7: Commit**

```bash
git add shared/agent_tools.py .env.example docs/architecture.md tests/test_phase8/test_build_review_context.py
git commit -m "feat(odis): route build_review_context through Jev impact selection"
```
