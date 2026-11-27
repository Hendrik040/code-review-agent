# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_promptfix_opus55_high_old_r1

Model: `claude-opus-5-5`.  Line tolerance: ±10.  N: 10 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| pandas#26 | blame | 8 | $0.3130 | 1 | Y | Y | submit_findings | 45.3 | run_651 |
| thefuck#7 | blame | 6 | $0.1058 | 0 | N | N | submit_findings | 27.0 | run_658 |
| ansible#15 | blame | 6 | $0.0879 | 0 | N | N | submit_findings | 33.4 | run_667 |
| pandas#108 | blame | 9 | $0.1846 | 0 | N | N | submit_findings | 34.7 | run_672 |
| pandas#121 | blame | 12 | $0.3588 | 4 | Y | N | submit_findings | 80.4 | run_678 |
| thefuck#12 | blame | 7 | $0.1327 | 0 | N | N | submit_findings | 22.9 | run_695 |
| thefuck#20 | blame | 7 | $0.1812 | 4 | Y | Y | submit_findings | 41.6 | run_697 |
| thefuck#21 | blame | 6 | $0.1232 | 1 | Y | N | submit_findings | 29.9 | run_701 |
| thefuck#26 | blame | 5 | $0.0927 | 1 | Y | Y | submit_findings | 23.1 | run_705 |
| thefuck#28 | blame | 6 | $0.1391 | 3 | Y | Y | submit_findings | 38.4 | run_706 |

**Summary:** 10 entries, total cost $1.7190, total turns 72, file-hit 6/10, line-hit 4/10.
