# Offline cascade test: can Jev tell which reviews need a second pass?

Date: 2026-11-27. Branch: `bench/model-tiers-pilot-local`. Written and committed
before any Jev answer for this test exists, so the questions, the rule and the
success bar below are fixed in advance.

## Why

Routing a PR to one model from its diff does not work well here: the current depth
score ranks the bugs only Opus finds below the bugs Haiku finds, and the block-level
questions (step 10 of `bugsinpy_bench/EXPERIMENT_LOG.md`) ended at chance. Part of the
reason is that the target is noisy: a second Haiku run found 3 of the 6 "needs Opus"
bugs that have one.

A cascade asks a different question. The cheap model reviews every PR first. Jev then
reads that finished review and decides whether a stronger model should take a second
look, and the two sets of findings are merged. This is TypeSafe's documented cascade
pattern (cheap model, narrow verifier checks, escalate on a flag). On stored results:

| Haiku first, Opus 5.5 added on | Found | Cost |
|---|---:|---:|
| no PR (Haiku alone) | 35 | $0.52 |
| a random half (expected) | 42.0 | $8.68 |
| exactly the PRs where Haiku missed (upper bound) | 49 | $10.41 |
| every PR | 49 | $16.85 |

A useful signal moves the middle rows toward the upper bound.

## What Jev sees

One call per stored review. State, built from files already in the repo:

- `pull_request_title`: first line of the bug-introducing commit.
- `files_changed`: path, lines added, lines removed.
- `findings`: what the reviewer submitted (file, line, severity, category, summary;
  summary cut at 300 characters).
- `closing_message`: the reviewer's own text from the turn that called
  `submit_findings` onward, cut at 6,000 characters. Reviews that never submitted have
  the text of their last turn.

Jev does not see the diff, the judge's verdict, or any other model's review. All of
this is available in production: the reviewer's trace holds the closing message.

## Questions (yes/no; yes is a reason for a second look)

| id | Instructions |
|---|---|
| `unfiled_issue` | Does `closing_message` describe a defect, risk or questionable behaviour in the changed code that is not covered by any entry in `findings`? |
| `dismissed_as_intended` | Does `closing_message` say the reviewer noticed a behaviour change or problem but did not report it because it looks intentional, pre-existing, out of scope or low impact? |
| `could_not_verify` | Does `closing_message` say the reviewer was unable to run, test or otherwise confirm something about the changed code? |

Three questions on purpose. Step 10 took a maximum over about 45 answers per PR and
the score saturated.

## Rule

- `flag` = the largest of the three probabilities. A review that ended without
  `submit_findings`, or whose Jev call failed, has `flag` 1.0.
- Escalate when `flag` >= 0.5. The whole range 0.05 to 0.95 is reported as a curve.
- Each arm is asked twice, to measure how much Jev's answers move between calls.

## Scoring (stored results only, no new reviews)

`first` reviews every bug; `second` is added on the escalated bugs. A bug is found if
either found it. Cost is the stored review cost of `first` on all 100 bugs plus
`second` on the escalated ones. Jev's own cost is reported separately.

- **Ranking:** AUC of `flag` for the reviews where `first` missed and `second` found
  (the gain cases) against all other reviews of `first`. 0.5 is chance.
- **Against random:** at the declared threshold, the share of 10,000 random escalation
  sets of the same size that find at least as many bugs.
- **Baselines without Jev:** "the reviewer filed nothing", the number of turns, and
  the current router's P(deep).

Test sets:

| First pass | Second pass | Gain cases | Status |
|---|---|---:|---|
| Haiku 5.5 | Opus 5.5 | 14 | primary |
| Haiku 5.5 | Sonnet 5.5 | 10 | secondary |
| Sonnet 5.5 | Opus 5.5 | 8 | secondary |
| Opus 5.5 | Haiku 5.5 | 7 | not a clean test: the questions were written after reading Opus 5.5's traces for these bugs |

## Success bar

On the primary set, in both passes: AUC of `flag` at least 0.70, and at threshold 0.5
the cascade finds at least as many bugs as 95% of random escalation sets of the same
size. Anything less is reported as "no usable signal".

## Limits known in advance

- 14 gain cases: an AUC from them has a standard error of about 0.08.
- One review run per model per bug. BugsInPy counts only whether the target bug was
  found, so the extra false positives from merging two reviews are not measured here.
- BugsInPy only. Martian is left out, as in step 10.
