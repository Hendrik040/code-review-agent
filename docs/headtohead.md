# Client SDK vs Agent SDK — head-to-head

Latest run per fixture, current category-aware matcher, line tolerance ±10. Hit format: file_hit / line_hit.

Cost basis: both columns are USD at the `claude-opus-4-7` API rate. Agent SDK cost is the harness-reported `total_cost_usd`; Client SDK cost is recomputed from each run's stored usage with `pricing.py`.

| fixture | client turns | client cost | client F/L | agent turns | agent cost | agent F/L |
|---|---:|---:|:---:|---:|---:|:---:|
| contract_mismatch | 3 | $0.0359 | Y/Y | 4 | $0.1993 | Y/Y |
| sentry_80168 | 16 | $0.5862 | Y/Y | 19 | $1.2952 | Y/Y |
| sentry_80528 | 5 | $0.1544 | Y/Y | 7 | $0.3902 | Y/Y |
| sentry_67876 | 42 | $2.0086 | N/N | 23 | $1.6211 | N/N |
| sentry_93824 | 39 | $1.1890 | N/N | 10 | $1.2177 | Y/Y |
| sentry_77754 | 18 | $0.4816 | Y/Y | 10 | $0.5389 | Y/Y |
| sentry_95633 | 29 | $1.5196 | N/N | 25 | $4.4991 | N/N |
| **Totals** | **152** | **$5.9752** | **4/7 f, 4/7 l** | **98** | **$9.7615** | **5/7 f, 5/7 l** |

**Cost delta:** Agent SDK total = $9.7615 vs Client SDK total = $5.9752 (+63.4%).
