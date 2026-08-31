#!/usr/bin/env bash
# run_tts_seed.sh — TTS-Seed 精度任务执行入口（WER + SIM，GM3M9G 修复后的隔离 env）
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${OUT:-/tmp/tts_seed_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUT"

cd "$REPO_ROOT"
set -a
source "$REPO_ROOT/submission/config/config-accuracy.env"
set +a

set +e
EVAL_CONFIG="$REPO_ROOT/submission/config/config-accuracy.env" \
  ./evaluation/run_eval.sh tts > "$OUT/tts.log" 2>&1
RC=$?
set -e
cp evaluation/output/*/metrics_tts.json "$OUT/" 2>/dev/null || true
echo "rc=$RC  log=$OUT/tts.log"
exit $RC
