#!/usr/bin/env bash
# run_demo.sh — 交互式双工 Demo（终端版）：视频/音频输入 → 实时流式语音回复
# 用法:
#   ./run_demo.sh                 # 用 judge-final 自带双工视频跑完整会话
#   ./run_demo.sh <video.mp4>     # 自定义视频
# 前置: submission/environment/env_check.sh 全 PASS
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VIDEO="${1:-$REPO_ROOT/evaluation/judge-final/assets/video/omni_duplex1.mp4}"
GPU="${GPU:-1}"
PORT="${PORT:-19060}"
OUT="${OUT:-$REPO_ROOT/submission/demo/session_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUT"

cd "$REPO_ROOT"
echo "============================================================"
echo " MiniCPM-o 4.5 全双工 Demo（llama.cpp-omni + Ascend 910C）"
echo " 候选: perf/tilelang-bridge  RTF 0.4829 (基线 1.087)"
echo "============================================================"
echo " 输入视频 : $VIDEO"
echo " NPU     : ASCEND_RT_VISIBLE_DEVICES=$GPU"
echo " 输出目录 : $OUT"
echo "============================================================"

# A+C 性能配方 + TileLang 核 + NFE2（全部 launch-only）
set -a
source "$REPO_ROOT/submission/config/server.env"
set +a
export OMNI_T2W_N_TIMESTEPS=2
export OMNI_T2W_PROMPT_CACHE=/workspace/models/token2wav-rts-nfe2/prompt_cache.gguf
# 固定采样种子（= 存档 4-run 的 seed 1001）：保证录制时确定性地出现 SPEAK 语音轮
export OMNI_SAMPLER_SEED="${OMNI_SAMPLER_SEED:-1001}"

# CANN 环境：无条件 source（幂等）。终端里 ASCEND_OPP_PATH 可能未设置、
# 未 export、或指向失效路径 —— 任一情况首个 aclnn 算子初始化都报 EZ1002 直接崩。
CANN_ENV="${CANN_ENV:-/usr/local/Ascend/ascend-toolkit/set_env.sh}"
if [ -f "$CANN_ENV" ]; then
  set +u; source "$CANN_ENV"; set -u
else
  echo "[ERROR] 找不到 $CANN_ENV — CANN 环境无法加载，中止" >&2
  exit 1
fi
# 显式 export 兜底（防 set_env.sh 变量被外层同名未导出值覆盖）
export ASCEND_OPP_PATH ASCEND_AICPU_PATH ASCEND_HOME_PATH ASCEND_TOOLKIT_HOME

# 硬校验：OPP 路径必须存在且含算子目录（built-in 或 builtin），否则启动后必崩
if [ -z "${ASCEND_OPP_PATH:-}" ] || [ ! -d "${ASCEND_OPP_PATH}" ] || { [ ! -d "${ASCEND_OPP_PATH}/built-in" ] && [ ! -d "${ASCEND_OPP_PATH}/builtin" ]; }; then
  echo "[ERROR] ASCEND_OPP_PATH 无效: '${ASCEND_OPP_PATH:-<空>}' (需含 builtin/)" >&2
  echo "        请先: source /usr/local/Ascend/ascend-toolkit/set_env.sh" >&2
  exit 1
fi
echo "[env ] CANN 就绪  OPP=$ASCEND_OPP_PATH"

echo "[1/3] 启动双工会话（server 冷启动 + 模型加载 ~60-120s）…"
/workspace/llama.cpp-omni-bench-huawei/.venv-eval/bin/python \
  "$REPO_ROOT/evaluation/judge-final/run_judge_direct.py" \
  --model /workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf \
  --llamacpp-root "$REPO_ROOT" \
  --video "$VIDEO" \
  --max-duration "${MAX_DURATION:-120}" \
  --gpu "$GPU" \
  --runs-dir "$OUT/runs" \
  --verbose 2>&1 | tee "$OUT/demo.log"

echo
echo "[2/3] 会话结束。生成物:"
find "$OUT" -name "*.wav" -o -name "*.json" 2>/dev/null | head -20 || true

echo
echo "[3/3] Demo 完成。"
echo "  - 模型语音输出（整轮拼接）: judge-final/sessions/<stamp>/speak_turns/turn_0N.wav"
echo "  - 逐段计时报告            : judge-final/sessions/<stamp>/eval_e2e_report.json"
echo "  - 完整日志               : $OUT/demo.log"
