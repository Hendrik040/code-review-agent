# Fixture: sentry_95633

Built from getsentry/sentry#95633 via `scripts/build_pr_fixture.py`.

- **Source PR**: https://github.com/getsentry/sentry/pull/95633
- **Title**: feat(uptime): Add ability to use queues to manage parallelism
- **base sha**: `fd358e8a388939959369f08f616e29552cdaf96e`
- **head sha**: `9966ec5a13e331659c3ea00981f9b11b0faf821f`
- **files** (7):
  src/sentry/consumers/__init__.py  +2 -2  (modified)
  src/sentry/remote_subscriptions/consumers/queue_consumer.py  +345 -0  (added)
  src/sentry/remote_subscriptions/consumers/result_consumer.py  +41 -3  (modified)
  tests/sentry/remote_subscriptions/__init__.py  +0 -0  (added)
  tests/sentry/remote_subscriptions/consumers/__init__.py  +0 -0  (added)
  tests/sentry/remote_subscriptions/consumers/test_queue_consumer.py  +421 -0  (added)
  tests/sentry/uptime/consumers/test_results_consumer.py  +467 -1  (modified)

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
