# Fixture: sentry_77754

Built from getsentry/sentry#77754 via `scripts/build_pr_fixture.py`.

- **Source PR**: https://github.com/getsentry/sentry/pull/77754
- **Title**: fix(ecosystem): Breaks issue sync cycles
- **base sha**: `bb5a6837cb5b3d8d3b174e17d42ec14486ef8738`
- **head sha**: `9501091c52ae94e8d916f79b35d21975b3f9cadb`
- **files** (7):
  src/sentry/integrations/mixins/issues.py  +18 -3  (modified)
  src/sentry/integrations/services/assignment_source.py  +35 -0  (added)
  src/sentry/integrations/tasks/sync_assignee_outbound.py  +16 -3  (modified)
  src/sentry/integrations/utils/sync.py  +25 -4  (modified)
  src/sentry/models/groupassignee.py  +9 -2  (modified)
  tests/sentry/integrations/services/test_assignment_source.py  +38 -0  (added)
  tests/sentry/models/test_groupassignee.py  +71 -3  (modified)

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
