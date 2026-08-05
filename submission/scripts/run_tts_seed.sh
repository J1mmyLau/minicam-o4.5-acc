#!/usr/bin/env bash
# run_tts_seed.sh — TTS-Seed 官方 Benchmark 执行入口
# 当前状态：BLOCKED_BY_OFFICIAL_STARTER_KIT（官方能力指标 WER/SIM/音频有效性/RTF 未定）。
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA="${DATA:-/workspace/benchmarks/seed-tts-eval}"
MODE="${1:-candidate}"   # baseline | candidate
OUT="${OUT:-${REPO_ROOT}/submission/benchmark_results/${MODE}}"
mkdir -p "${OUT}"

if [ ! -d "${DATA}" ]; then
  echo "[BLOCKED_BY_ASSET] TTS-Seed 数据目录不存在: ${DATA}" >&2
  exit 1
fi

OFFICIAL_SCRIPT="${OFFICIAL_SCRIPT:-}"
if [ -z "${OFFICIAL_SCRIPT}" ] || [ ! -f "${OFFICIAL_SCRIPT}" ]; then
  cat >&2 <<'EOF'
[BLOCKED_BY_OFFICIAL_STARTER_KIT]
  TTS-Seed 数据在，但官方能力指标（WER/SIM/音频有效性/RTF）与脚本未定。
  不得用内部文档猜测最终官方指标。官方到达后：
    OFFICIAL_SCRIPT=/path/to/official.py bash submission/scripts/run_tts_seed.sh baseline
    OFFICIAL_SCRIPT=/path/to/official.py bash submission/scripts/run_tts_seed.sh candidate
  输出须含 baseline vs candidate 完整对比 + 逐 chunk RTF raw（供性能报告）。
EOF
  exit 2
fi

echo "== run_tts_seed [${MODE}] @ ${DATA} =="
# python3 "${OFFICIAL_SCRIPT}" --data "${DATA}" --out "${OUT}" ...
echo "OFFICIAL_RUN_PENDING"
