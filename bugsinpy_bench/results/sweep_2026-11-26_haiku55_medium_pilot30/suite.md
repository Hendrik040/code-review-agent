# BugsInPy bench — agent_sdk @ medium — sweep_2026-11-26_haiku55_medium_pilot30

Model: `claude-haiku-5-5`.  Line tolerance: ±10.  N: 30 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| PySnooper#3 | blame | 6 | $0.0052 | 2 | Y | Y | submit_findings | 20.5 | run_417 |
| ansible#3 | blame | 4 | $0.0040 | 0 | N | N | submit_findings | 24.9 | run_418 |
| black#1 | blame | 4 | $0.0033 | 1 | Y | N | submit_findings | 10.2 | run_419 |
| cookiecutter#4 | blame | 4 | $0.0037 | 1 | Y | Y | submit_findings | 11.4 | run_420 |
| fastapi#8 | blame | 7 | $0.0038 | 0 | N | N | submit_findings | 11.2 | run_421 |
| keras#3 | blame | 7 | $0.0101 | 3 | Y | N | submit_findings | 40.1 | run_422 |
| keras#4 | blame | 9 | $0.0070 | 1 | Y | N | submit_findings | 21.9 | run_423 |
| keras#13 | blame | 5 | $0.0037 | 1 | Y | Y | submit_findings | 12.0 | run_424 |
| keras#32 | blame | 6 | $0.0082 | 3 | Y | N | submit_findings | 29.1 | run_425 |
| luigi#2 | blame | 5 | $0.0037 | 1 | Y | N | submit_findings | 10.9 | run_426 |
| luigi#4 | blame | 5 | $0.0031 | 0 | N | N | submit_findings | 9.6 | run_427 |
| luigi#5 | blame | 7 | $0.0104 | 3 | Y | N | submit_findings | 37.6 | run_428 |
| matplotlib#6 | blame | 11 | $0.0107 | 0 | N | N | submit_findings | 52.5 | run_429 |
| matplotlib#23 | blame | 5 | $0.0064 | 1 | Y | Y | submit_findings | 27.0 | run_430 |
| matplotlib#25 | blame | 4 | $0.0053 | 3 | Y | N | submit_findings | 25.4 | run_431 |
| pandas#6 | blame | 7 | $0.0069 | 0 | N | N | submit_findings | 35.2 | run_432 |
| pandas#26 | blame | 7 | $0.0053 | 1 | Y | Y | submit_findings | 28.2 | run_433 |
| pandas#30 | blame | 8 | $0.0059 | 0 | N | N | submit_findings | 27.2 | run_434 |
| pandas#104 | blame | 6 | $0.0056 | 1 | Y | Y | submit_findings | 26.9 | run_435 |
| sanic#1 | blame | 10 | $0.0117 | 3 | Y | N | submit_findings | 48.3 | run_436 |
| scrapy#2 | blame | 5 | $0.0062 | 1 | Y | N | submit_findings | 23.7 | run_437 |
| scrapy#4 | blame | 3 | $0.0055 | 1 | Y | N | submit_findings | 20.8 | run_438 |
| scrapy#37 | blame | 7 | $0.0047 | 1 | Y | Y | submit_findings | 14.2 | run_439 |
| thefuck#1 | blame | 3 | $0.0035 | 2 | Y | Y | submit_findings | 13.3 | run_440 |
| thefuck#7 | blame | 6 | $0.0046 | 0 | N | N | submit_findings | 16.4 | run_441 |
| thefuck#9 | blame | 5 | $0.0050 | 4 | Y | Y | submit_findings | 22.5 | run_442 |
| tornado#4 | blame | 5 | $0.0048 | 0 | N | N | submit_findings | 20.6 | run_443 |
| tornado#13 | blame | 3 | $0.0041 | 1 | Y | N | submit_findings | 14.4 | run_444 |
| tqdm#2 | blame | 5 | $0.0059 | 1 | Y | Y | submit_findings | 25.3 | run_445 |
| tqdm#4 | blame | 4 | $0.0037 | 1 | Y | N | submit_findings | 10.8 | run_446 |

**Summary:** 30 entries, total cost $0.1722, total turns 173, file-hit 22/30, line-hit 10/30.
