# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_promptfix_opus55_high_new_r1

Model: `claude-opus-5-5`.  Line tolerance: ±10.  N: 10 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| pandas#26 | blame | 7 | $0.3338 | 1 | Y | Y | submit_findings | 46.5 | run_652 |
| thefuck#7 | blame | 3 | $0.0944 | 0 | N | N | submit_findings | 14.8 | run_659 |
| ansible#15 | blame | 4 | $0.0971 | 0 | N | N | submit_findings | 21.6 | run_663 |
| pandas#108 | blame | 6 | $0.2015 | 0 | N | N | submit_findings | 44.8 | run_671 |
| pandas#121 | blame | 6 | $0.2759 | 3 | Y | N | submit_findings | 61.9 | run_676 |
| thefuck#12 | blame | 4 | $0.1319 | 0 | N | N | submit_findings | 20.6 | run_687 |
| thefuck#20 | blame | 5 | $0.1494 | 3 | Y | Y | submit_findings | 35.9 | run_693 |
| thefuck#21 | blame | 7 | $0.2119 | 1 | Y | N | submit_findings | 40.0 | run_698 |
| thefuck#26 | blame | 5 | $0.1243 | 2 | Y | Y | submit_findings | 24.5 | run_702 |
| thefuck#28 | blame | 4 | $0.1425 | 2 | Y | Y | submit_findings | 30.4 | run_704 |

**Summary:** 10 entries, total cost $1.7628, total turns 51, file-hit 6/10, line-hit 4/10.
