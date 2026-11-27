# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_impactsel_opus55_high_aff16

Model: `claude-opus-5-5`.  Line tolerance: ±10.  N: 16 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| PySnooper#3 | blame | 4 | $0.2965 | 1 | Y | Y | submit_findings | 19.1 | run_564 |
| luigi#5 | blame | 5 | $0.3506 | 2 | Y | N | submit_findings | 35.3 | run_569 |
| pandas#26 | blame | 6 | $0.1795 | 1 | Y | Y | submit_findings | 34.7 | run_572 |
| thefuck#1 | blame | 4 | $0.1194 | 1 | Y | Y | submit_findings | 26.2 | run_577 |
| thefuck#7 | blame | 3 | $0.1014 | 1 | Y | Y | submit_findings | 22.0 | run_582 |
| ansible#15 | blame | 4 | $0.0979 | 0 | N | N | submit_findings | 21.6 | run_584 |
| pandas#108 | blame | 5 | $0.2034 | 0 | N | N | submit_findings | 28.1 | run_587 |
| pandas#121 | blame | 7 | $0.2368 | 2 | Y | N | submit_findings | 55.5 | run_589 |
| thefuck#12 | blame | 4 | $0.1323 | 0 | N | N | submit_findings | 20.1 | run_597 |
| thefuck#15 | blame | 3 | $0.0840 | 1 | Y | Y | submit_findings | 14.9 | run_601 |
| thefuck#20 | blame | 6 | $0.1554 | 3 | Y | Y | submit_findings | 33.8 | run_603 |
| thefuck#21 | blame | 5 | $0.1836 | 2 | Y | Y | submit_findings | 33.9 | run_607 |
| thefuck#25 | blame | 3 | $0.2312 | 1 | Y | Y | submit_findings | 17.3 | run_608 |
| thefuck#26 | blame | 5 | $0.1216 | 2 | Y | Y | submit_findings | 21.3 | run_609 |
| thefuck#28 | blame | 4 | $0.1509 | 2 | Y | Y | submit_findings | 31.6 | run_610 |
| thefuck#32 | blame | 3 | $0.0704 | 0 | N | N | submit_findings | 7.8 | run_611 |

**Summary:** 16 entries, total cost $2.7147, total turns 71, file-hit 12/16, line-hit 10/16.
