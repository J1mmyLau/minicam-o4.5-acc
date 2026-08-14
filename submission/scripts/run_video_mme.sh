#!/usr/bin/env bash
# run_video_mme.sh — Video-MME 官方 Benchmark 执行入口
# MODE=baseline|candidate 同一 OFFICIAL_SCRIPT 同跑（同脚本同子集同分母）。
# 输出隔离：${OUTPUT_ROOT}/<run_id>/<mode>/（RUN_ID 在 baseline/candidate 两次运行时保持一致）
# --dry-run：仅校验配置与资产 + 打印将执行命令（不起服务 / 不占 NPU / 不发请求 / 不落成绩）。
#   返回码：0=配置资产完整可执行 | 2=缺少官方资产或 Harness | 3=配置非法 | 4=baseline/candidate 不对称
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "${REPO_ROOT}/submission/config/server.env"

DRY_RUN=0
MODE="${MODE:-candidate}"
for a in "$@"; do
  case "$a" in
    --dry-run|-n) DRY_RUN=1 ;;
    --mode=*) MODE="${a#--mode=}" ;;
    baseline|candidate) MODE="$a" ;;
    *) echo "[INVALID_CONFIG] 未知参数: ${a}（仅接受 baseline|candidate|--dry-run）" >&2; exit 3 ;;
  esac
done
case "${MODE}" in
  baseline|candidate) ;;
  *) echo "[INVALID_CONFIG] MODE=${MODE}（仅允许 baseline|candidate）" >&2; exit 3 ;;
esac

DATA="${DATA:-${DATA_ROOT}/Video-MME}"
RUN_ID="${RUN_ID:-run_$(date +%Y%m%d_%H%M%S)_video_mme}"
OUT="${OUT:-${OUTPUT_ROOT}/${RUN_ID}/${MODE}}"
OFFICIAL_SCRIPT="${OFFICIAL_SCRIPT:-}"

# ---- 资产检查 ----
MISSING=()
[ -d "${DATA}" ]         || MISSING+=("data_dir=${DATA}")
[ -n "${MODEL_PATH:-}" ] || MISSING+=("MODEL_PATH 未设置（必须显式指定模型路径）")
[ -f "${MODEL_PATH:-}" ] || MISSING+=("model=${MODEL_PATH:-<empty>}")
HARNESS_MISSING=0
if [ -z "${OFFICIAL_SCRIPT}" ]; then
  HARNESS_MISSING=1
elif [ ! -f "${OFFICIAL_SCRIPT}" ]; then
  MISSING+=("OFFICIAL_SCRIPT=${OFFICIAL_SCRIPT} 不存在")
  HARNESS_MISSING=1
fi

sibling_mode() { [ "${MODE}" = "baseline" ] && echo candidate || echo baseline; }
SIB_DIR="${OUTPUT_ROOT}/${RUN_ID}/$(sibling_mode)"
symmetry() { python3 "${REPO_ROOT}/submission/scripts/check_baseline_candidate_symmetry.py" "${OUTPUT_ROOT}/${RUN_ID}"; }

# ================= DRY-RUN =================
if [ "${DRY_RUN}" = "1" ]; then
  echo "== DRY_RUN run_video_mme.sh (MODE=${MODE}) =="
  echo "  MODE            : ${MODE}"
  echo "  DATA            : ${DATA}"
  echo "  MODEL_PATH      : ${MODEL_PATH:-<unset>}"
  echo "  OFFICIAL_SCRIPT : ${OFFICIAL_SCRIPT:-<unset>}"
  echo "  SERVER_PORT     : ${SERVER_PORT}"
  echo "  OUT             : ${OUT}"
  echo "  server_cmd      : RUN_DIR=${OUT}/run bash ${REPO_ROOT}/submission/scripts/start_server.sh"
  echo "  benchmark_cmd   : python3 ${OFFICIAL_SCRIPT:-<official-harness>} --data ${DATA} --out ${OUT}（以官方 Harness 为准）"
  if [ "${HARNESS_MISSING}" = "1" ] || [ "${#MISSING[@]}" -gt 0 ]; then
    echo "  missing_official_assets : YES（官方 starter kit 未到 → 退出 2）"
    for m in "${MISSING[@]:-}"; do [ -n "${m}" ] && echo "  [MISSING_ASSET] ${m}"; done
    exit 2
  fi
  if [ -f "${SIB_DIR}/manifest.json" ]; then
    if symmetry >/dev/null 2>&1; then
      echo "  symmetry        : PASS（与 $(sibling_mode) manifest 一致）"
    else
      echo "  symmetry        : FAIL（与 $(sibling_mode) 不对称 → 退出 4）" >&2
      exit 4
    fi
  else
    echo "  symmetry        : SKIP（$(sibling_mode) 尚未运行；同 RUN_ID 跑完对侧后可做对称性检查）"
  fi
  echo "DRY_RUN_OK"
  exit 0
fi

# ================= 真实运行 =================
if [ "${HARNESS_MISSING}" = "1" ]; then
  cat >&2 <<'EOF'
[BLOCKED_BY_OFFICIAL_STARTER_KIT]
  Video-MME 数据在，但官方子集/视频解码/抽帧策略/答案解析/分母未定。
  官方到达后确认：短视频/长视频/有音频/无音频/多轮/输入上限分桶。RUN_ID 两 MODE 保持一致：
    RUN_ID=<id> OFFICIAL_SCRIPT=/path/to/official.py bash submission/scripts/run_video_mme.sh baseline
    RUN_ID=<id> OFFICIAL_SCRIPT=/path/to/official.py bash submission/scripts/run_video_mme.sh candidate
  输出须含：video_mme_{baseline,candidate}_raw.json + comparison.json + VIDEO_MME_REPORT.md
  先 --dry-run 预检（退出码 0 后再正式跑）。
EOF
  exit 2
fi
if [ "${#MISSING[@]}" -gt 0 ]; then
  for m in "${MISSING[@]}"; do echo "[MISSING_ASSET] ${m}" >&2; done
  exit 2
fi

mkdir -p "${OUT}"
echo "== run_video_mme [${MODE}] @ ${DATA} =="
# python3 "${OFFICIAL_SCRIPT}" --data "${DATA}" --out "${OUT}" ...
echo "OFFICIAL_RUN_PENDING"
