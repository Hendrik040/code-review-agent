# Agent SDK reviewer suite run 005

Line tolerance: +/- 10.  SDK: agent.

| fixture | turns | cost (USD) | findings | expected | file hit | line +/-10 | exit | latency (s) | run_id |
|---|---:|---:|---:|---:|:---:|:---:|---|---:|---:|
| contract_mismatch | 4 | $0.1993 | 1 | 2 | Y | Y | submit_findings | 20.7 | run_020 |
| sentry_80168 | 19 | $1.2952 | 1 | 1 | Y | Y | submit_findings | 198.0 | run_021 |
| sentry_80528 | 7 | $0.3902 | 1 | 1 | Y | Y | submit_findings | 65.1 | run_022 |
| sentry_67876 | 23 | $1.6211 | 3 | 1 | N | N | submit_findings | 385.5 | run_023 |
| sentry_93824 | 10 | $1.2177 | 2 | 1 | Y | Y | submit_findings | 250.6 | run_024 |
| sentry_77754 | 10 | $0.5389 | 1 | 1 | Y | Y | submit_findings | 92.3 | run_025 |
| sentry_95633 | 25 | $4.4991 | 0 | 1 | N | N | submit_findings | 1062.8 | run_026 |

**Summary (complete):** 7 fixtures, total cost $9.7615, total turns 98, file-hit 5/7, line-hit 5/7. Wall time so far: 2074.9s.
