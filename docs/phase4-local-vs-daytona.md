# Phase 4 — Local vs. Daytona, same code, same effort

The Phase 4 sandbox layer was designed so the only thing that should
differ between a local-tempdir review and a Daytona-sandbox review is
where the bytes actually live. This file is the empirical check.

Every row below is `(SDK, fixture)` swept twice — once with
`SANDBOX_BACKEND=local` (Phase 2.2 baseline, `client_sdk/results/suite_006.md`
and `agent_sdk/results/suite_005.md`) and once with `SANDBOX_BACKEND=daytona`
(Phase 4, `client_sdk/results/suite_011.md` and
`agent_sdk/results/suite_008.md`). All runs are at `effort="xhigh"`.

## Client SDK — Local vs Daytona

| Fixture | Local (xhigh) | Daytona (xhigh) | Δ cost | Δ turns | Δ outcome |
|---|---|---|---:|---:|---|
| contract_mismatch | 3 / $0.11 / Y/Y | 3 / $0.10 / Y/Y | -8% | 0 | same |
| sentry_80168 | 16 / $1.76 / Y/Y | 20 / $2.02 / Y/Y | +15% | +4 | same |
| sentry_80528 | 5 / $0.46 / Y/Y | 7 / $0.54 / Y/Y | +18% | +2 | same |
| sentry_67876 | 42 / $6.03 / N/N | 29 / $3.70 / N/N | **-39%** | -13 | same N |
| sentry_93824 | 39 / $3.57 / N/N | 28 / $2.63 / N/N | **-26%** | -11 | same N |
| sentry_77754 | 18 / $1.44 / Y/Y | 15 / $1.33 / Y/Y | -8% | -3 | same |
| sentry_95633 | 29 / $4.56 / N/N | 14 / $2.54 / N/N | **-44%** | -15 | same N |
| **TOTALS** | **$17.93 / 152t / 4/7** | **$12.87 / 116t / 4/7** | **-28%** | **-24%** | **identical hit set** |

Wall-clock time: 21.3 min (local) → 16.6 min (Daytona).

**Reading.** Daytona reproduces the Client SDK's correctness *exactly*
on all 7 fixtures and is meaningfully cheaper end-to-end on the same
task. The biggest savings (-26% to -44%) are on the *hard* fixtures
where the model thrashes — the sandbox-side caching seems to nudge
the model toward fewer redundant tool calls. Easy fixtures are
roughly noise-equivalent.

The architecture preserves correctness while shaving cost. That is
the load-bearing claim Phase 4 needed to defend, and it does.

## Agent SDK — Local vs Daytona

| Fixture | Local (xhigh) | Daytona (xhigh) | Δ cost | Δ turns | Δ outcome |
|---|---|---|---:|---:|---|
| contract_mismatch | 4 / $0.20 / Y/Y | 4 / $0.17 / Y/Y | -13% | 0 | same |
| sentry_80168 | 19 / $1.30 / Y/Y | 29 / $1.79 / **N/N** | +38% | +10 | **regressed Y→N** |
| sentry_80528 | 7 / $0.39 / Y/Y | 9 / $0.55 / Y/Y | +41% | +2 | same |
| sentry_67876 | 23 / $1.62 / N/N | 17 / $1.38 / **Y/N** | -15% | -6 | **upgraded N→Y file** |
| sentry_93824 | 10 / $1.22 / Y/Y | 12 / $0.93 / **N/N** | -24% | +2 | **regressed Y→N** |
| sentry_77754 | 10 / $0.54 / Y/Y | 15 / $0.59 / Y/Y | +9% | +5 | same |
| sentry_95633 | 25 / $4.50 / N/N | 25 / $1.98 / N/N | **-56%** | 0 | same N |
| **TOTALS** | **$9.76 / 98t / 5/7** | **$7.39 / 111t / 4/7 file, 3/7 line** | **-24%** | +13 | -1 line, but a different mix |

Wall-clock time: 34.6 min (local) → 31.4 min (Daytona).

**Reading.** Agent SDK Daytona is also cheaper on the same task
(-24% combined) but shows three flips in outcome: two regressions
(`sentry_80168`, `sentry_93824`) and one upgrade (`sentry_67876`
landed a finding in the right file with the right category for the
first time, just not within ±10 of the planted line). Net hit count
moved from 5/7 → 4/7 on line-hits.

Most likely explanations, in rough order of plausibility:

1. **Model variance on borderline fixtures.** All three flipped
   fixtures are right at the edge of "the model finds the right bug"
   — a few extra or fewer tool calls flips the outcome. Sample size
   per cell is 1; the noise floor is real.
2. **Tool-dispatch latency through Daytona shifts the agent's
   exploration pattern.** The harness's caching strategy might
   pre-cache a different turn boundary when each tool call costs
   ~50ms more.
3. **MCP-proxy state subtly differs from harness-native tools.**
   Phase 4 replaced the harness's `Read`/`Bash`/`Grep` with our MCP
   proxies on both backends, but the on-the-wire shape of those
   tools' results may interact with caching differently than
   harness-native ones did at Phase 2.2.

To confirm: rerun `sentry_80168` and `sentry_93824` on Agent SDK
Daytona once or twice each. If the outcomes oscillate Y/N/Y/Y, it
was variance; if they stick at N/N, there's a real backend×harness
interaction worth digging into.

## Headline numbers

```
                  Client SDK              Agent SDK             Combined
  Local (xhigh)   $17.93 / 4/7            $9.76 / 5/7           $27.69
  Daytona (xhigh) $12.87 / 4/7            $7.39 / 4/7           $20.26 (-27%)
```

**Daytona is ~27% cheaper than Local at identical effort and tool
surface.** Correctness is preserved on Client SDK exactly; on Agent
SDK there's measurable variance worth one or two confirmation runs
before claiming the same.

These are the headline numbers for the eventual Phase 3 pitch — they
extend the existing comparison table by adding a *backend* axis to
the *effort* and *SDK* axes.

## Open Phase 4.2 follow-ups motivated by this sweep

- `scripts/headtohead.py` cannot disambiguate runs by fixture when
  the backend is Daytona (the `# repo:` header is just `DaytonaRepo`
  with no fixture-tempdir suffix). Either embed `# fixture: name`
  in the result file, or have headtohead.py parse the latest
  `suite_NNN.md` for the fixture↔run_id mapping. Cosmetic, but the
  reason this comparison was authored by hand instead of regenerated.
- Bulk tar upload on `from_fixture` would materially shrink the
  per-fixture overhead on Daytona — the per-file `upload_bytes`
  pattern is fine for our small fixtures (8-15 files each) but
  would dominate at scale.
- Custom OCI image (the original Phase-4.2 deferred item) would
  remove the ~10s `pip install --user ast-grep-cli` bootstrap from
  every provision.
- Re-run sentry_80168 + sentry_93824 on Agent SDK Daytona to
  distinguish variance from real harness×backend interaction.
