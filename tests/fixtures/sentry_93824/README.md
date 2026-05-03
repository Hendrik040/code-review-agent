# Fixture: sentry_93824

Built from getsentry/sentry#93824 via `scripts/build_pr_fixture.py`.

- **Source PR**: https://github.com/getsentry/sentry/pull/93824
- **Title**: ref(span-buffer): Introduce multiprocessed flusher
- **base sha**: `de11fb0166a7244115bb066edd65ec0d6b7e365c`
- **head sha**: `3162ad68a5c87666788b27a44eb31235025091a9`
- **files** (6):
  CLAUDE.md  +11 -0  (modified)
  src/sentry/consumers/__init__.py  +9 -1  (modified)
  src/sentry/spans/consumers/process/factory.py  +3 -0  (modified)
  src/sentry/spans/consumers/process/flusher.py  +127 -47  (modified)
  tests/sentry/spans/consumers/process/test_consumer.py  +48 -1  (modified)
  tests/sentry/spans/consumers/process/test_flusher.py  +1 -1  (modified)

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
