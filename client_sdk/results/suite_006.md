<!-- Cost figures recomputed by scripts/reeval_suite.py --cost-only from each run's stored usage at the current pricing.py rate; nothing else in this file was changed. -->

# Client SDK reviewer suite run 006

Line tolerance: +/- 10.  SDK: client.

| fixture | turns | cost (USD) | findings | expected | file hit | line +/-10 | exit | latency (s) | run_id |
|---|---:|---:|---:|---:|:---:|:---:|---|---:|---:|
| contract_mismatch | 3 | $0.0359 | 1 | 2 | Y | Y | stop_reason_end_turn | 12.3 | run_029 |
| sentry_80168 | 16 | $0.5862 | 1 | 1 | Y | Y | stop_reason_end_turn | 100.7 | run_030 |
| sentry_80528 | 5 | $0.1544 | 1 | 1 | Y | Y | stop_reason_end_turn | 29.4 | run_031 |
| sentry_67876 | 42 | $2.0086 | 2 | 1 | N | N | stop_reason_end_turn | 468.3 | run_032 |
| sentry_93824 | 39 | $1.1890 | 1 | 1 | N | N | stop_reason_end_turn | 258.5 | run_033 |
| sentry_77754 | 18 | $0.4816 | 1 | 1 | Y | Y | stop_reason_end_turn | 94.3 | run_034 |
| sentry_95633 | 29 | $1.5196 | 2 | 1 | N | N | stop_reason_end_turn | 315.9 | run_035 |

**Summary (complete):** 7 fixtures, total cost $5.9752, total turns 152, file-hit 4/7, line-hit 4/7. Wall time so far: 1279.3s.
