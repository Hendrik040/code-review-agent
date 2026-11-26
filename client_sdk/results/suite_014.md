<!-- Cost figures recomputed by scripts/reeval_suite.py --cost-only from each run's stored usage at the current pricing.py rate; nothing else in this file was changed. -->

# Client SDK reviewer suite run 014

Line tolerance: +/- 10.  SDK: client.

| fixture | turns | cost (USD) | findings | expected | file hit | line +/-10 | exit | latency (s) | run_id |
|---|---:|---:|---:|---:|:---:|:---:|---|---:|---:|
| contract_mismatch | 3 | $0.0285 | 1 | 2 | Y | Y | stop_reason_end_turn | 17.6 | run_046 |
| sentry_80168 | 10 | $0.4420 | 1 | 1 | Y | Y | stop_reason_end_turn | 80.1 | run_047 |
| sentry_80528 | 7 | $0.1957 | 1 | 1 | Y | Y | stop_reason_end_turn | 44.9 | run_048 |
| sentry_67876 | 30 | $1.0436 | 3 | 1 | N | N | stop_reason_end_turn | 262.9 | run_049 |
| sentry_93824 | 21 | $0.6967 | 1 | 1 | N | N | stop_reason_end_turn | 171.1 | run_050 |
| sentry_77754 | 18 | $0.5216 | 1 | 1 | Y | Y | stop_reason_end_turn | 127.6 | run_051 |
| sentry_95633 | 38 | $1.6464 | 3 | 1 | N | N | stop_reason_end_turn | 354.4 | run_052 |

**Summary (complete):** 7 fixtures, total cost $4.5746, total turns 127, file-hit 4/7, line-hit 4/7. Wall time so far: 1058.5s.
