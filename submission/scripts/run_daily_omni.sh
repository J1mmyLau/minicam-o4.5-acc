#!/usr/bin/env bash
# run_daily_omni.sh — Daily-Omni 官方 Benchmark 执行入口
# 当前状态：BLOCKED_BY_OFFICIAL_STARTER_KIT（官方 Harness/子集/计时口径未到）。
# 官方脚本到达后：确认数据版本/子集/packing/prompt/答案解析/分母 → 在此接入。
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA="${DATA:-/workspace/benchmarks/Daily-Omni}"
MODE="${1:-candidate}"   # baseline | candidate
OUT="${OUT:-${REPO_ROOT}/submission/benchmark_results/${MODE}}"
mkdir -p "${OUT}"

if [ ! -d "${DATA}" ]; then
  echo "[BLOCKED_BY_ASSET] Daily-Omni 数据目录不存在: ${DATA}" >&2
  exit 1
fi
if [ ! -f "${REPO_ROOT}/submission/config/benchmark.yaml" ]; then
  echo "[BLOCKED_BY_ASSET] benchmark.yaml 缺失" >&2
  exit 1
fi

# 官方评测脚本未到 → 明确失败，不伪造
OFFICIAL_SCRIPT="${OFFICIAL_SCRIPT:-}"
if [ -z "${OFFICIAL_SCRIPT}" ] || [ ! -f "${OFFICIAL_SCRIPT}" ]; then
  cat >&2 <<'EOF'
[BLOCKED_BY_OFFICIAL_STARTER_KIT]
  Daily-Omni 数据在，但官方评测脚本/子集/计时口径未定（starter kit 45 项 0/45 确认）。
  内部 pilot 证据：docs/f6-s13-closure/phase2/daily_omni_pilot/PILOT_REPORT.md（非官方准确率）。
  官方脚本到达后设置 OFFICIAL_SCRIPT 并重跑：
    OFFICIAL_SCRIPT=/path/to/official.py bash submission/scripts/run_daily_omni.sh baseline
    OFFICIAL_SCRIPT=/path/to/official.py bash submission/scripts/run_daily_omni.sh candidate
  输出须含：daily_omni_{baseline,candidate}_raw.json + daily_omni_comparison.json + DAILY_OMNI_REPORT.md
EOF
  exit 2
fi

echo "== run_daily_omni [${MODE}] @ ${DATA} =="
# 占位：官方脚本接入点。要求同脚本同子集同分母跑 baseline 与 candidate。
# python3 "${OFFICIAL_SCRIPT}" --data "${DATA}" --subset ... --out "${OUT}" ...
echo "OFFICIAL_RUN_PENDING"
