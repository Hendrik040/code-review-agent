# Could the impact context have caught the bugs every reviewer missed?

Scope: the 47 BugsInPy bugs that no model (Haiku, Sonnet, Opus 5.5) found in any run on
this branch (old context, Jev impact selection, verify prompt). For each, the reviewed
diff, the maintainer's fix and exactly what ODIS + Jev showed the reviewer were bundled
(`make_bundles.py` → `bundles/`), located mechanically (`analyze_missed.py` →
`missed_analysis.json`) and judged by four independent readers with one rubric
(`judgments_g*.json`, combined in `judgments_all.json`).

## Where the fixes are

| Fix location | Bugs |
|---|---|
| inside a function the reviewed diff changed | 43 |
| same file, other function | 4 |
| a file the diff did not touch | 0 |

The benchmark is built this way: BugsInPy's "introducing commit" is found by blaming the
fix lines, so the bug sits in the diff by construction. Impact context cannot help by
pointing at a hidden location; it can only supply knowledge needed to recognize the bug.
ODIS found no callers or callees at all for 19 of the 47, and Jev was involved in 5.

## What knowledge each bug needed

| Knowledge needed | Bugs | Context could help: yes / maybe |
|---|---|---|
| domain or spec (intended behavior, issue, docs) | 20 | 0 / 2 |
| contract of a repo function the change calls | 12 | 1 / 9 |
| third-party or stdlib behavior | 6 | 0 / 0 |
| project convention (how sibling code does it) | 4 | 1 / 2 |
| how existing callers use the changed code | 3 | 1 / 1 |
| nothing beyond the diff | 2 | 0 / 0 |
| **total** | **47** | **3 / 14** |

**Yes (3):** the repo held specific evidence that makes the bug recognizable.
- cookiecutter#1: every sibling file read in the repo passes `encoding='utf-8'`, one in
  the same file (`generate.py:177`); the change does not. ODIS had 0 candidates.
  (Checked: `config.py:46`, `generate.py:177`, `hooks.py:89` all pass it.)
- pandas#42: `assert_interval_array_equal` / `assert_extension_array_equal` require both
  arguments to be that type, contradicting the changed `or` dispatch. Not collected; ODIS
  showed 13 unrelated `.type` properties instead.
- thefuck#8: the rule mixes bytes operations with str values passed to `replace_command`
  in the same file. The diff was comment-only, so ODIS collected nothing.

**Maybe (14):** mostly callee contracts that name matching never reaches: methods called
on objects (`layer.compute_mask`, `Layer.output` may return a list, `io_loop.time`),
exceptions raised a few calls deep (`safe_cast` raising TypeError), predicates in a
changed condition (`holds_integer`), and sibling helpers (`get_base_url`).

## What ODIS and Jev did with that knowledge

| Needed knowledge was… | Bugs |
|---|---|
| shown in full | 2 (pandas#27, where it was not enough; spacy#5, where the bug did not exist yet) |
| shown as a signature or counted away by Jev | 0 |
| in the repo but never collected by ODIS | 18 |
| not in the repo (spec, external library, the diff itself) | 27 |

**Jev never dropped knowledge a reviewer needed.** The bottleneck is what ODIS collects:
name-matched callers and callees of the changed names miss method calls on objects,
transitive contracts, predicates and sibling implementations, while pulling in unrelated
same-name definitions (thefuck: every rule's `match`).

## Benchmark caveat

The readers flagged about 12 of the 47 where the introducing commit did not really
introduce the bug: code moved, reformatted or dedented with the bug already present
(black#1, keras#17, keras#26, matplotlib#14, matplotlib#21, pandas#27, pandas#61,
scrapy#10, tornado#5, tornado#11, tqdm#6), the bug in a different file than the oracle
line (httpie#2), behavior that only became a bug later (fastapi#12, pandas#22, spacy#5,
pandas#149), or tests at the time expecting the buggy behavior (ansible#15, pandas#61).
No reviewer can be expected to catch those from that diff.

## Reading

1. On this benchmark, better caller/callee context can move at most about 17 of 47
   missed bugs (3 likely, 14 possible). 27 need knowledge no repo context holds.
2. Selection is not the problem; collection is. In 18 cases the needed code existed and
   ODIS never collected it. More Jev questions over the same candidates would not help.
3. What to collect, in order of the cases above: contracts of callees reached through
   objects and attributes (needs type or import resolution, not name matching); bodies
   of predicates and helpers called in changed conditions; sibling implementations of
   the same job (same-file or same-package code doing the same call); and the exception
   and return contracts of those callees, summarized. Jev then judges relevance among
   those, with questions per kind (see the questions discussed for thefuck#26).
4. To measure such a change, BugsInPy-blame is the wrong yardstick: it selects bugs that
   sit in the diff, and a third of these are not fair at all. A set of contract-breaking
   changes (a signature or return change that breaks distant callers) would show whether
   context matters.
