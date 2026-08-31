#!/usr/bin/env bash
# run_daily_omni.sh — Daily-Omni 精度任务执行入口（GM3M9G 修复后的隔离 env）
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${OUT:-/tmp/daily_omni_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUT"

cd "$REPO_ROOT"
set -a
source "$REPO_ROOT/submission/config/config-accuracy.env"
set +a

set +e
EVAL_CONFIG="$REPO_ROOT/submission/config/config-accuracy.env" \
  ./evaluation/run_eval.sh daily-omni > "$OUT/daily.log" 2>&1
RC=$?
set -e
cp evaluation/output/*/metrics_daily.json "$OUT/" 2>/dev/null || true
echo "rc=$RC  log=$OUT/daily.log"
exit $RC
