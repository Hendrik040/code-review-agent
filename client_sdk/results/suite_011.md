# Client SDK reviewer suite run 011

Line tolerance: +/- 10.  SDK: client.

| fixture | turns | cost (USD) | findings | expected | file hit | line +/-10 | exit | latency (s) | run_id |
|---|---:|---:|---:|---:|:---:|:---:|---|---:|---:|
| contract_mismatch | 3 | $0.1028 | 1 | 2 | Y | Y | stop_reason_end_turn | 18.5 | run_038 |
| sentry_80168 | 20 | $2.0177 | 1 | 1 | Y | Y | stop_reason_end_turn | 113.4 | run_039 |
| sentry_80528 | 7 | $0.5411 | 1 | 1 | Y | Y | stop_reason_end_turn | 44.6 | run_040 |
| sentry_67876 | 29 | $3.7012 | 0 | 1 | N | N | stop_reason_end_turn | 326.1 | run_041 |
| sentry_93824 | 28 | $2.6298 | 2 | 1 | N | N | stop_reason_end_turn | 208.5 | run_042 |
| sentry_77754 | 15 | $1.3349 | 1 | 1 | Y | Y | stop_reason_end_turn | 109.0 | run_043 |
| sentry_95633 | 14 | $2.5446 | 3 | 1 | N | N | stop_reason_end_turn | 174.7 | run_044 |

**Summary (complete):** 7 fixtures, total cost $12.8720, total turns 116, file-hit 4/7, line-hit 4/7. Wall time so far: 994.7s.
