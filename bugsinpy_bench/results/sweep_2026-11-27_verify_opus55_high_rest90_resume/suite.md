# BugsInPy bench — agent_sdk @ high — sweep_2026-11-27_verify_opus55_high_rest90_resume

Model: `claude-opus-5-5`.  Line tolerance: ±10.  N: 76 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| matplotlib#25 | blame | 6 | $0.3328 | 4 | Y | N | submit_findings | 63.7 | run_969 |
| pandas#6 | blame | 11 | $0.3234 | 2 | Y | N | submit_findings | 70.0 | run_974 |
| pandas#30 | blame | 4 | $0.1007 | 1 | Y | N | submit_findings | 25.6 | run_980 |
| pandas#104 | blame | 4 | $0.1370 | 1 | Y | Y | submit_findings | 39.5 | run_985 |
| sanic#1 | blame | 7 | $0.2935 | 4 | Y | N | submit_findings | 54.1 | run_990 |
| scrapy#2 | blame | 6 | $0.1686 | 1 | Y | N | submit_findings | 25.3 | run_997 |
| scrapy#4 | blame | 7 | $0.1946 | 2 | Y | N | submit_findings | 36.1 | run_999 |
| scrapy#37 | blame | 5 | $0.1196 | 2 | Y | Y | submit_findings | 21.9 | run_1003 |
| thefuck#1 | blame | 3 | $0.1058 | 2 | Y | Y | submit_findings | 23.3 | run_1005 |
| thefuck#9 | blame | 5 | $0.1458 | 4 | Y | Y | submit_findings | 34.0 | run_1008 |
| tornado#4 | blame | 8 | $0.2019 | 2 | Y | N | submit_findings | 40.4 | run_1010 |
| tornado#13 | blame | 6 | $0.1809 | 1 | Y | N | submit_findings | 29.3 | run_1014 |
| tqdm#2 | blame | 5 | $0.1406 | 1 | Y | Y | submit_findings | 27.2 | run_1016 |
| tqdm#4 | blame | 6 | $0.1607 | 2 | Y | N | submit_findings | 23.0 | run_1019 |
| black#5 | blame | 3 | $0.0928 | 0 | N | N | submit_findings | 17.1 | run_1020 |
| black#11 | blame | 8 | $0.3430 | 1 | Y | N | submit_findings | 72.6 | run_1022 |
| black#12 | blame | 4 | $0.1584 | 0 | N | N | submit_findings | 36.2 | run_1026 |
| black#13 | blame | 12 | $0.3688 | 1 | Y | Y | submit_findings | 69.1 | run_1027 |
| black#16 | blame | 5 | $0.0868 | 0 | N | N | submit_findings | 15.0 | run_1030 |
| cookiecutter#1 | blame | 5 | $0.0947 | 0 | N | N | submit_findings | 17.0 | run_1031 |
| fastapi#12 | blame | 5 | $0.1394 | 0 | N | N | submit_findings | 16.5 | run_1033 |
| httpie#2 | blame | 5 | $0.1334 | 0 | N | N | submit_findings | 14.0 | run_1035 |
| keras#7 | blame | 4 | $0.1254 | 0 | N | N | submit_findings | 10.7 | run_1037 |
| keras#15 | blame | 4 | $0.0803 | 0 | N | N | submit_findings | 12.7 | run_1038 |
| keras#17 | blame | 4 | $0.0794 | 0 | N | N | submit_findings | 11.0 | run_1040 |
| keras#24 | blame | 5 | $0.1054 | 0 | N | N | submit_findings | 15.4 | run_1042 |
| keras#26 | blame | 4 | $0.1496 | 2 | Y | N | submit_findings | 26.6 | run_1043 |
| keras#28 | blame | 3 | $0.1392 | 3 | Y | N | submit_findings | 28.3 | run_1045 |
| keras#34 | blame | 6 | $0.1821 | 3 | Y | N | submit_findings | 27.0 | run_1047 |
| keras#35 | blame | 5 | $0.1431 | 2 | Y | N | submit_findings | 25.6 | run_1048 |
| luigi#10 | blame | 6 | $0.1315 | 0 | N | N | submit_findings | 25.8 | run_1050 |
| luigi#16 | blame | 8 | $0.1401 | 0 | N | N | submit_findings | 20.7 | run_1052 |
| luigi#18 | blame | 5 | $0.2054 | 1 | Y | N | submit_findings | 36.8 | run_1055 |
| luigi#19 | blame | 5 | $0.1388 | 1 | Y | N | submit_findings | 36.5 | run_1058 |
| luigi#26 | blame | 5 | $0.1175 | 1 | Y | N | submit_findings | 21.5 | run_1061 |
| luigi#33 | blame | 6 | $0.1214 | 0 | N | N | submit_findings | 20.3 | run_1063 |
| matplotlib#10 | blame | 3 | $0.0689 | 0 | N | N | submit_findings | 34.4 | run_1067 |
| matplotlib#14 | blame | 6 | $0.1280 | 0 | N | N | submit_findings | 31.3 | run_1069 |
| matplotlib#21 | blame | 5 | $0.1495 | 1 | Y | Y | submit_findings | 44.3 | run_1071 |
| matplotlib#29 | blame | 6 | $0.2088 | 2 | Y | N | submit_findings | 51.2 | run_1074 |
| pandas#21 | blame | 5 | $0.2293 | 0 | N | N | submit_findings | 52.3 | run_1075 |
| pandas#22 | blame | 5 | $0.1670 | 0 | N | N | stop_reason_end_turn | 41.1 | run_1076 |
| pandas#27 | blame | 15 | $0.4491 | 1 | N | N | submit_findings | 77.9 | run_1077 |
| pandas#35 | blame | 7 | $0.2143 | 0 | N | N | submit_findings | 50.8 | run_1078 |
| pandas#42 | blame | 7 | $0.2376 | 3 | Y | Y | submit_findings | 44.2 | run_1079 |
| pandas#48 | blame | 4 | $0.1404 | 0 | N | N | submit_findings | 23.2 | run_1080 |
| pandas#50 | blame | 4 | $0.1181 | 1 | Y | Y | submit_findings | 23.2 | run_1081 |
| pandas#61 | blame | 4 | $0.0923 | 0 | N | N | submit_findings | 21.1 | run_1082 |
| pandas#69 | blame | 6 | $0.1388 | 0 | N | N | submit_findings | 25.8 | run_1083 |
| pandas#95 | blame | 8 | $0.2579 | 1 | Y | Y | submit_findings | 54.1 | run_1084 |
| pandas#106 | blame | 9 | $0.2514 | 1 | Y | N | submit_findings | 52.7 | run_1085 |
| pandas#132 | blame | 4 | $0.2101 | 0 | N | N | submit_findings | 40.8 | run_1086 |
| pandas#141 | blame | 3 | $0.1552 | 2 | Y | N | submit_findings | 33.5 | run_1087 |
| pandas#147 | blame | 4 | $0.0782 | 0 | N | N | submit_findings | 16.7 | run_1088 |
| pandas#149 | blame | 5 | $0.2047 | 1 | Y | N | submit_findings | 31.0 | run_1089 |
| scrapy#10 | blame | 3 | $0.0701 | 0 | N | N | submit_findings | 13.0 | run_1090 |
| scrapy#13 | blame | 4 | $0.1449 | 1 | Y | Y | submit_findings | 20.5 | run_1091 |
| scrapy#14 | blame | 5 | $0.0942 | 0 | N | N | submit_findings | 16.6 | run_1092 |
| scrapy#15 | blame | 5 | $0.2382 | 2 | Y | Y | submit_findings | 45.8 | run_1093 |
| scrapy#24 | blame | 5 | $0.0949 | 0 | N | N | submit_findings | 14.6 | run_1094 |
| scrapy#25 | blame | 3 | $0.0713 | 0 | N | N | submit_findings | 10.0 | run_1095 |
| scrapy#27 | blame | 4 | $0.1172 | 0 | N | N | submit_findings | 16.1 | run_1096 |
| scrapy#31 | blame | 5 | $0.2319 | 2 | Y | Y | submit_findings | 33.8 | run_1097 |
| scrapy#36 | blame | 4 | $0.1243 | 0 | N | N | submit_findings | 15.1 | run_1098 |
| scrapy#40 | blame | 5 | $0.1925 | 2 | Y | Y | submit_findings | 26.8 | run_1099 |
| spacy#5 | blame | 6 | $0.0985 | 0 | N | N | submit_findings | 54.2 | run_1100 |
| thefuck#8 | blame | 3 | $0.0570 | 0 | N | N | submit_findings | 9.4 | run_1101 |
| thefuck#15 | blame | 3 | $0.0812 | 1 | Y | Y | submit_findings | 16.6 | run_1102 |
| thefuck#23 | blame | 4 | $0.1791 | 3 | Y | Y | submit_findings | 33.8 | run_1103 |
| thefuck#25 | blame | 3 | $0.0797 | 1 | Y | Y | submit_findings | 14.6 | run_1104 |
| thefuck#32 | blame | 4 | $0.0844 | 0 | N | N | submit_findings | 11.0 | run_1105 |
| tornado#5 | blame | 3 | $0.0718 | 0 | N | N | submit_findings | 10.5 | run_1106 |
| tornado#11 | blame | 11 | $0.3920 | 4 | Y | N | submit_findings | 76.3 | run_1107 |
| tornado#12 | blame | 4 | $0.1739 | 2 | Y | Y | submit_findings | 30.2 | run_1108 |
| tqdm#6 | blame | 4 | $0.0892 | 0 | N | N | submit_findings | 9.8 | run_1109 |
| tqdm#7 | blame | 4 | $0.1371 | 1 | Y | N | submit_findings | 25.3 | run_1110 |

**Summary:** 76 entries, total cost $12.2054, total turns 402, file-hit 41/76, line-hit 18/76.
