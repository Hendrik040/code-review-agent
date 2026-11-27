# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_promptfix_sonnet55_high_verify_r2

Model: `claude-sonnet-5-5`.  Line tolerance: ±10.  N: 10 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| pandas#26 | blame | 5 | $0.0584 | 1 | Y | Y | submit_findings | 32.2 | run_710 |
| thefuck#7 | blame | 3 | $0.0359 | 1 | Y | Y | submit_findings | 13.3 | run_713 |
| ansible#15 | blame | 4 | $0.0391 | 0 | N | N | submit_findings | 20.6 | run_716 |
| pandas#108 | blame | 8 | $0.1141 | 0 | N | N | submit_findings | 39.5 | run_725 |
| pandas#121 | blame | 5 | $0.0827 | 2 | Y | N | submit_findings | 33.7 | run_731 |
| thefuck#12 | blame | 4 | $0.0522 | 0 | N | N | submit_findings | 12.0 | run_736 |
| thefuck#20 | blame | 6 | $0.0572 | 2 | Y | Y | submit_findings | 22.7 | run_739 |
| thefuck#21 | blame | 6 | $0.0746 | 1 | Y | Y | submit_findings | 23.6 | run_743 |
| thefuck#26 | blame | 3 | $0.0340 | 1 | Y | Y | submit_findings | 11.2 | run_746 |
| thefuck#28 | blame | 4 | $0.0577 | 1 | Y | N | submit_findings | 17.1 | run_752 |

**Summary:** 10 entries, total cost $0.6059, total turns 48, file-hit 7/10, line-hit 5/10.
