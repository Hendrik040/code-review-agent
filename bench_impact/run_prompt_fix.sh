#!/bin/bash
# Prompt-fix test on the 10 bugs whose context overflowed before impact
# selection (bench_impact/prepared_ctxerr10.json), Sonnet 5.5 high and
# Opus 5.5 high, three arms, two repetitions each, all on this branch:
#   old     IMPACT_SELECT=off  (today's one-shot context, overflows)
#   new     IMPACT_SELECT=jev
#   verify  IMPACT_SELECT=jev + REVIEW_PROMPT_VARIANT=verify
# Expected about $14.5. Per-sweep caps Opus $2.4 / Sonnet $1.0; the second
# repetition is skipped if the first one spent more than $9. Then judge
# with the same judge as every other sweep (claude-sonnet-4-5-20250929).
set -u
cd "$(dirname "$0")/.."
export CLAUDE_CONFIG_DIR="$PWD/bench_impact/claude-config-empty"
NEWCLI="$HOME/.local/share/claude/versions/2.1.332"
PB=bench_impact/prepared_ctxerr10.json
mkdir -p bench_impact/logs
run() {  # model tag effort cap arm rep
  local cli="" sel=jev var=""
  [ "$1" = claude-opus-5-5 ] && cli="$NEWCLI"
  [ "$5" = old ] && sel=off
  [ "$5" = verify ] && var=verify
  local id="sweep_2026-11-27_promptfix_${2}_${5}_r$6"
  IMPACT_SELECT=$sel REVIEW_PROMPT_VARIANT=$var REVIEW_CLI_PATH="$cli" REVIEW_MODEL=$1 \
    .venv/bin/python -W ignore bugsinpy_bench/scripts/run_bench.py --prepared $PB --sdk agent \
    --effort $3 --max-cost $4 --sweep-id $id > "bench_impact/logs/$id.log" 2>&1
  echo "done $id exit $? $(date)"
}
spent() {  # sum of suite.md costs for the given repetition
  cat bugsinpy_bench/results/sweep_2026-11-27_promptfix_*_r$1/suite.md 2>/dev/null \
    | awk -F'|' '$2 ~ /#/ { for (i=3;i<=NF;i++) if ($i ~ /\$/) { gsub(/[ $]/,"",$i); s+=$i; break } } END { printf "%.2f", s }'
}
echo "start $(date)"
for rep in 1 2; do
  for arm in old new verify; do
    run claude-opus-5-5   opus55_high   high 2.4 $arm $rep &
    run claude-sonnet-5-5 sonnet55_high high 1.0 $arm $rep &
  done
  wait
  s=$(spent $rep); echo "rep $rep spent \$$s"
  if [ $rep = 1 ] && awk "BEGIN{exit !($s > 9)}"; then echo "over budget, skipping rep 2"; break; fi
done
for d in bugsinpy_bench/results/sweep_2026-11-27_promptfix_*; do
  .venv/bin/python -W ignore bugsinpy_bench/scripts/judge.py "$d" > "bench_impact/logs/judge_$(basename $d).log" 2>&1
  echo "judged $(basename $d) exit $?"
done
echo "all done $(date)"
