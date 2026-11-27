#!/bin/bash
# Resume run_verify_full.sh after the API credit ran out (2026-11-27 ~11:00):
# rerun only the entries that crashed at $0 (suite.md cost 0) into *_resume
# sweeps, then re-judge every verify sweep (the first judge pass also failed
# on credit). Remaining budget from the approved $25: about $19.
set -u
cd "$(dirname "$0")/.."
export IMPACT_SELECT=jev REVIEW_PROMPT_VARIANT=verify
export CLAUDE_CONFIG_DIR="$PWD/bench_impact/claude-config-empty"
export REVIEW_CLI_PATH="$HOME/.local/share/claude/versions/2.1.332"
remaining() {  # sweep_dir prepared out -> entries without a paid run
  .venv/bin/python - "$1" "$2" "$3" <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, "bench_impact")
from score_impact import suite_costs, pr_label
sweep, prepared, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
paid = {k for k, v in suite_costs(sweep / "suite.md").items() if v > 0}
def label(e):
    return f"{e['project']}#{e['bug_id']}" if "project" in e else pr_label(e.get("url") or e.get("pr_url") or e["github_url"])
rest = [e for e in json.loads(Path(prepared).read_text()) if label(e) not in paid]
Path(out).write_text(json.dumps(rest, indent=1))
print(f"{sweep.name}: {len(rest)} remaining")
PY
}
run() {  # model script prepared cap sweep_id
  REVIEW_MODEL=$1 .venv/bin/python -W ignore $2 --prepared $3 --sdk agent --effort high \
    --max-cost $4 --sweep-id $5 > "bench_impact/logs/$5.log" 2>&1
  echo "done $5 exit $? $(date)"
}
B=bugsinpy_bench/scripts/run_bench.py; M=martian_bench/scripts/run_martian.py
R=bugsinpy_bench/results; RM=martian_bench/results
remaining $R/sweep_2026-11-27_verify_opus55_high_rest90 bench_impact/prepared_rest90.json bench_impact/prepared_resume_opus.json
remaining $R/sweep_2026-11-27_verify_sonnet55_high_rest90 bench_impact/prepared_rest90.json bench_impact/prepared_resume_sonnet.json
remaining $RM/sweep_2026-11-27_verify_martian_opus55_high martian_bench/dataset/prepared_martian.json bench_impact/prepared_resume_martian_opus.json
remaining $RM/sweep_2026-11-27_verify_martian_sonnet55_high martian_bench/dataset/prepared_martian.json bench_impact/prepared_resume_martian_sonnet.json
run claude-opus-5-5   $B bench_impact/prepared_resume_opus.json 12.6 sweep_2026-11-27_verify_opus55_high_rest90_resume &
run claude-sonnet-5-5 $B bench_impact/prepared_resume_sonnet.json 4.0 sweep_2026-11-27_verify_sonnet55_high_rest90_resume &
run claude-opus-5-5   $M bench_impact/prepared_resume_martian_opus.json 1.8 sweep_2026-11-27_verify_martian_opus55_high_resume &
run claude-sonnet-5-5 $M bench_impact/prepared_resume_martian_sonnet.json 0.5 sweep_2026-11-27_verify_martian_sonnet55_high_resume &
wait
for d in $R/sweep_2026-11-27_verify_*; do
  .venv/bin/python -W ignore bugsinpy_bench/scripts/judge.py "$d" > "bench_impact/logs/judge_$(basename $d).log" 2>&1; echo "judged $(basename $d) exit $?"
done
for d in $RM/sweep_2026-11-27_verify_*; do
  .venv/bin/python -W ignore martian_bench/scripts/judge_martian.py "$d" > "bench_impact/logs/judge_$(basename $d).log" 2>&1; echo "judged $(basename $d) exit $?"
done
echo "all done $(date)"
