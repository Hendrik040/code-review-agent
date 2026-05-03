# Fixture: sentry_80528

Built from getsentry/sentry#80528 via `scripts/build_pr_fixture.py`.

- **Source PR**: https://github.com/getsentry/sentry/pull/80528
- **Title**: ref(crons): Reorganize incident creation / issue occurrence logic
- **base sha**: `0cfc28e76ddc986d2d89dd9b9f63ee916a18a5f9`
- **head sha**: `dcdcadb771128e79259cc9eff9c70c38fc597976`
- **files** (4):
  src/sentry/monitors/logic/incident_occurrence.py  +171 -0  (added)
  src/sentry/monitors/logic/incidents.py  +104 -0  (added)
  src/sentry/monitors/logic/mark_failed.py  +4 -264  (modified)
  src/sentry/monitors/types.py  +10 -0  (modified)

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
