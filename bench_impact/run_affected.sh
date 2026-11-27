#!/bin/bash
# Re-run the bench entries whose context changes under impact selection,
# with IMPACT_SELECT=jev, on the three tiers the triage sweeps use.
# Waits for the other session's rest70 sweeps so both don't share the key.
# Caps total $23.30 (+$3.47 already spent on a discarded first attempt, < $30
# approved): Opus 2x$7 + Sonnet $3 + Haiku $0.5 on BugsInPy; Opus $4 + Sonnet
# $1.5 + Haiku $0.3 on Martian. Same isolation as the sweeps being compared:
# empty CLAUDE_CONFIG_DIR for every run; Claude Code 2.1.332 for Opus 5.5
# (the SDK's bundled CLI is too old for it), bundled CLI for Sonnet/Haiku.
set -u
cd "$(dirname "$0")/.."
while pgrep -f "sweep_2026-11-27_(opus55|sonnet55|haiku55)_.*_rest70" >/dev/null; do sleep 60; done
echo "start $(date)"
export IMPACT_SELECT=jev
export CLAUDE_CONFIG_DIR="$PWD/bench_impact/claude-config-empty"
NEWCLI="$HOME/.local/share/claude/versions/2.1.332"
PY=".venv/bin/python -W ignore"
run() {  # model effort script prepared cap sweep_id
  local cli=""; [ "$1" = claude-opus-5-5 ] && cli="$NEWCLI"
  REVIEW_CLI_PATH="$cli" REVIEW_MODEL=$1 $PY -c "
import logging, runpy, sys
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
for n in ('httpx', 'httpx2', 'typesafe_sdk'): logging.getLogger(n).setLevel(logging.WARNING)
sys.argv = ['$3', '--prepared', '$4', '--sdk', 'agent', '--effort', '$2', '--max-cost', '$5', '--sweep-id', '$6']
runpy.run_path('$3', run_name='__main__')
" > "bench_impact/logs/$6.log" 2>&1
  echo "done $6 exit $? $(date)"
}
mkdir -p bench_impact/logs
B=bugsinpy_bench/scripts/run_bench.py; M=martian_bench/scripts/run_martian.py
PB=bench_impact/prepared_affected.json; PM=bench_impact/prepared_martian_affected.json
run claude-opus-5-5   high   $B $PB 7   sweep_2026-11-27_impactsel_opus55_high_aff16 &
run claude-sonnet-5-5 high   $B $PB 3   sweep_2026-11-27_impactsel_sonnet55_high_aff16 &
run claude-haiku-5-5  medium $B $PB 0.5 sweep_2026-11-27_impactsel_haiku55_medium_aff16 &
wait
run claude-opus-5-5   high   $B $PB 7   sweep_2026-11-27_impactsel_opus55_high_aff16_rep2 &
run claude-opus-5-5   high   $M $PM 4   sweep_2026-11-27_impactsel_martian_opus55_high_aff6 &
run claude-sonnet-5-5 high   $M $PM 1.5 sweep_2026-11-27_impactsel_martian_sonnet55_high_aff6 &
run claude-haiku-5-5  medium $M $PM 0.3 sweep_2026-11-27_impactsel_martian_haiku55_medium_aff6 &
wait
echo "all done $(date)"
