# Fixture: contract-mismatch

A two-commit Python project with a planted **contract-mismatch bug**:
the signature of `calc.add` is changed in `v2/` from `add(a, b)` to
`add(a, b, c)`, but the caller in `main.py` is not updated. The diff
alone is innocuous — the bug only appears when you look at the *unchanged*
caller.

This is exactly the case ODIS is built to surface: the call site lands
in the `<callers>` block of the review context, and a competent reviewer
flags the missing argument.

## Layout

- `v1/` — bug-free state. The reviewer should NOT find anything here.
- `v2/` — same files with the planted change. The reviewer SHOULD flag
  the call site.

The loader (`shared/fixtures.py:load_contract_mismatch`) copies `v1/`
into a temp directory, commits it as `v1`, then overwrites with `v2/`
and commits as `v2`. The returned fixture exposes `repo_path`,
`base_ref="HEAD~1"`, `head_ref="HEAD"`, and the expected `Finding`.

## Why we don't use the baseline's `demo_project`

The pinned baseline submodule (`code-review-baseline/ai-code-reviewer`)
references `demo_project/` as a gitlink but ships no `.gitmodules`
entry, so the content is unrecoverable from our snapshot. Building our
own fixture also means we control the bug shape and expected findings,
which Phase 3 needs for evaluation.
