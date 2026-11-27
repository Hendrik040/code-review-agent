# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_promptfix_opus55_high_verify_r1

Model: `claude-opus-5-5`.  Line tolerance: ±10.  N: 10 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| pandas#26 | blame | 7 | $0.3494 | 1 | Y | Y | submit_findings | 48.0 | run_650 |
| thefuck#7 | blame | 3 | $0.1111 | 1 | Y | Y | submit_findings | 21.5 | run_660 |
| ansible#15 | blame | 4 | $0.1012 | 0 | N | N | submit_findings | 24.4 | run_665 |
| pandas#108 | blame | 6 | $0.2007 | 0 | N | N | submit_findings | 30.3 | run_670 |
| pandas#121 | blame | 9 | $0.3555 | 4 | Y | N | submit_findings | 79.0 | run_675 |
| thefuck#12 | blame | 4 | $0.1307 | 0 | N | N | submit_findings | 20.6 | run_691 |
| thefuck#20 | blame | 4 | $0.1153 | 2 | Y | Y | submit_findings | 26.3 | run_696 |
| thefuck#21 | blame | 5 | $0.1675 | 2 | Y | Y | submit_findings | 33.0 | run_699 |
| thefuck#26 | blame | 4 | $0.1089 | 2 | Y | Y | submit_findings | 19.3 | run_700 |
| thefuck#28 | blame | 4 | $0.1689 | 2 | Y | Y | submit_findings | 37.9 | run_703 |

**Summary:** 10 entries, total cost $1.8093, total turns 50, file-hit 7/10, line-hit 6/10.
