# BugsInPy bench — client_sdk @ high — sweep_2026-05-04_client_high_tail

Model: `claude-opus-4-7`.  Line tolerance: ±10.  N: 14 entries.

| entry | source | turns | cost (USD) | findings | file hit | line ±10 | exit | latency (s) | run_id |
|---|---|---:|---:|---:|:---:|:---:|---|---:|---:|
| thefuck#23 | blame | 9 | $0.8394 | 2 | Y | Y | stop_reason_end_turn | 73.3 | run_255 |
| thefuck#25 | blame | 3 | $0.4346 | 0 | N | N | stop_reason_end_turn | 32.8 | run_256 |
| thefuck#26 | blame | 5 | $2.8232 | 1 | Y | Y | stop_reason_end_turn | 48.4 | run_257 |
| thefuck#28 | blame | 14 | $5.1983 | 0 | N | N | stop_reason_end_turn | 175.9 | run_258 |
| thefuck#32 | blame | 4 | $0.4200 | 0 | N | N | stop_reason_end_turn | 22.2 | run_260 |
| tornado#4 | blame | 8 | $0.5789 | 0 | N | N | stop_reason_end_turn | 59.4 | run_261 |
| tornado#5 | blame | 4 | $0.1843 | 0 | N | N | stop_reason_end_turn | 23.2 | run_262 |
| tornado#11 | blame | 11 | $1.5265 | 1 | Y | N | stop_reason_end_turn | 100.4 | run_263 |
| tornado#12 | blame | 8 | $0.6341 | 1 | Y | N | stop_reason_end_turn | 47.2 | run_264 |
| tornado#13 | blame | 7 | $0.4651 | 1 | Y | N | stop_reason_end_turn | 40.7 | run_265 |
| tqdm#2 | blame | 8 | $0.4317 | 1 | Y | Y | stop_reason_end_turn | 53.0 | run_266 |
| tqdm#4 | blame | 6 | $0.4330 | 1 | Y | N | stop_reason_end_turn | 43.5 | run_267 |
| tqdm#6 | blame | 4 | $0.2392 | 0 | N | N | stop_reason_end_turn | 20.2 | run_268 |
| tqdm#7 | blame | 10 | $0.6011 | 1 | Y | N | stop_reason_end_turn | 53.2 | run_269 |

**Summary:** 14 entries, total cost $14.8094, total turns 101, file-hit 8/14, line-hit 3/14.
