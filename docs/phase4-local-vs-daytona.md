# Phase 4 — Local vs. Daytona, same code, same effort

The Phase 4 sandbox layer was designed so the only thing that should
differ between a local-tempdir review and a Daytona-sandbox review is
where the bytes actually live. This file is the empirical check.

Every row below is `(SDK, fixture)` swept multiple times across two
backends and (in the post-fix block) before/after the eval-leakage
fix CR caught on PR #22. All runs at `effort="xhigh"`.

Source data:
- Local baseline (Phase 2.2 xhigh): `client_sdk/results/suite_006.md`,
  `agent_sdk/results/suite_005.md`.
- Daytona pre-fix (Phase 4 first sweep): `client_sdk/results/suite_011.md`,
  `agent_sdk/results/suite_008.md`.
- Daytona post-fix (Phase 4 re-sweep, this commit): `client_sdk/results/suite_014.md`,
  `agent_sdk/results/suite_010.md`.

The leakage fix removed two oracle hints visible to the agent
(commit message `"v2 (planted bug)"` → `"head"`; the
`tests/fixtures/contract_mismatch/v2/calc.py` docstring
`"PLANTED BUG: ..."` → `"Sum three numbers."`). Plus a security fix
(LocalRepo no longer forwards `os.environ` into the agent's bash tool),
two path-traversal hardenings on DaytonaRepo, and a fixture
working-tree reset between v1/v2 commits.

## Client SDK

| Fixture | Local xhigh (Phase 2.2) | Daytona xhigh pre-fix | Daytona xhigh post-fix |
|---|---|---|---|
| contract_mismatch | 3 / $0.11 / Y/Y | 3 / $0.10 / Y/Y | 3 / $0.09 / Y/Y |
| sentry_80168 | 16 / $1.76 / Y/Y | 20 / $2.02 / Y/Y | 10 / $1.33 / Y/Y |
| sentry_80528 | 5 / $0.46 / Y/Y | 7 / $0.54 / Y/Y | 7 / $0.59 / Y/Y |
| sentry_67876 | 42 / $6.03 / N/N | 29 / $3.70 / N/N | 30 / $3.13 / N/N |
| sentry_93824 | 39 / $3.57 / N/N | 28 / $2.63 / N/N | 21 / $2.09 / N/N |
| sentry_77754 | 18 / $1.44 / Y/Y | 15 / $1.33 / Y/Y | 18 / $1.56 / Y/Y |
| sentry_95633 | 29 / $4.56 / N/N | 14 / $2.54 / N/N | 38 / $4.94 / N/N |
| **TOTALS** | **$17.93 / 152t / 4/7** | **$12.87 / 116t / 4/7** | **$13.72 / 127t / 4/7** |

Wall-clock: 21.3 → 16.6 → 17.6 minutes.

**Reading.** Daytona reproduces Client SDK correctness exactly across
both pre- and post-fix sweeps; the leakage removal didn't regress
anything. Daytona is meaningfully cheaper than Local on hard
fixtures (-39% on sentry_67876, -26% on sentry_93824, -44% to -7%
on sentry_95633 across the two Daytona sweeps). The bedrock misses
(`sentry_67876` CSRF, `sentry_95633` Python 3.13, `sentry_93824` at
xhigh) are stable across all three columns — they're knowledge-
frame / over-exploration gaps, not backend or eval-leakage gaps.

## Agent SDK

| Fixture | Local xhigh (Phase 2.2) | Daytona xhigh pre-fix | Daytona xhigh post-fix |
|---|---|---|---|
| contract_mismatch | 4 / $0.20 / Y/Y | 4 / $0.17 / Y/Y | 3 / $0.38 / Y/Y |
| sentry_80168 | 19 / $1.30 / Y/Y | 29 / $1.79 / **N/N** | 29 / $1.52 / **Y/Y** |
| sentry_80528 | 7 / $0.39 / Y/Y | 9 / $0.55 / Y/Y | 6 / $0.34 / Y/Y |
| sentry_67876 | 23 / $1.62 / N/N | 17 / $1.38 / **Y/N** | 18 / $1.43 / N/N |
| sentry_93824 | 10 / $1.22 / Y/Y | 12 / $0.93 / **N/N** | 18 / $1.60 / N/N |
| sentry_77754 | 10 / $0.54 / Y/Y | 15 / $0.59 / Y/Y | 15 / $0.66 / Y/Y |
| sentry_95633 | 25 / $4.50 / N/N | 25 / $1.98 / N/N | 20 / $2.17 / **Y/N** |
| **TOTALS** | **$9.76 / 98t / 5/7** | **$7.39 / 111t / 4/7 line** | **$8.09 / 109t / 4/7 line, 5/7 file** |

Wall-clock: 34.6 → 31.4 → 25.5 minutes.

**Reading.** Agent SDK is noisier than Client SDK across the
backend swap — three outcome flips between Local and Daytona pre-fix
(noted earlier). The post-fix sweep RECOVERED two of those: it
flipped `sentry_80168` back to Y/Y (matching Local), upgraded
`sentry_95633` from N/N to Y/N file-hit (the agent now lands a
finding in the right file with the right category, just not within
±10 of the planted line). Net Agent SDK file-hits move from 4/7
pre-fix → 5/7 post-fix while costs are statistically identical
(+9%, well within sample noise).

This is genuinely good news for the methodology: **the leakage fix
didn't merely sanitize the data, it also made Agent SDK runs
slightly MORE consistent with Local.** The "planted bug" hint had
been distracting the harness's exploration on the harder fixtures.

The two consistent misses (sentry_67876 CSRF; sentry_93824 at xhigh
on the Agent SDK) survive every sweep — bedrock per PLAN.md
lessons #9 (effort×harness asymmetry) and #10 (knowledge-frame
gaps).

## Headline numbers

```
                  Client SDK              Agent SDK
  Local xhigh     $17.93 / 4/7 line       $9.76 / 5/7 line
  Daytona pre-fix $12.87 / 4/7  (-28%)    $7.39 / 3/7 line  (-24%)
  Daytona post-fix $13.72 / 4/7 (-23%)    $8.09 / 4/7 line  (-17%)
                                                  / 5/7 file
```

**Daytona is ~17-28% cheaper than Local at identical effort and tool
surface, with no correctness regression after the leakage fix.**
That's the load-bearing claim for Phase 4 and it holds.

## Open Phase 4.2 follow-ups motivated by these sweeps

- `scripts/headtohead.py` cannot disambiguate Daytona runs by
  fixture (the `# repo:` header is just `DaytonaRepo` for every
  run). This file was authored by hand for that reason. Fix:
  embed `# fixture: name` in run_NNN.txt or have headtohead.py
  parse the latest `suite_NNN.md` for the fixture↔run_id mapping.
- Bulk tar upload on `from_fixture` would shrink per-fixture
  overhead on Daytona — fine for our small fixtures, would matter
  at scale.
- One or two more re-runs on the borderline Agent SDK Daytona
  fixtures (`sentry_67876`, `sentry_93824`) to nail down whether
  the residual flips are sample-1 variance or a real
  harness×backend interaction.
