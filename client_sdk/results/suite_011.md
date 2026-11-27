<!-- Cost figures recomputed by scripts/reeval_suite.py --cost-only from each run's stored usage at the current pricing.py rate; nothing else in this file was changed. -->

# Client SDK reviewer suite run 011

Line tolerance: +/- 10.  SDK: client.

| fixture | turns | cost (USD) | findings | expected | file hit | line +/-10 | exit | latency (s) | run_id |
|---|---:|---:|---:|---:|:---:|:---:|---|---:|---:|
| contract_mismatch | 3 | $0.0343 | 1 | 2 | Y | Y | stop_reason_end_turn | 18.5 | run_038 |
| sentry_80168 | 20 | $0.6726 | 1 | 1 | Y | Y | stop_reason_end_turn | 113.4 | run_039 |
| sentry_80528 | 7 | $0.1804 | 1 | 1 | Y | Y | stop_reason_end_turn | 44.6 | run_040 |
| sentry_67876 | 29 | $1.2337 | 0 | 1 | N | N | stop_reason_end_turn | 326.1 | run_041 |
| sentry_93824 | 28 | $0.8766 | 2 | 1 | N | N | stop_reason_end_turn | 208.5 | run_042 |
| sentry_77754 | 15 | $0.4450 | 1 | 1 | Y | Y | stop_reason_end_turn | 109.0 | run_043 |
| sentry_95633 | 14 | $0.8482 | 3 | 1 | N | N | stop_reason_end_turn | 174.7 | run_044 |

**Summary (complete):** 7 fixtures, total cost $4.2907, total turns 116, file-hit 4/7, line-hit 4/7. Wall time so far: 994.7s.
