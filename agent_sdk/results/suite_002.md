# Agent SDK reviewer suite run 002

Line tolerance: +/- 10.  SDK: agent.

| fixture | turns | cost (USD) | findings | expected | file hit | line +/-10 | exit | latency (s) | run_id |
|---|---:|---:|---:|---:|:---:|:---:|---|---:|---:|
| contract_mismatch | 4 | $0.1472 | 1 | 2 | Y | Y | submit_findings | 24.5 | run_010 |
| sentry_80168 | 14 | $1.0005 | 1 | 1 | Y | Y | submit_findings | 237.8 | run_011 |
| sentry_80528 | 8 | $0.3259 | 0 | 1 | N | N | submit_findings | 81.7 | run_012 |
| sentry_67876 | 20 | $0.9539 | 2 | 1 | Y | N | submit_findings | 355.1 | run_013 |
| sentry_93824 | 8 | $0.8168 | 1 | 1 | Y | N | submit_findings | 249.3 | run_014 |
| sentry_77754 | 12 | $0.4950 | 1 | 1 | Y | Y | submit_findings | 150.2 | run_015 |
| sentry_95633 | 21 | $2.0512 | 2 | 1 | Y | N | submit_findings | 999.8 | run_016 |

**Summary (complete):** 7 fixtures, total cost $5.7905, total turns 87, file-hit 6/7, line-hit 3/7. Wall time so far: 2098.3s.
