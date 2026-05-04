# BugsInPy bench — client_sdk @ max — sweep_2026-05-04_client_max_tail

Model: `claude-opus-4-7`.  Line tolerance: ±10.  N: 41 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| pandas#132 | blame | 40 | $5.4131 | 2 | Y | N | stop_reason_end_turn | 348.5 | run_315 |
| pandas#141 | blame | 28 | $2.7394 | 2 | Y | N | stop_reason_end_turn | 237.5 | run_316 |
| pandas#147 | blame | 7 | $0.3130 | 0 | N | N | stop_reason_end_turn | 43.8 | run_317 |
| pandas#149 | blame | 65 | $8.0570 | 0 | N | N | stop_reason_end_turn | 459.5 | run_318 |
| sanic#1 | blame | 51 | $6.0036 | 3 | Y | Y | stop_reason_end_turn | 423.9 | run_319 |
| scrapy#2 | blame | 30 | $2.4077 | 1 | Y | N | stop_reason_end_turn | 226.5 | run_320 |
| scrapy#4 | blame | 16 | $1.4193 | 1 | Y | N | stop_reason_end_turn | 115.0 | run_321 |
| scrapy#10 | blame | 6 | $0.4104 | 0 | N | N | stop_reason_end_turn | 46.9 | run_322 |
| scrapy#13 | blame | 26 | $2.2093 | 1 | Y | Y | stop_reason_end_turn | 178.1 | run_323 |
| scrapy#14 | blame | 13 | $0.7515 | 0 | N | N | stop_reason_end_turn | 84.6 | run_324 |
| scrapy#15 | blame | 55 | $7.3616 | 1 | Y | Y | stop_reason_end_turn | 503.0 | run_325 |
| scrapy#24 | blame | 6 | $0.3488 | 0 | N | N | stop_reason_end_turn | 37.7 | run_326 |
| scrapy#25 | blame | 21 | $1.4277 | 0 | N | N | stop_reason_end_turn | 134.0 | run_327 |
| scrapy#27 | blame | 7 | $0.7397 | 0 | N | N | stop_reason_end_turn | 71.8 | run_328 |
| scrapy#31 | blame | 63 | $6.4756 | 2 | Y | Y | stop_reason_end_turn | 422.3 | run_329 |
| scrapy#36 | blame | 22 | $2.3353 | 1 | N | N | stop_reason_end_turn | 175.0 | run_330 |
| scrapy#37 | blame | 22 | $1.5110 | 2 | Y | Y | stop_reason_end_turn | 127.8 | run_331 |
| scrapy#40 | blame | 24 | $2.0858 | 1 | Y | Y | stop_reason_end_turn | 128.4 | run_332 |
| spacy#5 | blame | 11 | $0.3920 | 0 | N | N | stop_reason_end_turn | 55.1 | run_333 |
| thefuck#1 | blame | 11 | $1.3642 | 1 | Y | Y | stop_reason_end_turn | 79.7 | run_334 |
| thefuck#7 | blame | 17 | $8.4500 | 0 | N | N | stop_reason_end_turn | 136.5 | run_335 |
| thefuck#8 | blame | 5 | $0.1493 | 0 | N | N | stop_reason_end_turn | 19.3 | run_336 |
| thefuck#9 | blame | 28 | $1.5473 | 2 | Y | Y | stop_reason_end_turn | 168.5 | run_337 |
| thefuck#12 | blame | 26 | $4.4230 | 0 | N | N | stop_reason_end_turn | 218.3 | run_338 |
| thefuck#15 | blame | 10 | $1.4136 | 0 | N | N | stop_reason_end_turn | 91.3 | run_339 |
| thefuck#20 | blame | 17 | $3.7039 | 1 | Y | Y | stop_reason_end_turn | 150.3 | run_340 |
| thefuck#21 | blame | 14 | $4.3523 | 1 | Y | N | stop_reason_end_turn | 111.3 | run_341 |
| thefuck#23 | blame | 21 | $1.9627 | 3 | Y | Y | stop_reason_end_turn | 182.2 | run_342 |
| thefuck#25 | blame | 7 | $0.7476 | 0 | N | N | stop_reason_end_turn | 55.1 | run_343 |
| thefuck#26 | blame | 10 | $3.9259 | 0 | N | N | stop_reason_end_turn | 81.9 | run_344 |
| thefuck#28 | blame | 27 | $9.3881 | 0 | N | N | stop_reason_end_turn | 364.3 | run_345 |
| thefuck#32 | blame | 6 | $0.5830 | 0 | N | N | stop_reason_end_turn | 39.8 | run_346 |
| tornado#4 | blame | 41 | $3.5400 | 0 | N | N | stop_reason_end_turn | 305.4 | run_347 |
| tornado#5 | blame | 5 | $0.5240 | 0 | N | N | stop_reason_end_turn | 57.3 | run_348 |
| tornado#11 | blame | 32 | $4.7779 | 2 | Y | N | stop_reason_end_turn | 317.6 | run_349 |
| tornado#12 | blame | 13 | $1.0919 | 1 | Y | N | stop_reason_end_turn | 87.7 | run_350 |
| tornado#13 | blame | 16 | $1.3296 | 1 | Y | N | stop_reason_end_turn | 119.6 | run_351 |
| tqdm#2 | blame | 43 | $3.6818 | 1 | Y | Y | stop_reason_end_turn | 319.4 | run_352 |
| tqdm#4 | blame | 17 | $1.0649 | 1 | Y | N | stop_reason_end_turn | 93.1 | run_353 |
| tqdm#6 | blame | 8 | $0.4757 | 0 | N | N | stop_reason_end_turn | 43.6 | run_354 |
| tqdm#7 | blame | 21 | $1.3285 | 1 | Y | N | stop_reason_end_turn | 118.6 | run_355 |

**Summary:** 41 entries, total cost $112.2268, total turns 908, file-hit 21/41, line-hit 11/41.
