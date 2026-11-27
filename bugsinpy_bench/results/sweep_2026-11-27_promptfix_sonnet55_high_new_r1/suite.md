# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_promptfix_sonnet55_high_new_r1

Model: `claude-sonnet-5-5`.  Line tolerance: ±10.  N: 10 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| pandas#26 | blame | 4 | $0.1329 | 1 | Y | Y | submit_findings | 28.2 | run_648 |
| thefuck#7 | blame | 3 | $0.0292 | 0 | N | N | submit_findings | 10.9 | run_654 |
| ansible#15 | blame | 5 | $0.0395 | 0 | N | N | submit_findings | 17.7 | run_656 |
| pandas#108 | blame | 5 | $0.0869 | 0 | N | N | submit_findings | 24.8 | run_662 |
| pandas#121 | blame | 9 | $0.1214 | 1 | Y | N | submit_findings | 42.7 | run_666 |
| thefuck#12 | blame | 6 | $0.0597 | 0 | N | N | submit_findings | 17.2 | run_674 |
| thefuck#20 | blame | 4 | $0.0461 | 2 | Y | Y | submit_findings | 19.4 | run_679 |
| thefuck#21 | blame | 5 | $0.0655 | 2 | Y | Y | submit_findings | 17.5 | run_682 |
| thefuck#26 | blame | 3 | $0.0352 | 1 | Y | Y | submit_findings | 12.8 | run_685 |
| thefuck#28 | blame | 4 | $0.0627 | 1 | Y | N | submit_findings | 20.9 | run_688 |

**Summary:** 10 entries, total cost $0.6791, total turns 48, file-hit 6/10, line-hit 4/10.
