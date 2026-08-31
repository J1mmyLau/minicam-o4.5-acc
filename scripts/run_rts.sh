#!/usr/bin/env bash
# run_rts.sh — Track A 性能主指标（SPEAK→WAV 完整链路 RTF）执行入口
# 用法: ./run_rts.sh [seed]      （默认 seed=1001）
# 输出: metrics_rts.json（均值/分解/SPEAK→wav 毫秒数）+ rts.log + judge-final 会话报告
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SEED="${1:-1001}"
OUT="${OUT:-/tmp/rts_seed${SEED}_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUT"

cd "$REPO_ROOT"
# A+C 配方 + TileLang 核 + RTS 专用 NFE2 —— 全部 launch-only 注入
set -a
source "$REPO_ROOT/submission/config/server.env"
set +a
export OMNI_T2W_N_TIMESTEPS=2
export OMNI_T2W_PROMPT_CACHE=/workspace/models/token2wav-rts-nfe2/prompt_cache.gguf
export EVAL_CONFIG="$REPO_ROOT/config-local.env"
set +e

EVAL_SEED="$SEED" RTS_MAX_DURATION=120 ./evaluation/run_eval.sh rts \
  > "$OUT/rts.log" 2>&1
RC=$?
set -e
# 只拷贝本次 run 的 metrics（最新 output 目录），避免 glob 把历史 run 的 json 带进来
NEWEST_OUT=$(ls -1t evaluation/output/ | head -1)
cp "evaluation/output/$NEWEST_OUT/metrics_rts.json" "$OUT/" 2>/dev/null || true
echo "rc=$RC  log=$OUT/rts.log  metrics=$OUT/metrics_rts.json"
exit $RC
