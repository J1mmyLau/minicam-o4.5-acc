#!/usr/bin/env bash
# start_server.sh — 启动冻结候选 llama-omni-server
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "${REPO_ROOT}/submission/config/server.env"
if [ -f /usr/local/Ascend/cann/set_env.sh ]; then
  # shellcheck disable=SC1091
  source /usr/local/Ascend/cann/set_env.sh
fi

# run_id + 目录（默认 ${OUTPUT_ROOT}/<run_id>，绝不用 /tmp）
TAG="${TAG:-perf}"
RUN_ID="run_$(date +%Y%m%d_%H%M%S)_${TAG}"
RUN_DIR="${RUN_DIR:-${OUTPUT_ROOT}/${RUN_ID}}"
mkdir -p "${RUN_DIR}/kv_cache"

# KV cache 默认落在 run 目录（避免 /tmp 依赖）；已有则用配置值
export OMNI_KV_CACHE_PATH="${OMNI_KV_CACHE_PATH:-${RUN_DIR}/kv_cache}"

SERVER_BIN="${SERVER_BIN:-${REPO_ROOT}/build/bin/llama-omni-server}"
[ -f "${SERVER_BIN}" ] || { echo "[FAIL] ${SERVER_BIN} 不存在，先 build.sh" >&2; exit 1; }
[ -n "${MODEL_PATH:-}" ] || { echo "[FAIL] MODEL_PATH 未设置（必须显式指定模型路径；无私有默认值）" >&2; exit 1; }
[ -f "${MODEL_PATH}" ] || { echo "[FAIL] MODEL_PATH=${MODEL_PATH} 不存在" >&2; exit 1; }

# 端口冲突检查
if ss -tlnp 2>/dev/null | grep -q ":${SERVER_PORT} "; then
  echo "[FAIL] 端口 ${SERVER_PORT} 已占用" >&2
  exit 1
fi

echo "== RUN_ID = ${RUN_ID} =="
echo "== 端口 = ${SERVER_PORT} | model = ${MODEL_PATH} =="

CMD=(stdbuf -oL -eL "${SERVER_BIN}" -m "${MODEL_PATH}" -ngl "${NGL}" --device "${DEVICE}"
     -c "${CTX}" -b "${BATCH}" -ub "${UBATCH}" --split-mode "${SPLIT_MODE}" --port "${SERVER_PORT}")

# 记录完整命令与环境（复现审计）
{
  echo "# run_id=${RUN_ID}"
  echo "# cmd=${CMD[*]}"
  echo "# cwd=$(pwd)"
  echo "# binary_sha=$(sha256sum "${SERVER_BIN}" | cut -d' ' -f1)"
  echo "# model_sha=$(sha256sum "${MODEL_PATH}" | cut -d' ' -f1)"
  env | grep -E '^(OMNI_|ASCEND|GGML_)' | sort
} > "${RUN_DIR}/run.env"

# 前台启动（评测/录像需要看日志）。日志同时落到 run 目录。
exec "${CMD[@]}" 2>&1 | tee "${RUN_DIR}/server.log"
