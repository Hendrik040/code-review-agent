# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_opus55_high_pilot30

Model: `claude-opus-5-5`.  Line tolerance: ±10.  N: 30 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| PySnooper#3 | blame | 4 | $0.0861 | 2 | Y | Y | submit_findings | 21.3 | run_452 |
| ansible#3 | blame | 4 | $0.1119 | 0 | N | N | submit_findings | 30.8 | run_453 |
| black#1 | blame | 3 | $0.0799 | 1 | Y | N | submit_findings | 12.6 | run_454 |
| cookiecutter#4 | blame | 5 | $0.1317 | 2 | Y | Y | submit_findings | 23.6 | run_455 |
| fastapi#8 | blame | 5 | $0.1112 | 1 | Y | N | submit_findings | 18.9 | run_456 |
| keras#3 | blame | 5 | $0.3256 | 2 | Y | N | submit_findings | 74.7 | run_457 |
| keras#4 | blame | 5 | $0.1495 | 2 | Y | N | submit_findings | 31.6 | run_458 |
| keras#13 | blame | 4 | $0.0967 | 1 | Y | Y | submit_findings | 15.6 | run_459 |
| keras#32 | blame | 5 | $0.1845 | 2 | Y | N | submit_findings | 31.4 | run_460 |
| luigi#2 | blame | 4 | $0.0903 | 1 | Y | N | submit_findings | 15.0 | run_461 |
| luigi#4 | blame | 6 | $0.1221 | 1 | Y | N | submit_findings | 24.2 | run_462 |
| luigi#5 | blame | 8 | $0.2000 | 3 | Y | N | submit_findings | 42.5 | run_463 |
| matplotlib#6 | blame | 6 | $0.1560 | 0 | N | N | submit_findings | 110.7 | run_464 |
| matplotlib#23 | blame | 4 | $0.1559 | 1 | Y | Y | submit_findings | 35.9 | run_465 |
| matplotlib#25 | blame | 5 | $0.1600 | 3 | Y | N | submit_findings | 40.1 | run_466 |
| pandas#6 | blame | 14 | $0.3725 | 1 | Y | N | submit_findings | 77.4 | run_467 |
| pandas#26 | blame | 8 | $0.1755 | 1 | Y | Y | submit_findings | 40.2 | run_468 |
| pandas#30 | blame | 13 | $0.2845 | 1 | Y | N | submit_findings | 59.5 | run_469 |
| pandas#104 | blame | 3 | $0.1154 | 1 | Y | Y | submit_findings | 24.8 | run_470 |
| sanic#1 | blame | 4 | $0.2443 | 3 | Y | N | submit_findings | 51.7 | run_471 |
| scrapy#2 | blame | 4 | $0.1390 | 1 | Y | N | submit_findings | 22.3 | run_472 |
| scrapy#4 | blame | 4 | $0.1547 | 1 | Y | N | submit_findings | 20.1 | run_473 |
| scrapy#37 | blame | 6 | $0.1397 | 2 | Y | Y | submit_findings | 30.1 | run_474 |
| thefuck#1 | blame | 3 | $0.1009 | 2 | Y | Y | submit_findings | 23.0 | run_475 |
| thefuck#7 | blame | 5 | $0.1167 | 1 | Y | Y | submit_findings | 23.3 | run_476 |
| thefuck#9 | blame | 4 | $0.1323 | 3 | Y | Y | submit_findings | 43.5 | run_477 |
| tornado#4 | blame | 6 | $0.1370 | 0 | N | N | submit_findings | 39.7 | run_478 |
| tornado#13 | blame | 5 | $0.1435 | 1 | Y | N | submit_findings | 23.9 | run_479 |
| tqdm#2 | blame | 9 | $0.2140 | 1 | Y | Y | submit_findings | 45.3 | run_480 |
| tqdm#4 | blame | 5 | $0.1382 | 2 | Y | N | submit_findings | 19.4 | run_481 |

**Summary:** 30 entries, total cost $4.7695, total turns 166, file-hit 27/30, line-hit 11/30.
