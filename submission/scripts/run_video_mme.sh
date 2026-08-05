#!/usr/bin/env bash
# run_video_mme.sh — Video-MME 官方 Benchmark 执行入口
# 当前状态：BLOCKED_BY_OFFICIAL_STARTER_KIT（官方子集/解码/抽帧/答案解析未定）。
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA="${DATA:-/workspace/benchmarks/Video-MME}"
MODE="${1:-candidate}"   # baseline | candidate
OUT="${OUT:-${REPO_ROOT}/submission/benchmark_results/${MODE}}"
mkdir -p "${OUT}"

if [ ! -d "${DATA}" ]; then
  echo "[BLOCKED_BY_ASSET] Video-MME 数据目录不存在: ${DATA}" >&2
  exit 1
fi

OFFICIAL_SCRIPT="${OFFICIAL_SCRIPT:-}"
if [ -z "${OFFICIAL_SCRIPT}" ] || [ ! -f "${OFFICIAL_SCRIPT}" ]; then
  cat >&2 <<'EOF'
[BLOCKED_BY_OFFICIAL_STARTER_KIT]
  Video-MME 数据在，但官方子集/视频解码/抽帧策略/答案解析/分母未定。
  官方到达后确认：短视频/长视频/有音频/无音频/多轮/输入上限分桶。
    OFFICIAL_SCRIPT=/path/to/official.py bash submission/scripts/run_video_mme.sh baseline
    OFFICIAL_SCRIPT=/path/to/official.py bash submission/scripts/run_video_mme.sh candidate
  输出须含：video_mme_{baseline,candidate}_raw.json + comparison.json + VIDEO_MME_REPORT.md
EOF
  exit 2
fi

echo "== run_video_mme [${MODE}] @ ${DATA} =="
# python3 "${OFFICIAL_SCRIPT}" --data "${DATA}" --out "${OUT}" ...
echo "OFFICIAL_RUN_PENDING"
