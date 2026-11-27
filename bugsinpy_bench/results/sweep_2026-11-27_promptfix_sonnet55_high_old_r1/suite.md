# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_promptfix_sonnet55_high_old_r1

Model: `claude-sonnet-5-5`.  Line tolerance: ±10.  N: 10 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| pandas#26 | blame | 7 | $0.1376 | 1 | Y | Y | submit_findings | 32.7 | run_649 |
| thefuck#7 | blame | 6 | $0.0438 | 1 | Y | Y | submit_findings | 18.7 | run_655 |
| ansible#15 | blame | 9 | $0.0963 | 0 | N | N | submit_findings | 32.3 | run_661 |
| pandas#108 | blame | 9 | $0.0966 | 0 | N | N | submit_findings | 33.5 | run_668 |
| pandas#121 | blame | 8 | $0.0792 | 1 | Y | N | submit_findings | 29.4 | run_673 |
| thefuck#12 | blame | 6 | $0.0431 | 0 | N | N | submit_findings | 16.7 | run_680 |
| thefuck#20 | blame | 5 | $0.0468 | 3 | Y | Y | submit_findings | 17.7 | run_683 |
| thefuck#21 | blame | 7 | $0.0632 | 1 | Y | Y | submit_findings | 21.5 | run_686 |
| thefuck#26 | blame | 5 | $0.0422 | 1 | Y | Y | submit_findings | 17.4 | run_690 |
| thefuck#28 | blame | 6 | $0.0546 | 2 | Y | Y | submit_findings | 18.6 | run_694 |

**Summary:** 10 entries, total cost $0.7033, total turns 68, file-hit 7/10, line-hit 6/10.
