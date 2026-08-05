#!/usr/bin/env bash
# run_performance.sh — 逐 chunk RTF 采集（llama 子赛道核心指标）
#
# baseline 与 candidate 共用同一 runner：同一数据 manifest / 请求顺序 / seed / warmup /
# measured count / chunk parser / valid_audio 判定 / 统计脚本。仅 MODE 选择二进制配置。
# 输出隔离：${OUTPUT_ROOT}/<run_id>/<mode>/
# 每次保存 manifest.json：resolved config / 完整启动命令 / 完整 benchmark 命令 /
#   source commit / binary SHA / model SHA / data SHA / env vars / raw chunk CSV / summary JSON。
# 对称性：check_baseline_candidate_symmetry.py 比对两 MODE 的 dataset SHA / case count /
#   request IDs / sampling config / model / prompt / 统计代码 SHA，任一不一致退出非零。
#
# --dry-run：仅校验配置与资产 + 打印将执行命令（不起服务 / 不占 NPU / 不发请求 / 不落成绩）。
#   返回码：0=配置资产完整可执行 | 2=缺少资产 | 3=配置非法 | 4=baseline/candidate 不对称
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "${REPO_ROOT}/submission/config/server.env"
if [ -f /usr/local/Ascend/cann/set_env.sh ]; then
  # shellcheck disable=SC1091
  source /usr/local/Ascend/cann/set_env.sh
fi

# ---- 参数解析：MODE=baseline|candidate（env 或位置参数），--dry-run 标志 ----
DRY_RUN=0
MODE="${MODE:-candidate}"
for a in "$@"; do
  case "$a" in
    --dry-run|-n) DRY_RUN=1 ;;
    --mode=*) MODE="${a#--mode=}" ;;
    --) break ;;
    baseline|candidate) MODE="$a" ;;
    *) echo "[INVALID_CONFIG] 未知参数: ${a}（仅接受 baseline|candidate|--dry-run）" >&2; exit 3 ;;
  esac
done
case "${MODE}" in
  baseline|candidate) ;;
  *) echo "[INVALID_CONFIG] MODE=${MODE}（仅允许 baseline|candidate）" >&2; exit 3 ;;
esac

# ---- 运行配置（baseline/candidate 共用，仅二进制不同） ----
N="${N:-3}"                        # 测量请求数（内部规范 ≥30 有效 chunk）
WARMUP="${WARMUP:-0}"              # 预热请求数（不计入测量）
SEED="${SEED:-0}"                  # 0=字典序；>0=固定打乱
SAMPLE_RATE="${SAMPLE_RATE:-24000}"
RUN_ID="${RUN_ID:-run_$(date +%Y%m%d_%H%M%S)_perf}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${REPO_ROOT}/submission_runs}"
RUN_DIR="${RUN_DIR:-${OUTPUT_ROOT}/${RUN_ID}/${MODE}}"
OUT_DIR="${RUN_DIR}/out"
TEXT_DIR="${TEXT_DIR:-}"

# ---- 二进制选择：baseline 必须显式给出（无私有默认）；candidate 默认 build/bin ----
if [ "${MODE}" = "baseline" ]; then
  SERVER_BIN="${BASELINE_SERVER_BIN:-}"
  [ -n "${SERVER_BIN}" ] || { echo "[INVALID_CONFIG] MODE=baseline 需要 BASELINE_SERVER_BIN（官方 baseline 二进制路径）" >&2; exit 3; }
else
  SERVER_BIN="${CANDIDATE_SERVER_BIN:-${REPO_ROOT}/build/bin/llama-omni-server}"
fi

# ---- 资产检查 ----
MISSING=()
[ -f "${SERVER_BIN}" ]     || MISSING+=("server_bin=${SERVER_BIN}")
[ -n "${MODEL_PATH:-}" ]   || MISSING+=("MODEL_PATH 未设置（必须显式指定模型路径）")
[ -f "${MODEL_PATH:-}" ]   || MISSING+=("model=${MODEL_PATH:-<empty>}")
if [ -n "${TEXT_DIR:-}" ]; then
  [ -d "${TEXT_DIR}" ]     || MISSING+=("text_dir=${TEXT_DIR}")
fi
STATS_SHA="$(sha256sum "${REPO_ROOT}/submission/scripts/analyze_chunk_rtf.py" \
                       "${REPO_ROOT}/submission/scripts/run_chunk_rtf_client.py" \
                       "${REPO_ROOT}/submission/scripts/check_baseline_candidate_symmetry.py" \
             | sha256sum | cut -d' ' -f1)"
if [ "${#MISSING[@]}" -gt 0 ]; then
  for m in "${MISSING[@]}"; do echo "[MISSING_ASSET] ${m}" >&2; done
  exit 2
fi

# ---- 派生指纹 / 命令（dry-run 与真实运行共用，保证打印与执行一致） ----
BIN_SHA="$(sha256sum "${SERVER_BIN}" | cut -d' ' -f1)"
MODEL_SHA="$(sha256sum "${MODEL_PATH}" | cut -d' ' -f1)"
if [ -n "${TEXT_DIR}" ] && [ -d "${TEXT_DIR}" ]; then
  DATA_SHA="$(find "${TEXT_DIR}" -type f -name '*.txt' -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
else
  DATA_SHA="$(printf 'builtin-default-texts' | sha256sum | cut -d' ' -f1)"
fi
SOURCE_COMMIT="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo unknown)"

SERVER_CMD=(stdbuf -oL -eL "${SERVER_BIN}" -m "${MODEL_PATH}" -ngl "${NGL}" --device "${DEVICE}"
            -c "${CTX}" -b "${BATCH}" -ub "${UBATCH}" --split-mode "${SPLIT_MODE}" --port "${SERVER_PORT}")
BENCH_CMD=(python3 "${REPO_ROOT}/submission/scripts/run_chunk_rtf_client.py"
           --port "${SERVER_PORT}" --n "${N}" --warmup "${WARMUP}" --seed "${SEED}"
           --text-dir "${TEXT_DIR}" --texts-out "${RUN_DIR}/requests.txt")
ANALYZE_CMD=(python3 "${REPO_ROOT}/submission/scripts/analyze_chunk_rtf.py" "${RUN_DIR}/server.log" "${RUN_ID}"
             --out "${OUT_DIR}" --binary-sha "${BIN_SHA}" --model-sha "${MODEL_SHA}"
             --mode "${MODE}" --sample-rate "${SAMPLE_RATE}"
             --warmup "${WARMUP}" --wav-dir "${RUN_DIR}")

SYMMETRY_CMD=(python3 "${REPO_ROOT}/submission/scripts/check_baseline_candidate_symmetry.py"
              "${OUTPUT_ROOT}/${RUN_ID}")

# ---- 对称性预检辅助（dry-run 打印；真实运行在分析后调用） ----
sibling_mode() { [ "${MODE}" = "baseline" ] && echo candidate || echo baseline; }
SIBLING_DIR="${OUTPUT_ROOT}/${RUN_ID}/$(sibling_mode)"

# ================= DRY-RUN =================
if [ "${DRY_RUN}" = "1" ]; then
  echo "== DRY_RUN run_performance.sh (MODE=${MODE}) =="
  echo "  MODE            : ${MODE}"
  echo "  MODEL_PATH      : ${MODEL_PATH} (sha=${MODEL_SHA})"
  echo "  DATA            : ${TEXT_DIR:-builtin-default-texts} (data_sha=${DATA_SHA})"
  echo "  SERVER_BIN      : ${SERVER_BIN} (sha=${BIN_SHA})"
  echo "  SERVER_PORT     : ${SERVER_PORT}"
  echo "  RUN_DIR         : ${RUN_DIR}"
  echo "  OUT_DIR         : ${OUT_DIR}"
  echo "  N/WARMUP/SEED   : ${N}/${WARMUP}/${SEED}  sample_rate=${SAMPLE_RATE}"
  echo "  source_commit   : ${SOURCE_COMMIT}  candidate_source=${LLAMA_CANDIDATE_SOURCE_COMMIT}"
  echo "  stats_code_sha  : ${STATS_SHA}"
  echo "  server_cmd      : ${SERVER_CMD[*]}"
  echo "  benchmark_cmd   : ${BENCH_CMD[*]}"
  echo "  analyze_cmd     : ${ANALYZE_CMD[*]}"
  if [ -f "${SIBLING_DIR}/manifest.json" ]; then
    if "${SYMMETRY_CMD[@]}" >/dev/null 2>&1; then
      echo "  symmetry        : PASS（与 $(sibling_mode) manifest 一致）"
    else
      echo "  symmetry        : FAIL（与 $(sibling_mode) 不对称 → 退出 4）" >&2
      exit 4
    fi
  else
    echo "  symmetry        : SKIP（$(sibling_mode) 尚未运行，只有先跑对侧后才能做对称性检查）"
  fi
  echo "DRY_RUN_OK"
  exit 0
fi

# ================= 真实运行 =================
mkdir -p "${RUN_DIR}/kv_cache" "${OUT_DIR}"
export OMNI_KV_CACHE_PATH="${OMNI_KV_CACHE_PATH:-${RUN_DIR}/kv_cache}"
if ss -tlnp 2>/dev/null | grep -q ":${SERVER_PORT} "; then
  echo "[FAIL] 端口 ${SERVER_PORT} 已占用" >&2
  exit 1
fi

echo "== RUN_ID=${RUN_ID} MODE=${MODE} N=${N} WARMUP=${WARMUP} SEED=${SEED} port=${SERVER_PORT} =="

# 1) 启动服务（后台）
"${SERVER_CMD[@]}" > "${RUN_DIR}/server.log" 2>&1 &
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

# 3) 驱动 TTS 请求（warmup + measured）
"${BENCH_CMD[@]}" > "${RUN_DIR}/client.log" 2>&1 \
  || { echo "[FAIL] 客户端失败" >&2; tail -30 "${RUN_DIR}/client.log" >&2; exit 1; }

# 4) 停服（等 drain）
sleep 2
kill "${SRV_PID}" 2>/dev/null || true
wait "${SRV_PID}" 2>/dev/null || true
trap - EXIT

# 5) 解析 → CSV + summary（--server-pid 用实际 server PID 溯源）
"${ANALYZE_CMD[@]}" --server-pid "${SRV_PID}" > "${OUT_DIR}/analyze.stdout" 2>&1 \
  || { echo "[FAIL] 解析失败" >&2; tail -30 "${OUT_DIR}/analyze.stdout" >&2; exit 1; }

# 6) manifest.json（resolved config / 完整命令 / 指纹 / env）
SERVER_CMD_JSON="$(python3 -c "import json,sys;print(json.dumps(sys.argv[1:]))" "${SERVER_CMD[@]}")"
BENCH_CMD_JSON="$(python3 -c "import json,sys;print(json.dumps(sys.argv[1:]))" "${BENCH_CMD[@]}")"
ENV_JSON="$({ env | grep -E '^(OMNI_|ASCEND|GGML_|MODEL_PATH|TEXT_DIR|OUTPUT_ROOT)=' || true; } \
            | python3 -c "import sys,json;d={};[d.__setitem__(l.rstrip('\\n').split('=',1)[0],l.rstrip('\\n').split('=',1)[1]) for l in sys.stdin];print(json.dumps(d,sort_keys=True))")"
cat > "${RUN_DIR}/manifest.json" <<EOF
{
  "run_id": "${RUN_ID}",
  "mode": "${MODE}",
  "source_commit": "${SOURCE_COMMIT}",
  "candidate_source_commit": "${LLAMA_CANDIDATE_SOURCE_COMMIT}",
  "binary_sha": "${BIN_SHA}",
  "model_sha": "${MODEL_SHA}",
  "model_path": "${MODEL_PATH}",
  "data_sha": "${DATA_SHA}",
  "text_dir": "${TEXT_DIR:-builtin}",
  "stats_code_sha": "${STATS_SHA}",
  "n_measured": "${N}",
  "warmup": "${WARMUP}",
  "seed": "${SEED}",
  "sample_rate": "${SAMPLE_RATE}",
  "server_port": "${SERVER_PORT}",
  "server_bin": "${SERVER_BIN}",
  "server_cmd": ${SERVER_CMD_JSON},
  "benchmark_cmd": ${BENCH_CMD_JSON},
  "env": ${ENV_JSON},
  "outputs": {
    "raw_chunk_csv": "${OUT_DIR}/chunk_rtf_raw.csv",
    "summary_json": "${OUT_DIR}/chunk_rtf_summary.json",
    "requests_txt": "${RUN_DIR}/requests.txt",
    "server_log": "${RUN_DIR}/server.log"
  }
}
EOF
echo "manifest → ${RUN_DIR}/manifest.json"

# 7) 对称性检查（对侧已运行则比对；不一致退出 4）
if [ -f "${SIBLING_DIR}/manifest.json" ]; then
  if "${SYMMETRY_CMD[@]}"; then
    echo "SYMMETRY=PASS"
  else
    echo "[FAIL] baseline/candidate 不对称（见上方差异）" >&2
    exit 4
  fi
fi

echo "PERF_DONE mode=${MODE} run=${RUN_ID} dir=${RUN_DIR}"
