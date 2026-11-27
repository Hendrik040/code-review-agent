# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_sonnet55_high_rest70

Model: `claude-sonnet-5-5`.  Line tolerance: ±10.  N: 70 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| ansible#15 | blame | 8 | $0.1432 | 0 | N | N | submit_findings | 99.3 | run_482 |
| black#5 | blame | 3 | $0.0329 | 0 | N | N | submit_findings | 11.4 | run_487 |
| black#11 | blame | 4 | $0.1612 | 0 | N | N | submit_findings | 21.5 | run_489 |
| black#12 | blame | 4 | $0.0461 | 0 | N | N | submit_findings | 11.1 | run_494 |
| black#13 | blame | 5 | $0.0690 | 0 | N | N | submit_findings | 18.9 | run_496 |
| black#16 | blame | 7 | $0.0402 | 0 | N | N | submit_findings | 14.7 | run_498 |
| cookiecutter#1 | blame | 3 | $0.0238 | 0 | N | N | submit_findings | 11.0 | run_500 |
| fastapi#12 | blame | 4 | $0.0537 | 0 | N | N | submit_findings | 17.0 | run_501 |
| httpie#2 | blame | 5 | $0.0570 | 0 | N | N | submit_findings | 13.9 | run_502 |
| keras#7 | blame | 4 | $0.0539 | 0 | N | N | submit_findings | 10.1 | run_503 |
| keras#15 | blame | 3 | $0.0218 | 0 | N | N | submit_findings | 7.8 | run_504 |
| keras#17 | blame | 3 | $0.0235 | 0 | N | N | submit_findings | 8.5 | run_506 |
| keras#24 | blame | 3 | $0.0238 | 0 | N | N | submit_findings | 8.6 | run_507 |
| keras#26 | blame | 3 | $0.0488 | 1 | Y | N | submit_findings | 16.0 | run_509 |
| keras#28 | blame | 3 | $0.0561 | 2 | Y | N | submit_findings | 20.5 | run_513 |
| keras#34 | blame | 5 | $0.0604 | 1 | Y | N | submit_findings | 16.1 | run_518 |
| keras#35 | blame | 8 | $0.0653 | 2 | Y | N | submit_findings | 20.7 | run_520 |
| luigi#10 | blame | 4 | $0.0466 | 0 | N | N | submit_findings | 15.3 | run_525 |
| luigi#16 | blame | 4 | $0.0376 | 0 | N | N | submit_findings | 14.4 | run_529 |
| luigi#18 | blame | 4 | $0.0753 | 1 | Y | N | submit_findings | 21.7 | run_530 |
| luigi#19 | blame | 4 | $0.0482 | 1 | Y | N | submit_findings | 25.4 | run_537 |
| luigi#26 | blame | 4 | $0.0497 | 2 | Y | N | submit_findings | 17.4 | run_542 |
| luigi#33 | blame | 7 | $0.0551 | 0 | N | N | submit_findings | 14.4 | run_544 |
| matplotlib#10 | blame | 4 | $0.0322 | 0 | N | N | submit_findings | 57.6 | run_551 |
| matplotlib#14 | blame | 4 | $0.0276 | 0 | N | N | submit_findings | 43.1 | run_557 |
| matplotlib#21 | blame | 5 | $0.0602 | 1 | Y | Y | submit_findings | 58.3 | run_562 |
| matplotlib#29 | blame | 4 | $0.0488 | 1 | N | N | submit_findings | 65.7 | run_569 |
| pandas#21 | blame | 7 | $0.0888 | 0 | N | N | submit_findings | 33.9 | run_571 |
| pandas#22 | blame | 6 | $0.0702 | 0 | N | N | submit_findings | 24.1 | run_574 |
| pandas#27 | blame | 14 | $0.1697 | 1 | N | N | submit_findings | 60.7 | run_575 |
| pandas#35 | blame | 4 | $0.0478 | 0 | N | N | submit_findings | 31.4 | run_581 |
| pandas#42 | blame | 8 | $0.1015 | 1 | Y | Y | submit_findings | 35.3 | run_584 |
| pandas#48 | blame | 4 | $0.0574 | 0 | N | N | submit_findings | 21.6 | run_586 |
| pandas#50 | blame | 5 | $0.0546 | 1 | Y | Y | submit_findings | 27.4 | run_591 |
| pandas#61 | blame | 4 | $0.0342 | 0 | N | N | submit_findings | 34.7 | run_593 |
| pandas#69 | blame | 5 | $0.0536 | 0 | N | N | submit_findings | 20.4 | run_595 |
| pandas#95 | blame | 8 | $0.1137 | 1 | N | N | submit_findings | 40.2 | run_599 |
| pandas#106 | blame | 4 | $0.0467 | 0 | N | N | submit_findings | 20.3 | run_603 |
| pandas#108 | blame | 8 | $0.0865 | 0 | N | N | submit_findings | 28.5 | run_607 |
| pandas#121 | blame | 7 | $0.0831 | 2 | Y | N | submit_findings | 39.6 | run_610 |
| pandas#132 | blame | 5 | $0.0876 | 1 | Y | N | submit_findings | 28.0 | run_613 |
| pandas#141 | blame | 3 | $0.0579 | 1 | Y | N | submit_findings | 23.2 | run_616 |
| pandas#147 | blame | 4 | $0.0299 | 0 | N | N | submit_findings | 14.9 | run_621 |
| pandas#149 | blame | 4 | $0.0771 | 1 | Y | N | submit_findings | 22.3 | run_622 |
| scrapy#10 | blame | 3 | $0.0272 | 0 | N | N | submit_findings | 7.7 | run_625 |
| scrapy#13 | blame | 5 | $0.0682 | 1 | Y | Y | submit_findings | 18.6 | run_626 |
| scrapy#14 | blame | 6 | $0.0382 | 0 | N | N | submit_findings | 13.3 | run_629 |
| scrapy#15 | blame | 3 | $0.0738 | 1 | Y | Y | submit_findings | 28.5 | run_630 |
| scrapy#24 | blame | 4 | $0.0283 | 0 | N | N | submit_findings | 10.0 | run_633 |
| scrapy#25 | blame | 4 | $0.0323 | 0 | N | N | submit_findings | 8.2 | run_634 |
| scrapy#27 | blame | 3 | $0.0358 | 0 | N | N | submit_findings | 8.6 | run_636 |
| scrapy#31 | blame | 5 | $0.0915 | 1 | Y | Y | submit_findings | 21.5 | run_637 |
| scrapy#36 | blame | 6 | $0.0564 | 0 | N | N | submit_findings | 13.1 | run_639 |
| scrapy#40 | blame | 4 | $0.0726 | 1 | Y | Y | submit_findings | 14.7 | run_641 |
| spacy#5 | blame | 7 | $0.0450 | 0 | N | N | submit_findings | 65.4 | run_644 |
| thefuck#8 | blame | 3 | $0.0192 | 0 | N | N | submit_findings | 9.1 | run_649 |
| thefuck#12 | blame | 6 | $0.0455 | 0 | N | N | submit_findings | 15.0 | run_651 |
| thefuck#15 | blame | 5 | $0.0409 | 2 | Y | Y | submit_findings | 17.5 | run_654 |
| thefuck#20 | blame | 5 | $0.0515 | 3 | Y | Y | submit_findings | 19.8 | run_656 |
| thefuck#21 | blame | 6 | $0.0609 | 1 | Y | Y | submit_findings | 23.9 | run_657 |
| thefuck#23 | blame | 5 | $0.0706 | 2 | Y | Y | submit_findings | 39.9 | run_659 |
| thefuck#25 | blame | 3 | $0.0583 | 1 | Y | Y | submit_findings | 14.1 | run_663 |
| thefuck#26 | blame | 5 | $0.0450 | 2 | Y | Y | submit_findings | 26.3 | run_665 |
| thefuck#28 | blame | 6 | $0.0555 | 2 | Y | Y | submit_findings | 19.6 | run_668 |
| thefuck#32 | blame | 4 | $0.0604 | 0 | N | N | submit_findings | 7.0 | run_670 |
| tornado#5 | blame | 3 | $0.0257 | 0 | N | N | submit_findings | 7.5 | run_671 |
| tornado#11 | blame | 9 | $0.1095 | 2 | Y | N | submit_findings | 37.3 | run_672 |
| tornado#12 | blame | 5 | $0.0634 | 1 | Y | N | submit_findings | 14.7 | run_675 |
| tqdm#6 | blame | 4 | $0.0351 | 0 | N | N | submit_findings | 9.7 | run_678 |
| tqdm#7 | blame | 4 | $0.0560 | 1 | Y | N | submit_findings | 20.7 | run_679 |

**Summary:** 70 entries, total cost $4.0892, total turns 342, file-hit 28/70, line-hit 14/70.
