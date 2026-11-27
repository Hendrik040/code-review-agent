# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_promptfix_sonnet55_high_old_r2

Model: `claude-sonnet-5-5`.  Line tolerance: ±10.  N: 10 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| pandas#26 | blame | 6 | $0.0552 | 1 | Y | Y | submit_findings | 35.9 | run_709 |
| thefuck#7 | blame | 7 | $0.0496 | 0 | N | N | submit_findings | 18.1 | run_715 |
| ansible#15 | blame | 6 | $0.0487 | 0 | N | N | submit_findings | 22.1 | run_720 |
| pandas#108 | blame | 9 | $0.1017 | 0 | N | N | submit_findings | 36.4 | run_726 |
| pandas#121 | blame | 11 | $0.1117 | 1 | Y | N | submit_findings | 42.1 | run_733 |
| thefuck#12 | blame | 6 | $0.0496 | 0 | N | N | submit_findings | 19.1 | run_740 |
| thefuck#20 | blame | 8 | $0.0602 | 2 | Y | Y | submit_findings | 24.7 | run_744 |
| thefuck#21 | blame | 6 | $0.0589 | 1 | Y | Y | submit_findings | 19.5 | run_748 |
| thefuck#26 | blame | 5 | $0.0430 | 2 | Y | Y | submit_findings | 18.4 | run_753 |
| thefuck#28 | blame | 6 | $0.0514 | 1 | Y | N | submit_findings | 17.9 | run_757 |

**Summary:** 10 entries, total cost $0.6303, total turns 70, file-hit 6/10, line-hit 4/10.
