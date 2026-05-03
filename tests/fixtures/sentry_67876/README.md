# Fixture: sentry_67876

Built from getsentry/sentry#67876 via `scripts/build_pr_fixture.py`.

- **Source PR**: https://github.com/getsentry/sentry/pull/67876
- **Title**: fix(security): validate GitHub user during integration installation
- **base sha**: `344aa102e7818606e29426ebe69d5a680d8727c6`
- **head sha**: `bb75657fc8f13923c1d7983f422290908a1e7310`
- **files** (3):
  src/sentry/integrations/github/integration.py  +118 -41  (modified)
  src/sentry/web/frontend/pipeline_advancer.py  +4 -7  (modified)
  tests/sentry/integrations/github/test_integration.py  +125 -2  (modified)

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
