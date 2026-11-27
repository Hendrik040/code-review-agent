# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_impactsel_sonnet55_high_aff16

Model: `claude-sonnet-5-5`.  Line tolerance: ±10.  N: 16 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| PySnooper#3 | blame | 5 | $0.1469 | 1 | Y | Y | submit_findings | 15.6 | run_566 |
| luigi#5 | blame | 7 | $0.1697 | 1 | Y | N | submit_findings | 24.7 | run_567 |
| pandas#26 | blame | 5 | $0.0563 | 1 | Y | Y | submit_findings | 22.1 | run_570 |
| thefuck#1 | blame | 3 | $0.0336 | 1 | Y | Y | submit_findings | 11.9 | run_573 |
| thefuck#7 | blame | 3 | $0.1098 | 0 | N | N | submit_findings | 17.9 | run_575 |
| ansible#15 | blame | 4 | $0.0404 | 0 | N | N | submit_findings | 22.2 | run_579 |
| pandas#108 | blame | 7 | $0.1010 | 0 | N | N | submit_findings | 25.3 | run_581 |
| pandas#121 | blame | 11 | $0.1443 | 2 | Y | N | submit_findings | 51.7 | run_585 |
| thefuck#12 | blame | 5 | $0.0562 | 0 | N | N | submit_findings | 12.0 | run_590 |
| thefuck#15 | blame | 4 | $0.0382 | 2 | Y | Y | submit_findings | 14.6 | run_592 |
| thefuck#20 | blame | 4 | $0.0427 | 1 | Y | Y | submit_findings | 17.1 | run_594 |
| thefuck#21 | blame | 6 | $0.0718 | 2 | Y | Y | submit_findings | 23.3 | run_595 |
| thefuck#25 | blame | 3 | $0.0296 | 1 | Y | Y | submit_findings | 12.2 | run_599 |
| thefuck#26 | blame | 3 | $0.0366 | 1 | Y | Y | submit_findings | 11.0 | run_602 |
| thefuck#28 | blame | 5 | $0.0655 | 2 | Y | Y | submit_findings | 23.9 | run_604 |
| thefuck#32 | blame | 4 | $0.0311 | 0 | N | N | submit_findings | 6.8 | run_606 |

**Summary:** 16 entries, total cost $1.1737, total turns 79, file-hit 11/16, line-hit 9/16.
