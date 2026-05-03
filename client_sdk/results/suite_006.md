# Client SDK reviewer suite run 006

Line tolerance: +/- 10.  SDK: client.

| fixture | turns | cost (USD) | findings | expected | file hit | line +/-10 | exit | latency (s) | run_id |
|---|---:|---:|---:|---:|:---:|:---:|---|---:|---:|
| contract_mismatch | 3 | $0.1076 | 1 | 2 | Y | Y | stop_reason_end_turn | 12.3 | run_029 |
| sentry_80168 | 16 | $1.7587 | 1 | 1 | Y | Y | stop_reason_end_turn | 100.7 | run_030 |
| sentry_80528 | 5 | $0.4632 | 1 | 1 | Y | Y | stop_reason_end_turn | 29.4 | run_031 |
| sentry_67876 | 42 | $6.0257 | 2 | 1 | N | N | stop_reason_end_turn | 468.3 | run_032 |
| sentry_93824 | 39 | $3.5669 | 1 | 1 | N | N | stop_reason_end_turn | 258.5 | run_033 |
| sentry_77754 | 18 | $1.4447 | 1 | 1 | Y | Y | stop_reason_end_turn | 94.3 | run_034 |
| sentry_95633 | 29 | $4.5587 | 2 | 1 | N | N | stop_reason_end_turn | 315.9 | run_035 |

**Summary (complete):** 7 fixtures, total cost $17.9255, total turns 152, file-hit 4/7, line-hit 4/7. Wall time so far: 1279.3s.
