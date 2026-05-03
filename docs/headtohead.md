# Client SDK vs Agent SDK — head-to-head

Latest run per fixture, current category-aware matcher, line tolerance ±10. Hit format: file_hit / line_hit.

| fixture | client turns | client cost | client F/L | agent turns | agent cost | agent F/L |
|---|---:|---:|:---:|---:|---:|:---:|
| contract_mismatch | 3 | $0.0954 | Y/Y | 4 | $0.1472 | Y/Y |
| sentry_80168 | 18 | $1.7931 | Y/Y | 14 | $1.0005 | Y/Y |
| sentry_80528 | 5 | $0.5034 | Y/Y | 6 | $0.4986 | Y/Y |
| sentry_67876 | 16 | $1.7766 | N/N | 20 | $0.9539 | N/N |
| sentry_93824 | 20 | $1.6459 | Y/Y | 8 | $0.8168 | N/N |
| sentry_77754 | 14 | $1.0900 | Y/Y | 12 | $0.4950 | Y/Y |
| sentry_95633 | 13 | $2.1825 | N/N | 21 | $2.0512 | N/N |
| **Totals** | **89** | **$9.0869** | **5/7 f, 5/7 l** | **85** | **$5.9631** | **4/7 f, 4/7 l** |

**Cost delta:** Agent SDK total = $5.9631 vs Client SDK total = $9.0869 (-34.4%).
