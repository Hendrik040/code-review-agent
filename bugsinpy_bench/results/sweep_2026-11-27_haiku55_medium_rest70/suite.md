# BugsInPy bench — agent_sdk @ medium — sweep_2026-11-27_haiku55_medium_rest70

Model: `claude-haiku-5-5`.  Line tolerance: ±10.  N: 70 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| ansible#15 | blame | 6 | $0.0079 | 0 | N | N | submit_findings | 96.5 | run_483 |
| black#5 | blame | 4 | $0.0067 | 0 | N | N | submit_findings | 12.4 | run_485 |
| black#11 | blame | 5 | $0.0071 | 0 | N | N | submit_findings | 26.8 | run_488 |
| black#12 | blame | 3 | $0.0048 | 0 | N | N | submit_findings | 28.5 | run_495 |
| black#13 | blame | 10 | $0.0160 | 0 | N | N | submit_findings | 84.3 | run_497 |
| black#16 | blame | 6 | $0.0033 | 0 | N | N | submit_findings | 14.5 | run_508 |
| cookiecutter#1 | blame | 4 | $0.0021 | 0 | N | N | submit_findings | 5.9 | run_510 |
| fastapi#12 | blame | 3 | $0.0031 | 0 | N | N | submit_findings | 9.2 | run_512 |
| httpie#2 | blame | 5 | $0.0038 | 0 | N | N | submit_findings | 9.0 | run_514 |
| keras#7 | blame | 5 | $0.0043 | 1 | Y | N | submit_findings | 12.0 | run_517 |
| keras#15 | blame | 4 | $0.0023 | 0 | N | N | submit_findings | 10.6 | run_519 |
| keras#17 | blame | 7 | $0.0040 | 0 | N | N | submit_findings | 10.3 | run_521 |
| keras#24 | blame | 4 | $0.0027 | 0 | N | N | submit_findings | 8.5 | run_523 |
| keras#26 | blame | 4 | $0.0042 | 0 | N | N | submit_findings | 14.7 | run_526 |
| keras#28 | blame | 3 | $0.0043 | 1 | Y | N | submit_findings | 17.7 | run_528 |
| keras#34 | blame | 5 | $0.0045 | 1 | Y | N | submit_findings | 17.3 | run_531 |
| keras#35 | blame | 5 | $0.0046 | 2 | Y | N | submit_findings | 21.2 | run_536 |
| luigi#10 | blame | 7 | $0.0059 | 1 | Y | N | submit_findings | 25.5 | run_541 |
| luigi#16 | blame | 6 | $0.0039 | 0 | N | N | submit_findings | 13.6 | run_545 |
| luigi#18 | blame | 9 | $0.0099 | 2 | Y | N | submit_findings | 40.5 | run_547 |
| luigi#19 | blame | 8 | $0.0088 | 2 | Y | N | submit_findings | 37.8 | run_549 |
| luigi#26 | blame | 3 | $0.0025 | 1 | Y | Y | submit_findings | 11.0 | run_556 |
| luigi#33 | blame | 5 | $0.0035 | 1 | Y | Y | submit_findings | 14.0 | run_559 |
| matplotlib#10 | blame | 3 | $0.0019 | 0 | N | N | submit_findings | 67.5 | run_563 |
| matplotlib#14 | blame | 5 | $0.0034 | 1 | Y | N | submit_findings | 45.8 | run_568 |
| matplotlib#21 | blame | 6 | $0.0058 | 1 | Y | Y | submit_findings | 55.0 | run_573 |
| matplotlib#29 | blame | 8 | $0.0064 | 1 | N | N | submit_findings | 84.8 | run_578 |
| pandas#21 | blame | 8 | $0.0091 | 0 | N | N | submit_findings | 48.6 | run_583 |
| pandas#22 | blame | 9 | $0.0062 | 0 | N | N | submit_findings | 36.9 | run_588 |
| pandas#27 | blame | 12 | $0.0132 | 0 | N | N | submit_findings | 55.3 | run_592 |
| pandas#35 | blame | 6 | $0.0049 | 0 | N | N | submit_findings | 25.2 | run_597 |
| pandas#42 | blame | 9 | $0.0060 | 0 | N | N | submit_findings | 33.9 | run_601 |
| pandas#48 | blame | 4 | $0.0048 | 0 | N | N | submit_findings | 22.4 | run_604 |
| pandas#50 | blame | 4 | $0.0040 | 1 | Y | Y | submit_findings | 27.1 | run_609 |
| pandas#61 | blame | 4 | $0.0029 | 0 | N | N | submit_findings | 23.9 | run_612 |
| pandas#69 | blame | 5 | $0.0046 | 0 | N | N | submit_findings | 43.5 | run_614 |
| pandas#95 | blame | 9 | $0.0090 | 2 | Y | Y | submit_findings | 41.9 | run_619 |
| pandas#106 | blame | 9 | $0.0072 | 1 | Y | N | submit_findings | 33.6 | run_623 |
| pandas#108 | blame | 13 | $0.0124 | 0 | N | N | submit_findings | 46.9 | run_628 |
| pandas#121 | blame | 12 | $0.0109 | 2 | Y | N | submit_findings | 45.3 | run_632 |
| pandas#132 | blame | 5 | $0.0081 | 1 | Y | N | submit_findings | 38.1 | run_638 |
| pandas#141 | blame | 5 | $0.0054 | 1 | Y | N | submit_findings | 23.6 | run_643 |
| pandas#147 | blame | 5 | $0.0028 | 0 | N | N | submit_findings | 14.5 | run_646 |
| pandas#149 | blame | 3 | $0.0050 | 1 | Y | N | submit_findings | 20.5 | run_647 |
| scrapy#10 | blame | 3 | $0.0021 | 0 | N | N | submit_findings | 7.7 | run_648 |
| scrapy#13 | blame | 5 | $0.0041 | 1 | Y | Y | submit_findings | 12.3 | run_650 |
| scrapy#14 | blame | 5 | $0.0029 | 0 | N | N | submit_findings | 9.3 | run_653 |
| scrapy#15 | blame | 6 | $0.0103 | 1 | Y | Y | submit_findings | 43.4 | run_655 |
| scrapy#24 | blame | 5 | $0.0030 | 0 | N | N | submit_findings | 17.5 | run_658 |
| scrapy#25 | blame | 3 | $0.0026 | 0 | N | N | submit_findings | 25.6 | run_660 |
| scrapy#27 | blame | 3 | $0.0028 | 1 | N | N | submit_findings | 10.4 | run_662 |
| scrapy#31 | blame | 5 | $0.0068 | 1 | Y | Y | submit_findings | 34.4 | run_664 |
| scrapy#36 | blame | 4 | $0.0040 | 0 | N | N | submit_findings | 11.9 | run_667 |
| scrapy#40 | blame | 3 | $0.0052 | 1 | Y | Y | submit_findings | 17.0 | run_669 |
| spacy#5 | blame | 6 | $0.0036 | 0 | N | N | submit_findings | 54.6 | run_673 |
| thefuck#8 | blame | 3 | $0.0016 | 0 | N | N | submit_findings | 4.8 | run_676 |
| thefuck#12 | blame | 9 | $0.0074 | 1 | Y | N | submit_findings | 23.7 | run_677 |
| thefuck#15 | blame | 4 | $0.0031 | 1 | Y | Y | submit_findings | 12.0 | run_680 |
| thefuck#20 | blame | 8 | $0.0072 | 2 | Y | Y | submit_findings | 32.7 | run_681 |
| thefuck#21 | blame | 6 | $0.0051 | 1 | Y | N | submit_findings | 20.0 | run_683 |
| thefuck#23 | blame | 3 | $0.0060 | 2 | Y | Y | submit_findings | 32.3 | run_685 |
| thefuck#25 | blame | 6 | $0.0060 | 1 | Y | Y | submit_findings | 13.9 | run_687 |
| thefuck#26 | blame | 5 | $0.0036 | 1 | Y | Y | submit_findings | 13.0 | run_688 |
| thefuck#28 | blame | 7 | $0.0051 | 1 | Y | Y | submit_findings | 18.4 | run_690 |
| thefuck#32 | blame | 4 | $0.0042 | 0 | N | N | submit_findings | 7.0 | run_692 |
| tornado#5 | blame | 3 | $0.0023 | 0 | N | N | submit_findings | 10.9 | run_693 |
| tornado#11 | blame | 10 | $0.0096 | 2 | Y | N | submit_findings | 41.5 | run_695 |
| tornado#12 | blame | 5 | $0.0049 | 1 | Y | N | submit_findings | 17.7 | run_697 |
| tqdm#6 | blame | 5 | $0.0036 | 0 | N | N | submit_findings | 10.0 | run_699 |
| tqdm#7 | blame | 5 | $0.0050 | 1 | Y | N | submit_findings | 17.8 | run_700 |

**Summary:** 70 entries, total cost $0.3761, total turns 396, file-hit 33/70, line-hit 15/70.
