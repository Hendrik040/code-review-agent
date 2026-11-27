# BugsInPy bench — agent_sdk @ medium — sweep_2026-11-27_impactsel_haiku55_medium_aff16

Model: `claude-haiku-5-5`.  Line tolerance: ±10.  N: 16 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| PySnooper#3 | blame | 4 | $0.0085 | 2 | Y | Y | submit_findings | 16.3 | run_565 |
| luigi#5 | blame | 7 | $0.0113 | 1 | Y | N | submit_findings | 25.4 | run_568 |
| pandas#26 | blame | 6 | $0.0047 | 2 | Y | Y | submit_findings | 28.4 | run_571 |
| thefuck#1 | blame | 3 | $0.0027 | 0 | N | N | submit_findings | 11.6 | run_574 |
| thefuck#7 | blame | 3 | $0.0022 | 0 | N | N | submit_findings | 7.7 | run_576 |
| ansible#15 | blame | 5 | $0.0069 | 0 | N | N | submit_findings | 18.7 | run_578 |
| pandas#108 | blame | 7 | $0.0064 | 1 | N | N | submit_findings | 22.4 | run_580 |
| pandas#121 | blame | 9 | $0.0079 | 1 | N | N | submit_findings | 28.7 | run_583 |
| thefuck#12 | blame | 6 | $0.0058 | 0 | N | N | submit_findings | 21.0 | run_586 |
| thefuck#15 | blame | 3 | $0.0032 | 1 | Y | Y | submit_findings | 15.4 | run_588 |
| thefuck#20 | blame | 6 | $0.0046 | 1 | Y | Y | submit_findings | 20.1 | run_591 |
| thefuck#21 | blame | 7 | $0.0071 | 3 | Y | Y | submit_findings | 26.5 | run_593 |
| thefuck#25 | blame | 3 | $0.0023 | 1 | Y | Y | submit_findings | 8.9 | run_596 |
| thefuck#26 | blame | 3 | $0.0028 | 1 | Y | Y | submit_findings | 10.6 | run_598 |
| thefuck#28 | blame | 3 | $0.0058 | 1 | Y | Y | submit_findings | 32.3 | run_600 |
| thefuck#32 | blame | 4 | $0.0024 | 0 | N | N | submit_findings | 6.4 | run_605 |

**Summary:** 16 entries, total cost $0.0848, total turns 79, file-hit 9/16, line-hit 8/16.
