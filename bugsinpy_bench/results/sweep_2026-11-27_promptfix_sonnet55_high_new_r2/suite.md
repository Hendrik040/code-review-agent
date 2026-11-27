# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_promptfix_sonnet55_high_new_r2

Model: `claude-sonnet-5-5`.  Line tolerance: ±10.  N: 10 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| pandas#26 | blame | 5 | $0.0624 | 1 | Y | Y | submit_findings | 35.2 | run_708 |
| thefuck#7 | blame | 3 | $0.0302 | 0 | N | N | submit_findings | 11.1 | run_714 |
| ansible#15 | blame | 4 | $0.0397 | 0 | N | N | submit_findings | 25.9 | run_719 |
| pandas#108 | blame | 5 | $0.0945 | 0 | N | N | submit_findings | 26.7 | run_724 |
| pandas#121 | blame | 6 | $0.1174 | 1 | Y | N | submit_findings | 43.3 | run_730 |
| thefuck#12 | blame | 4 | $0.0496 | 0 | N | N | submit_findings | 13.7 | run_737 |
| thefuck#20 | blame | 5 | $0.0456 | 1 | Y | Y | submit_findings | 16.2 | run_741 |
| thefuck#21 | blame | 5 | $0.0651 | 1 | Y | Y | submit_findings | 17.6 | run_742 |
| thefuck#26 | blame | 3 | $0.0331 | 1 | Y | Y | submit_findings | 12.1 | run_745 |
| thefuck#28 | blame | 5 | $0.0631 | 1 | Y | Y | submit_findings | 16.9 | run_750 |

**Summary:** 10 entries, total cost $0.6009, total turns 45, file-hit 6/10, line-hit 5/10.
