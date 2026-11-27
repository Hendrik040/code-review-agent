# BugsInPy bench — agent_sdk @ high — sweep_2026-11-26_sonnet55_high_pilot30

Model: `claude-sonnet-5-5`.  Line tolerance: ±10.  N: 30 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| PySnooper#3 | blame | 4 | $0.0328 | 2 | Y | Y | submit_findings | 11.0 | run_389 |
| ansible#3 | blame | 5 | $0.0502 | 0 | N | N | submit_findings | 25.7 | run_390 |
| black#1 | blame | 3 | $0.0284 | 1 | Y | N | submit_findings | 9.7 | run_391 |
| cookiecutter#4 | blame | 4 | $0.0414 | 1 | Y | Y | submit_findings | 14.2 | run_392 |
| fastapi#8 | blame | 6 | $0.0506 | 1 | Y | N | submit_findings | 31.3 | run_393 |
| keras#3 | blame | 3 | $0.0645 | 2 | Y | N | submit_findings | 19.0 | run_394 |
| keras#4 | blame | 5 | $0.0517 | 1 | Y | N | submit_findings | 15.5 | run_395 |
| keras#13 | blame | 4 | $0.0378 | 1 | Y | Y | submit_findings | 10.3 | run_396 |
| keras#32 | blame | 5 | $0.0673 | 1 | Y | N | submit_findings | 18.5 | run_397 |
| luigi#2 | blame | 4 | $0.0343 | 1 | Y | N | submit_findings | 11.6 | run_398 |
| luigi#4 | blame | 6 | $0.0418 | 1 | Y | N | submit_findings | 12.6 | run_399 |
| luigi#5 | blame | 7 | $0.0822 | 1 | Y | N | submit_findings | 19.4 | run_400 |
| matplotlib#6 | blame | 3 | $0.0342 | 0 | N | N | submit_findings | 25.7 | run_401 |
| matplotlib#23 | blame | 4 | $0.0589 | 0 | N | N | submit_findings | 38.7 | run_402 |
| matplotlib#25 | blame | 7 | $0.0672 | 2 | Y | N | submit_findings | 34.9 | run_403 |
| pandas#6 | blame | 3 | $0.0353 | 0 | N | N | submit_findings | 17.2 | run_404 |
| pandas#26 | blame | 6 | $0.0503 | 1 | Y | Y | submit_findings | 25.5 | run_405 |
| pandas#30 | blame | 4 | $0.0350 | 1 | Y | N | submit_findings | 17.8 | run_406 |
| pandas#104 | blame | 4 | $0.0505 | 1 | Y | Y | submit_findings | 18.6 | run_407 |
| sanic#1 | blame | 6 | $0.1179 | 3 | Y | N | submit_findings | 27.9 | run_408 |
| scrapy#2 | blame | 4 | $0.0569 | 1 | Y | N | submit_findings | 15.2 | run_409 |
| scrapy#4 | blame | 4 | $0.0625 | 1 | Y | N | submit_findings | 15.5 | run_410 |
| scrapy#37 | blame | 4 | $0.0433 | 1 | Y | Y | submit_findings | 15.0 | run_411 |
| thefuck#1 | blame | 3 | $0.0304 | 1 | Y | Y | submit_findings | 13.3 | run_412 |
| thefuck#7 | blame | 6 | $0.0502 | 1 | Y | Y | submit_findings | 16.4 | run_413 |
| thefuck#9 | blame | 3 | $0.0400 | 2 | Y | Y | submit_findings | 17.1 | run_414 |
| tornado#4 | blame | 5 | $0.0462 | 0 | N | N | submit_findings | 16.1 | run_415 |
| tornado#13 | blame | 7 | $0.0624 | 0 | N | N | submit_findings | 31.3 | run_416 |
| tqdm#2 | blame | 5 | $0.0437 | 1 | Y | Y | submit_findings | 28.8 | run_417 |
| tqdm#4 | blame | 4 | $0.0399 | 1 | Y | N | submit_findings | 10.2 | run_418 |

**Summary:** 30 entries, total cost $1.5077, total turns 138, file-hit 24/30, line-hit 10/30.
