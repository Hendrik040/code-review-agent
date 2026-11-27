#!/bin/bash
# Full-benchmark check of the verify prompt (approved budget $25): Jev impact
# selection + REVIEW_PROMPT_VARIANT=verify on Sonnet 5.5 high and Opus 5.5 high,
# over the 90 BugsInPy bugs not in prepared_ctxerr10.json (those 10 already have
# two verify runs) and all 10 Martian PRs. One run each. Expected about $24.8;
# caps Opus $15 / Sonnet $5.3 on BugsInPy and $2.9 / $1.1 on Martian. Claude Code
# 2.1.332 for every run (Opus needs it; for Sonnet it avoids the SDK's 1 MB
# message limit that sentry-greptile#1 hit on the bundled CLI).
set -u
cd "$(dirname "$0")/.."
export IMPACT_SELECT=jev REVIEW_PROMPT_VARIANT=verify
export CLAUDE_CONFIG_DIR="$PWD/bench_impact/claude-config-empty"
export REVIEW_CLI_PATH="$HOME/.local/share/claude/versions/2.1.332"
mkdir -p bench_impact/logs
run() {  # model script prepared cap sweep_id
  REVIEW_MODEL=$1 .venv/bin/python -W ignore $2 --prepared $3 --sdk agent --effort high \
    --max-cost $4 --sweep-id $5 > "bench_impact/logs/$5.log" 2>&1
  echo "done $5 exit $? $(date)"
}
B=bugsinpy_bench/scripts/run_bench.py; M=martian_bench/scripts/run_martian.py
echo "start $(date)"
run claude-opus-5-5   $B bench_impact/prepared_rest90.json 15  sweep_2026-11-27_verify_opus55_high_rest90 &
run claude-sonnet-5-5 $B bench_impact/prepared_rest90.json 5.3 sweep_2026-11-27_verify_sonnet55_high_rest90 &
run claude-opus-5-5   $M martian_bench/dataset/prepared_martian.json 2.9 sweep_2026-11-27_verify_martian_opus55_high &
run claude-sonnet-5-5 $M martian_bench/dataset/prepared_martian.json 1.1 sweep_2026-11-27_verify_martian_sonnet55_high &
wait
for d in bugsinpy_bench/results/sweep_2026-11-27_verify_*; do
  .venv/bin/python -W ignore bugsinpy_bench/scripts/judge.py "$d" > "bench_impact/logs/judge_$(basename $d).log" 2>&1; echo "judged $(basename $d) exit $?"
done
for d in martian_bench/results/sweep_2026-11-27_verify_*; do
  .venv/bin/python -W ignore martian_bench/scripts/judge_martian.py "$d" > "bench_impact/logs/judge_$(basename $d).log" 2>&1; echo "judged $(basename $d) exit $?"
done
echo "all done $(date)"
