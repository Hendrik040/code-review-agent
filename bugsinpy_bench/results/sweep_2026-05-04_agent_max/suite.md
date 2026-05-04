# BugsInPy bench — agent_sdk @ max — sweep_2026-05-04_agent_max

Model: `claude-opus-4-7`.  Line tolerance: ±10.  N: 100 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| PySnooper#3 | blame | 16 | $1.2236 | 2 | Y | Y | submit_findings | 205.2 | run_236 |
| ansible#3 | blame | 17 | $1.2297 | 0 | N | N | submit_findings | 248.1 | run_238 |
| ansible#15 | blame | 14 | $0.7488 | 0 | N | N | submit_findings | 138.3 | run_241 |
| black#1 | blame | 5 | $0.2435 | 1 | Y | N | submit_findings | 43.5 | run_244 |
| black#5 | blame | 12 | $0.5964 | 0 | N | N | submit_findings | 143.7 | run_245 |
| black#11 | blame | 20 | $1.8230 | 0 | N | N | submit_findings | 493.8 | run_247 |
| black#12 | blame | 10 | $0.8250 | 0 | N | N | submit_findings | 174.0 | run_256 |
| black#13 | blame | 43 | $4.5466 | 0 | N | N | submit_findings | 1121.2 | run_260 |
| black#16 | blame | 14 | $0.7179 | 0 | N | N | submit_findings | 126.6 | run_281 |
| cookiecutter#1 | blame | 5 | $0.2835 | 0 | N | N | submit_findings | 58.1 | run_283 |
| cookiecutter#4 | blame | 14 | $0.5885 | 1 | Y | Y | submit_findings | 110.3 | run_285 |
| fastapi#8 | blame | 12 | $0.4596 | 0 | N | N | submit_findings | 64.4 | run_286 |
| fastapi#12 | blame | 5 | $0.3994 | 0 | N | N | submit_findings | 70.7 | run_287 |
| httpie#2 | blame | 9 | $0.4817 | 0 | N | N | submit_findings | 94.9 | run_289 |
| keras#3 | blame | 28 | $3.0617 | 6 | Y | N | submit_findings | 769.5 | run_291 |
| keras#4 | blame | 13 | $0.6894 | 2 | Y | N | submit_findings | 169.7 | run_296 |
| keras#7 | blame | 8 | $0.6562 | 0 | N | N | submit_findings | 141.1 | run_297 |
| keras#13 | blame | 5 | $0.3040 | 1 | Y | Y | submit_findings | 53.0 | run_299 |
| keras#15 | blame | 7 | $0.4256 | 0 | N | N | submit_findings | 87.7 | run_300 |
| keras#17 | blame | 9 | $0.4000 | 0 | N | N | submit_findings | 69.3 | run_302 |
| keras#24 | blame | 10 | $0.3870 | 0 | N | N | submit_findings | 71.0 | run_304 |
| keras#26 | blame | 10 | $0.5328 | 1 | Y | N | submit_findings | 126.3 | run_305 |
| keras#28 | blame | 7 | $0.8294 | 2 | Y | N | submit_findings | 213.0 | run_306 |
