# Agent SDK reviewer suite run 008

Line tolerance: +/- 10.  SDK: agent.

| fixture | turns | cost (USD) | findings | expected | file hit | line +/-10 | exit | latency (s) | run_id |
|---|---:|---:|---:|---:|:---:|:---:|---|---:|---:|
| contract_mismatch | 4 | $0.1749 | 1 | 2 | Y | Y | submit_findings | 28.5 | run_029 |
| sentry_80168 | 29 | $1.7868 | 1 | 1 | N | N | submit_findings | 360.5 | run_030 |
| sentry_80528 | 9 | $0.5526 | 1 | 1 | Y | Y | submit_findings | 87.0 | run_031 |
| sentry_67876 | 17 | $1.3786 | 2 | 1 | Y | N | submit_findings | 431.2 | run_032 |
| sentry_93824 | 12 | $0.9296 | 2 | 1 | N | N | submit_findings | 221.6 | run_033 |
| sentry_77754 | 15 | $0.5928 | 1 | 1 | Y | Y | submit_findings | 129.8 | run_034 |
| sentry_95633 | 25 | $1.9766 | 1 | 1 | N | N | submit_findings | 627.4 | run_035 |

**Summary (complete):** 7 fixtures, total cost $7.3919, total turns 111, file-hit 4/7, line-hit 3/7. Wall time so far: 1885.9s.
