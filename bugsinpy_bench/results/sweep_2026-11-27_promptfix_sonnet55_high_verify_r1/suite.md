# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_promptfix_sonnet55_high_verify_r1

Model: `claude-sonnet-5-5`.  Line tolerance: ±10.  N: 10 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| pandas#26 | blame | 5 | $0.1387 | 1 | Y | Y | submit_findings | 27.9 | run_647 |
| thefuck#7 | blame | 3 | $0.0363 | 1 | Y | Y | submit_findings | 13.8 | run_653 |
| ansible#15 | blame | 4 | $0.0459 | 0 | N | N | submit_findings | 24.2 | run_657 |
| pandas#108 | blame | 6 | $0.0874 | 0 | N | N | submit_findings | 23.9 | run_664 |
| pandas#121 | blame | 10 | $0.1212 | 2 | Y | N | submit_findings | 46.5 | run_669 |
| thefuck#12 | blame | 4 | $0.0526 | 0 | N | N | submit_findings | 12.1 | run_677 |
| thefuck#20 | blame | 7 | $0.0657 | 2 | Y | Y | submit_findings | 26.5 | run_681 |
| thefuck#21 | blame | 4 | $0.0625 | 2 | Y | Y | submit_findings | 18.1 | run_684 |
| thefuck#26 | blame | 3 | $0.0356 | 1 | Y | Y | submit_findings | 11.5 | run_689 |
| thefuck#28 | blame | 5 | $0.0627 | 2 | Y | Y | submit_findings | 18.5 | run_692 |

**Summary:** 10 entries, total cost $0.7086, total turns 51, file-hit 7/10, line-hit 6/10.
