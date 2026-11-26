# BugsInPy bench — agent_sdk @ high — sweep_2026-11-26_sonnet55_high_pilot30

Model: `claude-sonnet-5-5`.  Line tolerance: ±10.  N: 30 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| PySnooper#3 | blame | 4 | $0.0343 | 2 | Y | Y | submit_findings | 11.9 | run_387 |
| ansible#3 | blame | 4 | $0.0404 | 0 | N | N | submit_findings | 20.9 | run_388 |
| black#1 | blame | 3 | $0.0307 | 1 | Y | N | submit_findings | 8.8 | run_389 |
| cookiecutter#4 | blame | 4 | $0.0430 | 1 | Y | Y | submit_findings | 11.4 | run_390 |
| fastapi#8 | blame | 5 | $0.0462 | 1 | Y | N | submit_findings | 12.8 | run_391 |
| keras#3 | blame | 3 | $0.0779 | 3 | Y | N | submit_findings | 25.4 | run_392 |
| keras#4 | blame | 6 | $0.0554 | 1 | Y | N | submit_findings | 16.7 | run_393 |
| keras#13 | blame | 5 | $0.0478 | 1 | Y | Y | submit_findings | 12.7 | run_394 |
| keras#32 | blame | 4 | $0.0694 | 2 | Y | N | submit_findings | 17.3 | run_395 |
| luigi#2 | blame | 4 | $0.0409 | 1 | Y | N | submit_findings | 10.6 | run_396 |
| luigi#4 | blame | 7 | $0.0485 | 1 | Y | N | submit_findings | 14.0 | run_397 |
| luigi#5 | blame | 12 | $0.1257 | 1 | Y | N | submit_findings | 31.9 | run_398 |
| matplotlib#6 | blame | 3 | $0.0372 | 0 | N | N | submit_findings | 17.7 | run_399 |
| matplotlib#23 | blame | 4 | $0.0746 | 1 | Y | Y | submit_findings | 26.9 | run_400 |
| matplotlib#25 | blame | 6 | $0.0724 | 3 | Y | N | submit_findings | 24.8 | run_401 |
| pandas#6 | blame | 3 | $0.0376 | 0 | N | N | submit_findings | 20.4 | run_402 |
| pandas#26 | blame | 5 | $0.0597 | 1 | Y | Y | submit_findings | 25.1 | run_403 |
| pandas#30 | blame | 4 | $0.0374 | 1 | Y | N | submit_findings | 20.3 | run_404 |
| pandas#104 | blame | 4 | $0.0563 | 1 | Y | Y | submit_findings | 22.1 | run_405 |
| sanic#1 | blame | 8 | $0.1260 | 3 | Y | N | submit_findings | 32.3 | run_406 |
| scrapy#2 | blame | 4 | $0.0575 | 1 | Y | N | submit_findings | 13.1 | run_407 |
| scrapy#4 | blame | 4 | $0.0631 | 1 | Y | N | submit_findings | 13.8 | run_408 |
| scrapy#37 | blame | 4 | $0.0459 | 2 | Y | Y | submit_findings | 15.3 | run_409 |
| thefuck#1 | blame | 3 | $0.0354 | 1 | Y | Y | submit_findings | 13.3 | run_410 |
| thefuck#7 | blame | 6 | $0.0482 | 1 | Y | Y | submit_findings | 14.5 | run_411 |
| thefuck#9 | blame | 5 | $0.0447 | 2 | Y | Y | submit_findings | 14.9 | run_412 |
| tornado#4 | blame | 4 | $0.0448 | 0 | N | N | submit_findings | 13.0 | run_413 |
| tornado#13 | blame | 6 | $0.0696 | 1 | Y | N | submit_findings | 16.0 | run_414 |
| tqdm#2 | blame | 5 | $0.0593 | 1 | Y | Y | submit_findings | 18.6 | run_415 |
| tqdm#4 | blame | 4 | $0.0430 | 1 | Y | N | submit_findings | 10.9 | run_416 |

**Summary:** 30 entries, total cost $1.6728, total turns 143, file-hit 26/30, line-hit 11/30.
