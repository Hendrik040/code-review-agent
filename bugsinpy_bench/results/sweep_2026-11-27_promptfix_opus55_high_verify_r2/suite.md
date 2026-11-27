# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_promptfix_opus55_high_verify_r2

Model: `claude-opus-5-5`.  Line tolerance: ±10.  N: 10 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| pandas#26 | blame | 8 | $0.2158 | 2 | Y | Y | submit_findings | 55.5 | run_712 |
| thefuck#7 | blame | 3 | $0.1133 | 2 | Y | Y | submit_findings | 27.2 | run_721 |
| ansible#15 | blame | 4 | $0.1107 | 0 | N | N | submit_findings | 26.0 | run_727 |
| pandas#108 | blame | 7 | $0.2322 | 0 | N | N | submit_findings | 36.8 | run_732 |
| pandas#121 | blame | 8 | $0.2935 | 2 | Y | N | submit_findings | 61.6 | run_738 |
| thefuck#12 | blame | 6 | $0.1651 | 0 | N | N | submit_findings | 26.4 | run_751 |
| thefuck#20 | blame | 5 | $0.1548 | 3 | Y | Y | submit_findings | 36.3 | run_756 |
| thefuck#21 | blame | 5 | $0.1751 | 2 | Y | N | submit_findings | 34.9 | run_760 |
| thefuck#26 | blame | 4 | $0.1111 | 2 | Y | Y | submit_findings | 21.4 | run_762 |
| thefuck#28 | blame | 5 | $0.1665 | 3 | Y | Y | submit_findings | 34.1 | run_766 |

**Summary:** 10 entries, total cost $1.7380, total turns 55, file-hit 7/10, line-hit 5/10.
