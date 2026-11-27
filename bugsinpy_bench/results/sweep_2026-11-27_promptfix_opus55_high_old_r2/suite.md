# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_promptfix_opus55_high_old_r2

Model: `claude-opus-5-5`.  Line tolerance: ±10.  N: 10 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| pandas#26 | blame | 9 | $0.2050 | 2 | Y | Y | submit_findings | 49.2 | run_707 |
| thefuck#7 | blame | 4 | $0.0911 | 0 | N | N | stop_reason_end_turn | 17.1 | run_717 |
| ansible#15 | blame | 6 | $0.0885 | 0 | N | N | submit_findings | 25.1 | run_723 |
| pandas#108 | blame | 9 | $0.1819 | 0 | N | N | submit_findings | 32.8 | run_729 |
| pandas#121 | blame | 12 | $0.3296 | 3 | Y | N | submit_findings | 73.6 | run_734 |
| thefuck#12 | blame | 6 | $0.1310 | 0 | N | N | submit_findings | 21.7 | run_747 |
| thefuck#20 | blame | 6 | $0.1431 | 3 | Y | Y | submit_findings | 31.0 | run_754 |
| thefuck#21 | blame | 7 | $0.1598 | 1 | Y | N | submit_findings | 35.8 | run_758 |
| thefuck#26 | blame | 7 | $0.1325 | 2 | Y | Y | submit_findings | 23.8 | run_761 |
| thefuck#28 | blame | 8 | $0.2379 | 3 | Y | Y | submit_findings | 60.0 | run_764 |

**Summary:** 10 entries, total cost $1.7005, total turns 74, file-hit 6/10, line-hit 4/10.
