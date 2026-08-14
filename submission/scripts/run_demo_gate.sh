#!/usr/bin/env bash
# run_demo_gate.sh — 执行 Demo Gate D1-D12（需官方 Demo 资产到位）
# --dry-run: 仅检查资产是否到位，不实际运行
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "${REPO_ROOT}/submission/config/server.env"

DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=true
  echo "=== Demo Gate DRY-RUN (资产检查) ==="
fi

PASS=0; FAIL=0; NOT_READY=0

gate() {
  local id="$1" desc="$2"
  if [ "$DRY_RUN" = true ]; then
    echo "  [NOT_RUN] ${id} ${desc} (--dry-run, 不生成伪PASS)"
    NOT_READY=$((NOT_READY + 1))
    return 0
  fi
  echo "  [CHECK] ${id} ${desc} → 需官方资产到位后运行"
  NOT_READY=$((NOT_READY + 1))
}

echo "== 环境检查 =="
bash "${REPO_ROOT}/submission/environment/env_check.sh" >/dev/null 2>&1 || {
  echo "[BLOCK] 环境检查未通过"
  exit 1
}

# --- 资产就绪检查 ---
echo ""
echo "== 资产就绪检查 =="

MISSING=()

if [ ! -d "${DEMO_DIR}/.git" ]; then
  MISSING+=("MiniCPM-o-Demo 前端: bash submission/scripts/fetch_demo.sh  (commit ba7fa9c)")
fi

if [ ! -f "${MODEL_PATH}" ]; then
  MISSING+=("模型权重: ${MODEL_PATH}")
fi

if [ ${#MISSING[@]} -gt 0 ]; then
  echo "[BLOCKED_BY_ASSET] 以下资产缺失（全部 NOT_RUN，无伪 PASS）:"
  for m in "${MISSING[@]}"; do
    echo "  - ${m}"
  done
  echo ""
  echo "OFFICIAL_DEMO_GATE=NOT_RUN"
  echo "D1-D12=NOT_RUN (12/12)"
  if [ "$DRY_RUN" = false ]; then
    exit 2
  fi
else
  echo "所有资产就绪，可以运行 Demo Gate。"
fi

# --- D1-D12 ---
echo ""
echo "== D1-D12 Demo Gate =="

gate "D1" "Server start"
gate "D2" "Health check"
gate "D3" "Demo frontend start"
gate "D4" "Demo ↔ server connection"
gate "D5" "Text input"
gate "D6" "Image input"
gate "D7" "Audio input"
gate "D8" "Video input"
gate "D9" "Output completeness"
gate "D10" "Streaming audio continuity"
gate "D11" "Full interaction flow"
gate "D12" "Continuous stability (30min+)"

echo ""
echo "=== Demo Gate 结果 ==="
echo "PASS=${PASS} FAIL=${FAIL} NOT_RUN=${NOT_READY}"
echo ""
echo "OFFICIAL_DEMO_GATE=NOT_RUN"
echo "RUN_DEMO_GATE_PENDING（需官方资产 + 人工操作 + 录像）"

if [ "$DRY_RUN" = true ]; then
  echo ""
  echo "--dry-run 完成：所有 Gate 已标记 NOT_RUN，无伪 PASS 生成。"
  echo "对照表：submission/demo/DEMO_GATE_CHECKLIST.md"
fi
