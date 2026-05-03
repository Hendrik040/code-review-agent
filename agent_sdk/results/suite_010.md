# Agent SDK reviewer suite run 010

Line tolerance: +/- 10.  SDK: agent.

| fixture | turns | cost (USD) | findings | expected | file hit | line +/-10 | exit | latency (s) | run_id |
|---|---:|---:|---:|---:|:---:|:---:|---|---:|---:|
| contract_mismatch | 3 | $0.3758 | 1 | 2 | Y | Y | submit_findings | 23.2 | run_036 |
| sentry_80168 | 29 | $1.5199 | 1 | 1 | Y | Y | submit_findings | 185.8 | run_037 |
| sentry_80528 | 6 | $0.3439 | 1 | 1 | Y | Y | submit_findings | 59.1 | run_038 |
| sentry_67876 | 18 | $1.4277 | 2 | 1 | N | N | submit_findings | 308.5 | run_039 |
| sentry_93824 | 18 | $1.6038 | 3 | 1 | N | N | submit_findings | 352.7 | run_040 |
| sentry_77754 | 15 | $0.6570 | 1 | 1 | Y | Y | submit_findings | 133.5 | run_041 |
| sentry_95633 | 20 | $2.1651 | 3 | 1 | Y | N | submit_findings | 469.4 | run_042 |

**Summary (complete):** 7 fixtures, total cost $8.0932, total turns 109, file-hit 5/7, line-hit 4/7. Wall time so far: 1532.1s.
