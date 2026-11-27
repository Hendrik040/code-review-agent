# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_impactsel_opus55_high_aff16_rep2

Model: `claude-opus-5-5`.  Line tolerance: ±10.  N: 16 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| PySnooper#3 | blame | 4 | $0.1686 | 2 | Y | Y | submit_findings | 24.4 | run_612 |
| luigi#5 | blame | 5 | $0.2040 | 2 | Y | N | submit_findings | 32.8 | run_613 |
| pandas#26 | blame | 6 | $0.1638 | 1 | Y | Y | submit_findings | 33.2 | run_617 |
| thefuck#1 | blame | 3 | $0.1053 | 2 | Y | Y | submit_findings | 23.3 | run_618 |
| thefuck#7 | blame | 3 | $0.0846 | 0 | N | N | submit_findings | 17.1 | run_619 |
| ansible#15 | blame | 4 | $0.0998 | 0 | N | N | submit_findings | 23.4 | run_621 |
| pandas#108 | blame | 7 | $0.2272 | 0 | N | N | submit_findings | 32.7 | run_624 |
| pandas#121 | blame | 8 | $0.2900 | 3 | Y | N | submit_findings | 67.6 | run_626 |
| thefuck#12 | blame | 4 | $0.1294 | 0 | N | N | submit_findings | 18.5 | run_629 |
| thefuck#15 | blame | 3 | $0.0883 | 1 | Y | Y | submit_findings | 16.6 | run_631 |
| thefuck#20 | blame | 4 | $0.1178 | 3 | Y | Y | submit_findings | 27.3 | run_633 |
| thefuck#21 | blame | 6 | $0.1856 | 2 | Y | N | submit_findings | 33.6 | run_634 |
| thefuck#25 | blame | 4 | $0.1084 | 1 | Y | Y | submit_findings | 19.4 | run_637 |
| thefuck#26 | blame | 5 | $0.1229 | 2 | Y | Y | submit_findings | 20.3 | run_639 |
| thefuck#28 | blame | 4 | $0.1458 | 2 | Y | Y | submit_findings | 28.0 | run_640 |
| thefuck#32 | blame | 4 | $0.0839 | 0 | N | N | submit_findings | 12.6 | run_642 |

**Summary:** 16 entries, total cost $2.3255, total turns 74, file-hit 11/16, line-hit 8/16.
