# BugsInPy bench — agent_sdk @ medium — sweep_2026-11-26_haiku55_medium_pilot30

Model: `claude-haiku-5-5`.  Line tolerance: ±10.  N: 30 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| PySnooper#3 | blame | 6 | $0.0104 | 2 | Y | Y | submit_findings | 17.2 | run_419 |
| ansible#3 | blame | 7 | $0.0050 | 0 | N | N | submit_findings | 25.8 | run_420 |
| black#1 | blame | 3 | $0.0025 | 1 | Y | N | submit_findings | 10.0 | run_421 |
| cookiecutter#4 | blame | 5 | $0.0041 | 1 | Y | Y | submit_findings | 16.6 | run_422 |
| fastapi#8 | blame | 5 | $0.0030 | 0 | N | N | submit_findings | 9.6 | run_423 |
| keras#3 | blame | 4 | $0.0076 | 2 | Y | N | submit_findings | 38.5 | run_424 |
| keras#4 | blame | 7 | $0.0049 | 2 | Y | N | submit_findings | 16.6 | run_425 |
| keras#13 | blame | 3 | $0.0025 | 1 | Y | Y | submit_findings | 9.4 | run_426 |
| keras#32 | blame | 5 | $0.0055 | 1 | Y | N | submit_findings | 20.6 | run_427 |
| luigi#2 | blame | 5 | $0.0030 | 1 | Y | N | submit_findings | 12.2 | run_428 |
| luigi#4 | blame | 5 | $0.0025 | 0 | N | N | submit_findings | 9.2 | run_429 |
| luigi#5 | blame | 12 | $0.0083 | 1 | Y | N | submit_findings | 25.1 | run_430 |
| matplotlib#6 | blame | 3 | $0.0036 | 0 | N | N | submit_findings | 27.9 | run_431 |
| matplotlib#23 | blame | 4 | $0.0051 | 1 | Y | Y | submit_findings | 30.8 | run_432 |
| matplotlib#25 | blame | 3 | $0.0040 | 3 | Y | N | submit_findings | 30.3 | run_433 |
| pandas#6 | blame | 4 | $0.0044 | 0 | N | N | submit_findings | 25.3 | run_434 |
| pandas#26 | blame | 7 | $0.0049 | 1 | Y | Y | submit_findings | 23.2 | run_435 |
| pandas#30 | blame | 8 | $0.0049 | 1 | Y | N | submit_findings | 27.6 | run_436 |
| pandas#104 | blame | 4 | $0.0042 | 1 | Y | Y | submit_findings | 19.9 | run_437 |
| sanic#1 | blame | 6 | $0.0075 | 1 | Y | N | submit_findings | 25.0 | run_438 |
| scrapy#2 | blame | 5 | $0.0053 | 1 | Y | N | submit_findings | 20.8 | run_439 |
| scrapy#4 | blame | 5 | $0.0054 | 1 | Y | N | submit_findings | 18.5 | run_440 |
| scrapy#37 | blame | 7 | $0.0040 | 1 | Y | Y | submit_findings | 14.7 | run_441 |
| thefuck#1 | blame | 3 | $0.0028 | 1 | Y | Y | submit_findings | 14.3 | run_442 |
| thefuck#7 | blame | 6 | $0.0039 | 0 | N | N | submit_findings | 13.5 | run_443 |
| thefuck#9 | blame | 3 | $0.0042 | 3 | Y | Y | submit_findings | 22.6 | run_444 |
| tornado#4 | blame | 5 | $0.0045 | 0 | N | N | submit_findings | 20.4 | run_445 |
| tornado#13 | blame | 4 | $0.0043 | 1 | Y | N | submit_findings | 15.1 | run_446 |
| tqdm#2 | blame | 5 | $0.0047 | 0 | N | N | submit_findings | 21.3 | run_447 |
| tqdm#4 | blame | 5 | $0.0034 | 1 | Y | N | submit_findings | 12.5 | run_448 |

**Summary:** 30 entries, total cost $0.1404, total turns 154, file-hit 22/30, line-hit 9/30.
