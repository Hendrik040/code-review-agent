# Jev impact selection — design

Date: 2026-11-26. Branch: `claude/jev-impact-selection`, stacked on
`claude/jev-model-routing` (PR #30) because it reuses `shared/jev.py`.

## Why

`build_review_context` (ODIS) fills its "Impact Code" section by name
matching: every function or class in the repo whose name is called on a
changed line becomes a callee, and every bare-name call to a function whose
signature changed becomes a caller. Nothing judges relevance and nothing
caps the size.

Measured on the May 2026 BugsInPy sweep (100 bugs, Agent SDK):

- A typical context is mostly diff and changed-code snippets; callees are
  about 3% of it.
- When many functions share a name, the section explodes. `thefuck#7`
  changes one rule file that defines `match` and `get_new_command`; ODIS
  finds 675 candidates and builds a 449,000-character context, of which
  2,000 characters are the diff.
- In 13 of 100 bugs the Agent SDK refused the oversized tool result and
  returned an error pointing at a file on the host. The sandboxed agent
  could not read it and reviewed with no prepared context. Those 13 runs
  found the bug 0, 4 and 1 times at low, high and max effort, against 17,
  28 and 30 of 100 overall.

A spike on `thefuck#7` showed Jev can do the relevance judgment from a
one-line, code-extracted summary per candidate: 8 of 8 relevant candidates
scored 0.76 or higher and 29 of 29 unrelated ones scored 0.05 or lower, in
662 ms for 37 candidates. That is one easy case (file names disambiguate),
not a validation.

## Goals

1. The impact section never exceeds a fixed size, so the context always
   reaches the reviewer.
2. When there are more candidates than fit, the ones kept are chosen for
   relevance to the change, by Jev.
3. The reviewer is told what was left out, so it can fetch it with its own
   tools.
4. Reviews whose candidates all fit the impact budget, and whose whole
   context is under the total-size guard, get byte-identical context to
   today's.

## Non-goals

- New kinds of context (tests for the changed file, attribute and property
  accesses, PR description, guidelines). That is a later change that should
  reuse this mechanism.
- Stripping docs or tests from the diff. Docs are 159 of about 8,400
  changed lines in the benchmark.
- Changing how candidates are found, beyond recording one extra fact per
  candidate (see Candidates).
- Running the benchmark. Measurement is described below but is a separate,
  separately approved step: it costs money and its scripts live on
  `bench/bugsinpy`, not on this branch.

## Anti-goals

- A review that fails, or waits more than about 10 seconds, because Jev is
  slow, down or unconfigured.
- Candidates dropped silently.
- The TypeSafe key, or any Jev call, inside the sandbox.

## Approaches considered

- **A. Size cap only.** Order candidates by cheap facts (same
  file, imported by the changed file, not a test), stop at a budget. Fixes
  the 13 broken runs at no per-review cost, but when 200 functions share a
  name the choice among them is arbitrary.
- **B. Jev picks, cap as fallback (chosen).** Code lists candidates as
  today; Jev scores each one; the score decides how much of the candidate
  is shown. If Jev is unavailable the ordering from A is used. Chosen
  because it adds a relevance judgment where there is none, is small
  enough to measure, and degrades to A.
- **C. Jev also chooses what to add.** Widen the candidate pool to tests,
  properties, guidelines and learnings, one budget across all. Most likely
  to help the missed-bug cases, but each input is its own project and
  there is no context-quality measurement yet to tell which additions
  help. Deferred; B is its foundation.

Hendrik picked B on 2026-11-26.

## Design

### Where each step runs

ODIS runs next to the repo (inside the Daytona sandbox, or a host tempdir)
through `python -m shared.odis_cli`. Jev must run on the host. So
`build_review_context` in `shared/agent_tools.py` becomes two CLI calls
with the Jev call between them:

1. **Collect.** The CLI builds the diff, the changed-code snippets and the
   full candidate list, stores the candidates (with their snippets) in a
   file under `.git/odis/` inside the repo (the only place both backends'
   `upload_bytes` can write that `git status` and `git grep` ignore), and
   prints a JSON document: the diff, plus
   one summary per candidate. No snippet bodies cross the wire.
2. **Select** (host). Decide a tier for every candidate (below).
3. **Render.** The host uploads the decisions with `repo.upload_bytes`,
   also under `.git/odis/`; the CLI reads its stored candidates, prints the
   final markdown in the existing format and deletes both files.

There is no baked sandbox image: `sandbox/daytona.py::_bootstrap` uploads
the files in `_HOST_SHARED_FILES` into each sandbox. Any new module the CLI
needs must be added to that list and must not import host-only code
(`shared/jev.py`, the TypeSafe SDK).

Today's single-call form of the CLI (`odis_cli BASE..HEAD` printing
markdown) keeps working and is what `IMPACT_SELECT=off` uses.

### Candidates

Each candidate summary is extracted by code from the AST ODIS already
parses. No model writes it.

- role (`callee` or `caller`), file, line, symbol
- the line itself: the `def`/`class` line for a callee, the call line for
  a caller
- callee: first line of the docstring, if any
- caller: name of the enclosing function
- three computed facts, used for the fallback ordering and for logging:
  `same_file_as_change`, `imported_by_changed_file` (the changed file
  imports this candidate's module), and `is_test`

Candidates whose lines are already shown in the changed-code section are
dropped before selection, as today. Today's builder can emit the same
candidate twice; duplicates are removed only on the Jev and fallback
paths, never in the small case, so goal 4 holds.

### Selection

- **Small case, no Jev.** If all candidates fit the impact budget, every
  candidate is tier "full" and Jev is not called. This is the common case
  and its output is byte-identical to today's.
- **Otherwise Jev.** One yes/no (`noul`) question per candidate: is this
  the actual definition or call site the changed code refers to, such that
  a reviewer needs to see it to judge the change. Each request is one
  state (the diff plus that batch's candidate summaries) with one question
  per candidate. Jev's request limit is about 32,000 tokens; batches are
  sized to an estimated 24,000 (characters / 3) and run concurrently in a
  thread pool under one overall deadline (`IMPACT_SELECT_TIMEOUT`, default
  10 s). `shared/jev.py` has no timeout on `nouls()`, retries once, and
  has no batching: the per-request timeout and the deadline are built
  here. A diff over 24,000 characters is truncated to that length for Jev
  only, the same convention `shared/routing.py` uses.
- **Partial answers.** If some batches return and others fail or miss the
  deadline, the scores received are used; unscored candidates are placed
  after all scored ones, in fallback order, and can only be "signature" or
  "counted".
- **Fallback** (also what `IMPACT_SELECT=cap` does). No key, the SDK
  missing, or every batch failing: order candidates by same file, then
  imported by the changed file, then non-test, then path. Fill the budget
  in that order as "full", the next ones as "signature" up to the
  signature cap, the rest "counted".

### Tiers

| Jev probability | Tier | What the reviewer sees |
|---|---|---|
| at least `IMPACT_KEEP` (0.5) | full | The snippet, as today |
| at least `IMPACT_MENTION` (0.2) | signature | One line: file, line, the `def` or call line |
| below | counted | Nothing individual; grouped into a count |

Full-tier candidates are added highest probability first until the impact
budget (`IMPACT_MAX_CHARS`, default 12,000) is reached; any that do not
fit are demoted to signature. At most `IMPACT_MAX_SIGNATURES` (default
20) signature lines are shown, highest probability first; the rest are
counted. So the impact section is bounded by the budget, 20 lines and the
note.

After the callees and callers blocks, when anything was demoted or
counted, the section ends with a short note, for example:

```
Not shown: 254 other definitions of `match`, `get_new_command` and 417
other call sites, judged unrelated to this change. Use grep or
read_file_section if you need one.
```

On the fallback path nothing was judged, so the note says "not shown
(not ranked for relevance)" instead of "judged unrelated".

### Total-size guard

In `jev` and `cap` modes (not `off`), if the whole context would exceed
`CONTEXT_MAX_CHARS` (default 60,000), the changed-code section (which
repeats lines already in the diff) is replaced by a one-line note. The
diff itself is never cut.

### Configuration

`IMPACT_SELECT` = `jev` | `cap` | `off`. Default: `jev` when
`TYPESAFE_API_KEY` is set, else `cap`. `off` reproduces today's behaviour
for benchmark comparison. The other variables are named above and
documented in `.env.example`.

### Observability

One log line per call: candidate count, how many in each tier, which path
ran (small / jev / fallback and why), Jev latency and request count, final
context size.

### Untrusted input

Candidate text and the diff are repository content. Jev receives them as
state, never as instructions. The worst a hostile repo can do is push its
own code in or out of the impact section, which the reviewer can still
reach with its tools.

## Testing

- Unit tests with a fake Jev client (the `client=` seam in `shared/jev.py`):
  tiering at the thresholds, budget demotion, batching, the "not shown"
  note.
- Every fallback trigger produces the cap ordering and a logged reason.
- A fixture repo with many same-named functions reproduces the explosion
  and is held under the budget.
- The existing fixtures, which have few candidates, produce byte-identical
  context with `jev`, `cap` and `off`.
- Collect and render work through both `LocalRepo` and the CLI path used
  by `DaytonaRepo`; the Daytona image is not rebuilt in tests.

## Measurement (separate step, needs approval)

Re-run the 13 bugs that received an error context plus about 20 others, at
one effort level, three ways: `off`, `cap`, `jev`. Compare how often the
context arrives, target recall and cost. This needs an Anthropic key and a
spend go-ahead.

## Calls made here that Hendrik did not decide

- Stacking the branch on PR #30 instead of `main`.
- Skipping Jev when everything fits.
- The default numbers: 0.5, 0.2, 12,000, 60,000 and 10 s.
- Dropping the changed-code section, not the diff, under the total guard.
- The signature cap of 20, keeping partial Jev answers, truncating the
  diff for Jev at 24,000 characters, and storing the working files under
  `.git/odis/`.

## Left to the builder

File and function layout, the temp-file location and format, the exact
batching arithmetic, and the wording of the question, provided the
behaviour above holds.
