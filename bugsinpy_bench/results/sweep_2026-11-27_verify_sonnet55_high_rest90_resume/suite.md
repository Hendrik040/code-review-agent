# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_verify_sonnet55_high_rest90_resume

Model: `claude-sonnet-5-5`.  Line tolerance: ±10.  N: 66 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| tornado#4 | blame | 6 | $0.1450 | 1 | Y | N | submit_findings | 20.6 | run_967 |
| tornado#13 | blame | 5 | $0.0709 | 1 | Y | N | submit_findings | 18.5 | run_968 |
| tqdm#2 | blame | 6 | $0.0689 | 2 | Y | Y | submit_findings | 21.0 | run_971 |
| tqdm#4 | blame | 4 | $0.0496 | 1 | Y | N | submit_findings | 14.1 | run_973 |
| black#5 | blame | 4 | $0.0433 | 0 | N | N | submit_findings | 12.7 | run_975 |
| black#11 | blame | 10 | $0.1468 | 0 | N | N | submit_findings | 37.2 | run_977 |
| black#12 | blame | 5 | $0.0613 | 0 | N | N | submit_findings | 12.3 | run_978 |
| black#13 | blame | 5 | $0.0834 | 0 | N | N | submit_findings | 22.0 | run_981 |
| black#16 | blame | 5 | $0.0485 | 0 | N | N | submit_findings | 10.5 | run_983 |
| cookiecutter#1 | blame | 3 | $0.0303 | 0 | N | N | submit_findings | 7.4 | run_984 |
| fastapi#12 | blame | 5 | $0.0637 | 0 | N | N | submit_findings | 10.3 | run_986 |
| httpie#2 | blame | 5 | $0.0662 | 0 | N | N | submit_findings | 13.3 | run_988 |
| keras#7 | blame | 4 | $0.0688 | 1 | Y | N | submit_findings | 12.1 | run_989 |
| keras#15 | blame | 4 | $0.0388 | 0 | N | N | submit_findings | 8.9 | run_991 |
| keras#17 | blame | 4 | $0.0376 | 0 | N | N | submit_findings | 10.7 | run_993 |
| keras#24 | blame | 5 | $0.0484 | 0 | N | N | submit_findings | 11.7 | run_994 |
| keras#26 | blame | 3 | $0.0612 | 1 | Y | N | submit_findings | 16.2 | run_996 |
| keras#28 | blame | 4 | $0.0676 | 2 | Y | N | submit_findings | 18.8 | run_998 |
| keras#34 | blame | 5 | $0.0753 | 1 | Y | N | submit_findings | 19.6 | run_1000 |
| keras#35 | blame | 5 | $0.0592 | 3 | Y | N | submit_findings | 16.2 | run_1002 |
| luigi#10 | blame | 6 | $0.0652 | 0 | N | N | submit_findings | 19.9 | run_1004 |
| luigi#16 | blame | 5 | $0.0497 | 0 | N | N | submit_findings | 15.7 | run_1006 |
| luigi#18 | blame | 7 | $0.1024 | 1 | Y | N | submit_findings | 24.6 | run_1007 |
| luigi#19 | blame | 6 | $0.0643 | 1 | Y | N | submit_findings | 24.9 | run_1009 |
| luigi#26 | blame | 5 | $0.0541 | 1 | Y | N | submit_findings | 15.4 | run_1011 |
| luigi#33 | blame | 5 | $0.0538 | 0 | N | N | submit_findings | 15.0 | run_1013 |
| matplotlib#10 | blame | 3 | $0.0311 | 0 | N | N | submit_findings | 23.8 | run_1015 |
| matplotlib#14 | blame | 4 | $0.0364 | 0 | N | N | submit_findings | 22.0 | run_1017 |
| matplotlib#21 | blame | 6 | $0.0704 | 1 | Y | Y | submit_findings | 31.2 | run_1018 |
| matplotlib#29 | blame | 6 | $0.0738 | 1 | N | N | submit_findings | 31.7 | run_1021 |
| pandas#21 | blame | 5 | $0.0946 | 0 | N | N | submit_findings | 34.0 | run_1023 |
| pandas#22 | blame | 7 | $0.0903 | 0 | N | N | submit_findings | 23.7 | run_1024 |
| pandas#27 | blame | 12 | $0.1631 | 1 | N | N | submit_findings | 51.6 | run_1025 |
| pandas#35 | blame | 7 | $0.0902 | 0 | N | N | submit_findings | 33.7 | run_1028 |
| pandas#42 | blame | 10 | $0.1195 | 1 | Y | Y | submit_findings | 46.3 | run_1029 |
| pandas#48 | blame | 4 | $0.0672 | 0 | N | N | submit_findings | 17.2 | run_1032 |
| pandas#50 | blame | 5 | $0.0653 | 1 | Y | Y | submit_findings | 21.0 | run_1034 |
| pandas#61 | blame | 4 | $0.0415 | 0 | N | N | submit_findings | 17.9 | run_1036 |
| pandas#69 | blame | 5 | $0.0592 | 0 | N | N | submit_findings | 17.6 | run_1039 |
| pandas#95 | blame | 7 | $0.0982 | 0 | N | N | submit_findings | 34.5 | run_1041 |
| pandas#106 | blame | 5 | $0.0644 | 1 | N | N | submit_findings | 24.9 | run_1044 |
| pandas#132 | blame | 7 | $0.1243 | 1 | Y | N | submit_findings | 44.1 | run_1046 |
| pandas#141 | blame | 3 | $0.0641 | 1 | Y | N | submit_findings | 22.2 | run_1049 |
| pandas#147 | blame | 4 | $0.0403 | 0 | N | N | submit_findings | 21.5 | run_1051 |
| pandas#149 | blame | 4 | $0.0808 | 0 | N | N | submit_findings | 24.2 | run_1053 |
| scrapy#10 | blame | 3 | $0.0342 | 0 | N | N | submit_findings | 7.6 | run_1054 |
| scrapy#13 | blame | 5 | $0.0767 | 1 | Y | Y | submit_findings | 19.5 | run_1056 |
| scrapy#14 | blame | 4 | $0.0474 | 0 | N | N | submit_findings | 15.1 | run_1057 |
| scrapy#15 | blame | 3 | $0.0947 | 1 | Y | Y | submit_findings | 26.8 | run_1059 |
| scrapy#24 | blame | 4 | $0.0409 | 0 | N | N | submit_findings | 12.0 | run_1060 |
| scrapy#25 | blame | 5 | $0.0596 | 0 | N | N | submit_findings | 19.8 | run_1062 |
| scrapy#27 | blame | 5 | $0.0623 | 1 | Y | Y | submit_findings | 14.0 | run_1064 |
| scrapy#31 | blame | 5 | $0.1090 | 2 | Y | Y | submit_findings | 24.1 | run_1065 |
| scrapy#36 | blame | 6 | $0.0618 | 0 | N | N | submit_findings | 12.0 | run_1066 |
| scrapy#40 | blame | 5 | $0.0881 | 1 | Y | Y | submit_findings | 23.0 | run_1068 |
| spacy#5 | blame | 7 | $0.0552 | 0 | N | N | submit_findings | 52.9 | run_1070 |
| thefuck#8 | blame | 3 | $0.0278 | 0 | N | N | submit_findings | 6.4 | run_1072 |
| thefuck#15 | blame | 4 | $0.0502 | 2 | Y | Y | submit_findings | 14.7 | run_1073 |

**Summary:** 58 entries, total cost $4.0075, total turns 298, file-hit 23/58, line-hit 10/58.
