# BugsInPy bench — client_sdk @ max — sweep_2026-05-04_client_max

Model: `claude-opus-4-7`.  Line tolerance: ±10.  N: 100 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| PySnooper#3 | blame | 26 | $1.9041 | 1 | Y | Y | stop_reason_end_turn | 131.8 | run_239 |
| ansible#3 | blame | 27 | $2.2896 | 0 | N | N | stop_reason_end_turn | 192.8 | run_240 |
| ansible#15 | blame | 10 | $2.5244 | 0 | N | N | stop_reason_end_turn | 109.5 | run_241 |
| black#1 | blame | 7 | $0.3872 | 1 | Y | N | stop_reason_end_turn | 42.3 | run_242 |
| black#5 | blame | 19 | $1.1526 | 0 | N | N | stop_reason_end_turn | 98.0 | run_243 |
| black#11 | blame | 80 | $11.0919 | 0 | N | N | stop_reason_end_turn | 594.7 | run_244 |
| black#12 | blame | 49 | $3.6641 | 0 | N | N | stop_reason_end_turn | 262.4 | run_245 |
| black#13 | blame | 87 | $12.2550 | 1 | Y | N | stop_reason_end_turn | 785.0 | run_246 |
| black#16 | blame | 15 | $0.7342 | 0 | N | N | stop_reason_end_turn | 88.4 | run_247 |
| cookiecutter#1 | blame | 5 | $0.1975 | 0 | N | N | stop_reason_end_turn | 27.8 | run_248 |
| cookiecutter#4 | blame | 17 | $1.7017 | 1 | Y | Y | stop_reason_end_turn | 169.8 | run_249 |
| fastapi#8 | blame | 14 | $0.5199 | 0 | N | N | stop_reason_end_turn | 58.3 | run_250 |
| fastapi#12 | blame | 7 | $0.6315 | 0 | N | N | stop_reason_end_turn | 45.6 | run_251 |
| httpie#2 | blame | 17 | $1.0166 | 0 | N | N | stop_reason_end_turn | 82.4 | run_252 |
| keras#3 | blame | 46 | $7.2918 | 1 | Y | N | stop_reason_end_turn | 527.5 | run_253 |
| keras#4 | blame | 14 | $1.1829 | 3 | Y | N | stop_reason_end_turn | 113.5 | run_254 |
| keras#7 | blame | 13 | $0.9856 | 0 | N | N | stop_reason_end_turn | 68.9 | run_255 |
| keras#13 | blame | 7 | $0.4565 | 1 | Y | Y | stop_reason_end_turn | 48.4 | run_256 |
| keras#15 | blame | 13 | $0.6809 | 0 | N | N | stop_reason_end_turn | 80.2 | run_257 |
| keras#17 | blame | 12 | $0.6725 | 0 | N | N | stop_reason_end_turn | 71.7 | run_258 |
| keras#24 | blame | 12 | $0.7099 | 0 | N | N | stop_reason_end_turn | 78.7 | run_259 |
| keras#26 | blame | 10 | $0.9068 | 1 | Y | N | stop_reason_end_turn | 85.5 | run_260 |
| keras#28 | blame | 21 | $2.4861 | 2 | Y | N | stop_reason_end_turn | 263.9 | run_261 |
| keras#32 | blame | 31 | $3.0961 | 1 | Y | N | stop_reason_end_turn | 280.5 | run_266 |
| keras#34 | blame | 12 | $0.8428 | 1 | Y | N | stop_reason_end_turn | 62.9 | run_270 |
| keras#35 | blame | 9 | $0.5439 | 1 | Y | N | stop_reason_end_turn | 61.2 | run_271 |
| luigi#2 | blame | 8 | $0.4051 | 1 | Y | N | stop_reason_end_turn | 50.7 | run_272 |
| luigi#4 | blame | 8 | $0.4963 | 1 | Y | N | stop_reason_end_turn | 51.7 | run_273 |
| luigi#5 | blame | 22 | $2.5630 | 1 | Y | N | stop_reason_end_turn | 173.5 | run_274 |
| luigi#10 | blame | 36 | $3.4753 | 0 | N | N | stop_reason_end_turn | 288.6 | run_275 |
| luigi#16 | blame | 28 | $1.9215 | 0 | N | N | stop_reason_end_turn | 188.1 | run_276 |
| luigi#18 | blame | 65 | $8.4004 | 1 | Y | N | stop_reason_end_turn | 579.4 | run_277 |
| luigi#19 | blame | 58 | $8.6327 | 1 | Y | N | stop_reason_end_turn | 619.2 | run_285 |
| luigi#26 | blame | 25 | $2.1027 | 2 | Y | N | stop_reason_end_turn | 205.5 | run_288 |
| luigi#33 | blame | 23 | $1.4685 | 0 | N | N | stop_reason_end_turn | 130.3 | run_290 |
| matplotlib#6 | blame | 46 | $4.4539 | 0 | N | N | stop_reason_end_turn | 350.6 | run_291 |
| matplotlib#10 | blame | 7 | $0.5231 | 0 | N | N | stop_reason_end_turn | 60.7 | run_292 |
| matplotlib#14 | blame | 7 | $0.3560 | 0 | N | N | stop_reason_end_turn | 42.0 | run_293 |
| matplotlib#21 | blame | 16 | $1.3252 | 1 | Y | Y | stop_reason_end_turn | 124.1 | run_294 |
| matplotlib#23 | blame | 34 | $3.7566 | 1 | Y | Y | stop_reason_end_turn | 273.7 | run_295 |
| matplotlib#25 | blame | 24 | $2.3579 | 5 | Y | N | stop_reason_end_turn | 198.8 | run_296 |
| matplotlib#29 | blame | 51 | $3.8648 | 1 | N | N | stop_reason_end_turn | 239.6 | run_297 |
| pandas#6 | blame | 46 | $4.0149 | 0 | N | N | stop_reason_end_turn | 259.6 | run_298 |
