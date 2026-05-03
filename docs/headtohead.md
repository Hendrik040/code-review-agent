# Client SDK vs Agent SDK — head-to-head

Latest run per fixture, current category-aware matcher, line tolerance ±10. Hit format: file_hit / line_hit.

| fixture | client turns | client cost | client F/L | agent turns | agent cost | agent F/L |
|---|---:|---:|:---:|---:|---:|:---:|
| contract_mismatch | 3 | $0.1076 | Y/Y | 4 | $0.1993 | Y/Y |
| sentry_80168 | 16 | $1.7587 | Y/Y | 19 | $1.2952 | Y/Y |
| sentry_80528 | 5 | $0.4632 | Y/Y | 7 | $0.3902 | Y/Y |
| sentry_67876 | 42 | $6.0257 | N/N | 23 | $1.6211 | N/N |
| sentry_93824 | 39 | $3.5669 | N/N | 10 | $1.2177 | Y/Y |
| sentry_77754 | 18 | $1.4447 | Y/Y | 10 | $0.5389 | Y/Y |
| sentry_95633 | 29 | $4.5587 | N/N | 25 | $4.4991 | N/N |
| **Totals** | **152** | **$17.9255** | **4/7 f, 4/7 l** | **98** | **$9.7615** | **5/7 f, 5/7 l** |

**Cost delta:** Agent SDK total = $9.7615 vs Client SDK total = $17.9255 (-45.5%).
