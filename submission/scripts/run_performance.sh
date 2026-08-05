#!/usr/bin/env bash
# run_performance.sh — 逐 chunk RTF 采集（llama 子赛道核心指标）
# 流程：启动冻结服务 → 驱动 N 个 TTS 请求 → 解析日志 → chunk_rtf_raw.csv + summary.json
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "${REPO_ROOT}/submission/config/server.env"
if [ -f /usr/local/Ascend/cann/set_env.sh ]; then
  # shellcheck disable=SC1091
  source /usr/local/Ascend/cann/set_env.sh
fi

N="${N:-3}"
RUN_ID="run_$(date +%Y%m%d_%H%M%S)_perf"
RUN_DIR="${RUN_DIR:-${REPO_ROOT}/results/${RUN_ID}}"
OUT_DIR="${OUT_DIR:-${REPO_ROOT}/submission/performance}"
mkdir -p "${RUN_DIR}/kv_cache" "${OUT_DIR}"
export OMNI_KV_CACHE_PATH="${OMNI_KV_CACHE_PATH:-${RUN_DIR}/kv_cache}"

SERVER_BIN="${SERVER_BIN:-${REPO_ROOT}/build/bin/llama-omni-server}"
[ -f "${SERVER_BIN}" ] || { echo "[FAIL] ${SERVER_BIN} 不存在" >&2; exit 1; }

if ss -tlnp 2>/dev/null | grep -q ":${SERVER_PORT} "; then
  echo "[FAIL] 端口 ${SERVER_PORT} 已占用" >&2; exit 1
fi

echo "== RUN_ID=${RUN_ID} | N=${N} | port=${SERVER_PORT} =="

# 1) 启动冻结服务（后台）
BIN_SHA="$(sha256sum "${SERVER_BIN}" | cut -d' ' -f1)"
MODEL_SHA="$(sha256sum "${MODEL_PATH}" | cut -d' ' -f1)"
stdbuf -oL -eL "${SERVER_BIN}" -m "${MODEL_PATH}" -ngl "${NGL}" --device "${DEVICE}" \
  -c "${CTX}" -b "${BATCH}" -ub "${UBATCH}" --split-mode "${SPLIT_MODE}" --port "${SERVER_PORT}" \
  > "${RUN_DIR}/server.log" 2>&1 &
SRV_PID=$!
trap 'kill ${SRV_PID} 2>/dev/null || true' EXIT
echo "server pid=${SRV_PID} → ${RUN_DIR}/server.log"

# 2) 等待 health
for i in $(seq 1 120); do
  if curl -sf "http://127.0.0.1:${SERVER_PORT}/health" >/dev/null 2>&1; then
    echo "health OK after ${i}s"; break
  fi
  if ! kill -0 "${SRV_PID}" 2>/dev/null; then echo "[FAIL] server 提前退出" >&2; tail -30 "${RUN_DIR}/server.log" >&2; exit 1; fi
  sleep 1
  [ "${i}" = "120" ] && { echo "[FAIL] health 超时" >&2; exit 1; }
done

# 3) 驱动 TTS 请求
python3 "${REPO_ROOT}/submission/scripts/run_chunk_rtf_client.py" \
  --port "${SERVER_PORT}" --n "${N}" --text-dir "${TEXT_DIR:-}" \
  > "${RUN_DIR}/client.log" 2>&1 || { echo "[FAIL] 客户端失败" >&2; tail -30 "${RUN_DIR}/client.log" >&2; exit 1; }

# 4) 停服（等 drain）
sleep 2
kill "${SRV_PID}" 2>/dev/null || true
wait "${SRV_PID}" 2>/dev/null || true
trap - EXIT

# 5) 解析 → CSV + summary
python3 "${REPO_ROOT}/submission/scripts/analyze_chunk_rtf.py" \
  "${RUN_DIR}/server.log" "${RUN_ID}" \
  --out "${OUT_DIR}" --binary-sha "${BIN_SHA}" --model-sha "${MODEL_SHA}" --server-pid "${SRV_PID}"
echo "PERF_DONE run=${RUN_ID} log=${RUN_DIR}/server.log"
