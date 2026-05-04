# BugsInPy bench — agent SDK xhigh — suite 001

Line tolerance: ±10.  N: 5 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| pandas#82 | synthetic_revert | 14 | $0.9448 | 1 | Y | Y | submit_findings | 131.4 | run_043 |
| pandas#39 | synthetic_revert | 28 | $1.0990 | 1 | Y | Y | submit_findings | 212.7 | run_044 |
| pandas#6 | blame | 10 | $0.6254 | 0 | N | N | submit_findings | 155.8 | run_045 |
| pandas#134 | blame | 3 | $0.1422 | 0 | N | N | submit_findings | 27.9 | run_046 |
| pandas#65 | blame | 61 | $4.4261 | 1 | Y | N | submit_findings | 692.7 | run_047 |

**Summary:** 5 entries, total cost $7.2375, total turns 116, file-hit 3/5, line-hit 2/5.
