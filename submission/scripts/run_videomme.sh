#!/usr/bin/env bash
# run_videomme.sh — Video-MME 精度任务执行入口（GM3M9G 修复后的隔离 env）
# 用法: ./run_videomme.sh [smoke|full]   （默认 smoke=2 题；full=50 题全量 ~7-8h）
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${OUT:-/tmp/videomme_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUT"

cd "$REPO_ROOT"
# 精度任务：perf env 全量显式关闭（GM3M9G）
set -a
source "$REPO_ROOT/submission/config/config-accuracy.env"
set +a

set +e
if [ "${1:-smoke}" = "full" ]; then
  export SMOKE_VIDEOMME=0
  EVAL_CONFIG="$REPO_ROOT/submission/config/config-accuracy.env" \
    ./evaluation/run_eval.sh videomme > "$OUT/videomme.log" 2>&1
else
  EVAL_CONFIG="$REPO_ROOT/submission/config/config-accuracy.env" \
    ./evaluation/run_eval.sh videomme > "$OUT/videomme.log" 2>&1
fi
RC=$?
set -e
cp evaluation/output/*/metrics_videomme.json "$OUT/" 2>/dev/null || true
echo "rc=$RC  log=$OUT/videomme.log"
exit $RC
