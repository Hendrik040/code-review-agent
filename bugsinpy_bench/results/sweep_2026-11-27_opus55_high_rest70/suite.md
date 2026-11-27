# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_opus55_high_rest70

Model: `claude-opus-5-5`.  Line tolerance: ±10.  N: 70 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| ansible#15 | blame | 5 | $0.2390 | 0 | N | N | submit_findings | 97.3 | run_484 |
| black#5 | blame | 3 | $0.0885 | 0 | N | N | submit_findings | 16.3 | run_486 |
| black#11 | blame | 9 | $0.3150 | 1 | Y | N | submit_findings | 61.4 | run_490 |
| black#12 | blame | 7 | $0.2524 | 1 | Y | N | submit_findings | 60.1 | run_499 |
| black#13 | blame | 8 | $0.3566 | 0 | N | N | submit_findings | 76.3 | run_505 |
| black#16 | blame | 5 | $0.0934 | 0 | N | N | submit_findings | 15.1 | run_522 |
| cookiecutter#1 | blame | 4 | $0.0787 | 0 | N | N | submit_findings | 12.1 | run_524 |
| fastapi#12 | blame | 4 | $0.1269 | 0 | N | N | submit_findings | 24.2 | run_527 |
| httpie#2 | blame | 4 | $0.1208 | 0 | N | N | submit_findings | 12.9 | run_532 |
| keras#7 | blame | 4 | $0.1250 | 0 | N | N | submit_findings | 10.9 | run_534 |
| keras#15 | blame | 4 | $0.0740 | 0 | N | N | submit_findings | 12.3 | run_538 |
| keras#17 | blame | 4 | $0.0775 | 0 | N | N | submit_findings | 12.1 | run_540 |
| keras#24 | blame | 5 | $0.0988 | 0 | N | N | submit_findings | 17.1 | run_543 |
| keras#26 | blame | 4 | $0.1489 | 2 | Y | N | submit_findings | 26.0 | run_546 |
| keras#28 | blame | 3 | $0.1373 | 3 | Y | N | submit_findings | 26.0 | run_548 |
| keras#34 | blame | 4 | $0.1633 | 3 | Y | N | submit_findings | 25.5 | run_550 |
| keras#35 | blame | 4 | $0.2600 | 2 | Y | N | submit_findings | 20.7 | run_554 |
| luigi#10 | blame | 5 | $0.1329 | 0 | N | N | submit_findings | 23.7 | run_558 |
| luigi#16 | blame | 5 | $0.1079 | 0 | N | N | submit_findings | 15.7 | run_560 |
| luigi#18 | blame | 6 | $0.2602 | 1 | Y | N | submit_findings | 45.2 | run_561 |
| luigi#19 | blame | 6 | $0.2086 | 1 | Y | N | submit_findings | 37.0 | run_564 |
| luigi#26 | blame | 6 | $0.1676 | 1 | Y | N | submit_findings | 29.4 | run_570 |
| luigi#33 | blame | 6 | $0.1326 | 0 | N | N | submit_findings | 22.5 | run_572 |
| matplotlib#10 | blame | 4 | $0.0891 | 0 | N | N | submit_findings | 56.7 | run_576 |
| matplotlib#14 | blame | 4 | $0.0829 | 0 | N | N | submit_findings | 61.4 | run_582 |
| matplotlib#21 | blame | 4 | $0.1377 | 1 | Y | Y | submit_findings | 75.7 | run_590 |
| matplotlib#29 | blame | 4 | $0.1370 | 1 | Y | N | submit_findings | 73.1 | run_598 |
| pandas#21 | blame | 5 | $0.2207 | 0 | N | N | submit_findings | 50.2 | run_600 |
| pandas#22 | blame | 7 | $0.1798 | 0 | N | N | submit_findings | 31.9 | run_608 |
| pandas#27 | blame | 13 | $0.3869 | 1 | N | N | submit_findings | 73.0 | run_611 |
| pandas#35 | blame | 5 | $0.1418 | 0 | N | N | submit_findings | 38.5 | run_620 |
| pandas#42 | blame | 13 | $0.2677 | 1 | Y | Y | submit_findings | 52.6 | run_624 |
| pandas#48 | blame | 4 | $0.1618 | 0 | N | N | submit_findings | 35.0 | run_631 |
| pandas#50 | blame | 3 | $0.1151 | 1 | Y | Y | submit_findings | 26.3 | run_635 |
| pandas#61 | blame | 4 | $0.0880 | 0 | N | N | submit_findings | 29.5 | run_640 |
| pandas#69 | blame | 4 | $0.1267 | 0 | N | N | submit_findings | 24.6 | run_642 |
| pandas#95 | blame | 7 | $0.2614 | 1 | N | N | submit_findings | 60.3 | run_645 |
| pandas#106 | blame | 9 | $0.3432 | 1 | Y | N | submit_findings | 82.8 | run_652 |
| pandas#108 | blame | 8 | $0.1937 | 0 | N | N | submit_findings | 49.1 | run_661 |
| pandas#121 | blame | 11 | $0.3403 | 3 | Y | N | submit_findings | 88.6 | run_666 |
| pandas#132 | blame | 6 | $0.2965 | 1 | Y | N | submit_findings | 59.9 | run_674 |
| pandas#141 | blame | 3 | $0.1479 | 2 | Y | N | submit_findings | 37.2 | run_682 |
| pandas#147 | blame | 4 | $0.0810 | 0 | N | N | submit_findings | 18.7 | run_684 |
| pandas#149 | blame | 3 | $0.1861 | 1 | Y | N | submit_findings | 36.4 | run_686 |
| scrapy#10 | blame | 3 | $0.0711 | 0 | N | N | submit_findings | 10.2 | run_689 |
| scrapy#13 | blame | 5 | $0.3001 | 1 | Y | Y | submit_findings | 24.2 | run_691 |
| scrapy#14 | blame | 4 | $0.0846 | 0 | N | N | submit_findings | 16.3 | run_694 |
| scrapy#15 | blame | 5 | $0.2572 | 2 | Y | Y | submit_findings | 49.2 | run_696 |
| scrapy#24 | blame | 4 | $0.0894 | 0 | N | N | submit_findings | 16.7 | run_698 |
| scrapy#25 | blame | 4 | $0.1004 | 0 | N | N | submit_findings | 17.7 | run_701 |
| scrapy#27 | blame | 3 | $0.0959 | 1 | N | N | submit_findings | 16.6 | run_702 |
| scrapy#31 | blame | 6 | $0.2606 | 2 | Y | Y | submit_findings | 40.9 | run_703 |
| scrapy#36 | blame | 5 | $0.1714 | 1 | N | N | submit_findings | 26.2 | run_704 |
| scrapy#40 | blame | 3 | $0.1783 | 3 | Y | Y | submit_findings | 25.8 | run_705 |
| spacy#5 | blame | 6 | $0.0970 | 0 | N | N | submit_findings | 53.7 | run_706 |
| thefuck#8 | blame | 3 | $0.0554 | 0 | N | N | submit_findings | 6.8 | run_707 |
| thefuck#12 | blame | 7 | $0.1391 | 0 | N | N | submit_findings | 22.8 | run_708 |
| thefuck#15 | blame | 3 | $0.0752 | 1 | Y | Y | submit_findings | 16.5 | run_709 |
| thefuck#20 | blame | 9 | $0.2052 | 4 | Y | Y | submit_findings | 76.6 | run_710 |
| thefuck#21 | blame | 7 | $0.1612 | 2 | Y | Y | submit_findings | 34.0 | run_711 |
| thefuck#23 | blame | 4 | $0.1795 | 3 | Y | Y | submit_findings | 34.2 | run_712 |
| thefuck#25 | blame | 4 | $0.1661 | 1 | Y | Y | submit_findings | 21.7 | run_713 |
| thefuck#26 | blame | 5 | $0.1137 | 2 | Y | Y | submit_findings | 23.7 | run_714 |
| thefuck#28 | blame | 6 | $0.1473 | 2 | Y | Y | submit_findings | 34.3 | run_715 |
| thefuck#32 | blame | 3 | $0.1271 | 0 | N | N | submit_findings | 10.7 | run_716 |
| tornado#5 | blame | 3 | $0.0833 | 0 | N | N | submit_findings | 14.9 | run_717 |
| tornado#11 | blame | 9 | $0.2632 | 2 | Y | N | submit_findings | 47.5 | run_718 |
| tornado#12 | blame | 4 | $0.1635 | 2 | Y | Y | submit_findings | 25.5 | run_719 |
| tqdm#6 | blame | 4 | $0.0893 | 0 | N | N | submit_findings | 9.8 | run_720 |
| tqdm#7 | blame | 4 | $0.1325 | 2 | Y | N | submit_findings | 27.7 | run_721 |

**Summary:** 70 entries, total cost $11.5588, total turns 363, file-hit 32/70, line-hit 15/70.
