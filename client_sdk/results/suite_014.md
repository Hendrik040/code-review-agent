# Client SDK reviewer suite run 014

Line tolerance: +/- 10.  SDK: client.

| fixture | turns | cost (USD) | findings | expected | file hit | line +/-10 | exit | latency (s) | run_id |
|---|---:|---:|---:|---:|:---:|:---:|---|---:|---:|
| contract_mismatch | 3 | $0.0856 | 1 | 2 | Y | Y | stop_reason_end_turn | 17.6 | run_046 |
| sentry_80168 | 10 | $1.3261 | 1 | 1 | Y | Y | stop_reason_end_turn | 80.1 | run_047 |
| sentry_80528 | 7 | $0.5872 | 1 | 1 | Y | Y | stop_reason_end_turn | 44.9 | run_048 |
| sentry_67876 | 30 | $3.1308 | 3 | 1 | N | N | stop_reason_end_turn | 262.9 | run_049 |
| sentry_93824 | 21 | $2.0902 | 1 | 1 | N | N | stop_reason_end_turn | 171.1 | run_050 |
| sentry_77754 | 18 | $1.5649 | 1 | 1 | Y | Y | stop_reason_end_turn | 127.6 | run_051 |
| sentry_95633 | 38 | $4.9392 | 3 | 1 | N | N | stop_reason_end_turn | 354.4 | run_052 |

**Summary (complete):** 7 fixtures, total cost $13.7239, total turns 127, file-hit 4/7, line-hit 4/7. Wall time so far: 1058.5s.
