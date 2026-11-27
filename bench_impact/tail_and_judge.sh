#!/bin/bash
# Sonnet rerun of sentry-greptile#1 on Claude Code 2.1.332 (bundled CLI hit the
# SDK's 1 MB message limit, as in the compared sweep), then judge every sweep
# with the same judge as the compared sweeps (claude-sonnet-4-5-20250929).
set -u
cd "$(dirname "$0")/.."
export IMPACT_SELECT=jev CLAUDE_CONFIG_DIR="$PWD/bench_impact/claude-config-empty"
REVIEW_CLI_PATH="$HOME/.local/share/claude/versions/2.1.332" REVIEW_MODEL=claude-sonnet-5-5 \
  .venv/bin/python -W ignore martian_bench/scripts/run_martian.py --prepared bench_impact/prepared_martian_greptile1.json \
  --sdk agent --effort high --max-cost 1 --sweep-id sweep_2026-11-27_impactsel_martian_sonnet55_high_aff6_tail \
  > bench_impact/logs/sweep_2026-11-27_impactsel_martian_sonnet55_high_aff6_tail.log 2>&1
echo "tail exit $?"
for d in bugsinpy_bench/results/sweep_2026-11-27_impactsel_*; do
  .venv/bin/python -W ignore bugsinpy_bench/scripts/judge.py "$d" > "bench_impact/logs/judge_$(basename $d).log" 2>&1; echo "judged $(basename $d) exit $?"
done
for d in martian_bench/results/sweep_2026-11-27_impactsel_*; do
  .venv/bin/python -W ignore martian_bench/scripts/judge_martian.py "$d" > "bench_impact/logs/judge_$(basename $d).log" 2>&1; echo "judged $(basename $d) exit $?"
done
