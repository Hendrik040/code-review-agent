# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_promptfix_opus55_high_new_r2

Model: `claude-opus-5-5`.  Line tolerance: ±10.  N: 10 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| pandas#26 | blame | 7 | $0.1779 | 1 | Y | Y | submit_findings | 49.4 | run_711 |
| thefuck#7 | blame | 3 | $0.0845 | 0 | N | N | submit_findings | 14.4 | run_718 |
| ansible#15 | blame | 4 | $0.0977 | 0 | N | N | submit_findings | 22.5 | run_722 |
| pandas#108 | blame | 8 | $0.2588 | 0 | N | N | submit_findings | 39.0 | run_728 |
| pandas#121 | blame | 10 | $0.3299 | 2 | Y | N | submit_findings | 76.0 | run_735 |
| thefuck#12 | blame | 4 | $0.1344 | 0 | N | N | submit_findings | 22.2 | run_749 |
| thefuck#20 | blame | 6 | $0.1605 | 4 | Y | Y | submit_findings | 39.1 | run_755 |
| thefuck#21 | blame | 5 | $0.1748 | 2 | Y | Y | submit_findings | 42.9 | run_759 |
| thefuck#26 | blame | 4 | $0.0851 | 2 | Y | Y | submit_findings | 19.8 | run_763 |
| thefuck#28 | blame | 3 | $0.0937 | 1 | Y | N | submit_findings | 24.5 | run_765 |

**Summary:** 10 entries, total cost $1.5974, total turns 54, file-hit 6/10, line-hit 4/10.
