# Fixture: sentry_80168

Built from getsentry/sentry#80168 via `scripts/build_pr_fixture.py`.

- **Source PR**: https://github.com/getsentry/sentry/pull/80168
- **Title**: feat(workflow_engine): Add in hook for producing occurrences from the stateful detector
- **base sha**: `bdd229e3f22e307fe40b30ef99e92ff3f6723da4`
- **head sha**: `8422030ef456e3a898415e96475b4d8ddfc7640f`
- **files** (4):
  src/sentry/incidents/grouptype.py  +3 -8  (modified)
  src/sentry/workflow_engine/models/detector.py  +7 -1  (modified)
  src/sentry/workflow_engine/processors/detector.py  +22 -23  (modified)
  tests/sentry/workflow_engine/processors/test_detector.py  +217 -119  (modified)

## Layout

- `v1/` — files at `base_sha` (the bug-free state for this PR's purposes;
  in reality the bug is INTRODUCED at head_sha for some PRs and FIXED at
  head_sha for others — read the headline bug from the fixture's expected
  Finding to know which).
- `v2/` — files at `head_sha`.

The loader (`shared/fixtures.py:_materialize`) recursively copies these
trees into a temp git repo, commits `v1` then `v2`, returns refs
`HEAD~1..HEAD`.

## License notice

Source code is from getsentry/sentry and retains its upstream license.
This snapshot is included as a code-review evaluation fixture; not for
redistribution as a product.
