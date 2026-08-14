#!/usr/bin/env bash
# env_check.sh — 比赛环境检查（依赖 / NPU / 端口 / 模型 / 二进制）
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${REPO_ROOT}/submission/config/server.env" 2>/dev/null || true

FAIL=0
say()  { printf '\033[1;36m%s\033[0m\n' "$*"; }
ok()   { printf '  [OK]   %s\n' "$*"; }
warn() { printf '  [WARN] %s\n' "$*"; }
fail() { printf '  [FAIL] %s\n' "$*"; FAIL=1; }

say "== 1. CANN 环境 =="
if [ -f /usr/local/Ascend/cann/set_env.sh ]; then
  # shellcheck disable=SC1091
  source /usr/local/Ascend/cann/set_env.sh
  [ -n "${ASCEND_HOME_PATH:-}" ] && ok "ASCEND_HOME_PATH=${ASCEND_HOME_PATH}" || fail "ASCEND_HOME_PATH 未设置"
  [ -n "${ASCEND_OPP_PATH:-}" ]  && ok "ASCEND_OPP_PATH=${ASCEND_OPP_PATH}"    || fail "ASCEND_OPP_PATH 未设置"
else
  fail "未找到 /usr/local/Ascend/cann/set_env.sh（CANN 9.1.0-beta.1 需安装）"
fi

say "== 2. NPU 设备 =="
if command -v npu-smi >/dev/null 2>&1; then
  npu-smi info | head -15 || fail "npu-smi 执行失败"
else
  fail "npu-smi 不可用"
fi

say "== 3. 模型文件 =="
if [ -n "${MODEL_PATH:-}" ] && [ -f "${MODEL_PATH}" ]; then
  ok "MODEL_PATH=${MODEL_PATH}"
  echo "     model SHA256: $(sha256sum "${MODEL_PATH}" | cut -d' ' -f1)"
elif [ -n "${MODEL_PATH:-}" ]; then
  fail "MODEL_PATH=${MODEL_PATH} 不存在（通过 MODEL_PATH 显式指定）"
else
  fail "MODEL_PATH 未设置（必须显式指定模型路径；无私有默认值）"
fi

say "== 4. 冻结二进制 =="
SERVER_BIN="${SERVER_BIN:-${REPO_ROOT}/build/bin/llama-omni-server}"
LIBOMNI="${LIBOMNI:-${REPO_ROOT}/build/bin/libomni.so}"
if [ -f "${SERVER_BIN}" ]; then
  got="$(sha256sum "${SERVER_BIN}" | cut -c1-8)"
  exp="4694cb58"
  [ "${got}" = "${exp}" ] && ok "server ${got}…（= 冻结 4694cb58…）" || warn "server ${got}…（期望 ${exp}…，非冻结二进制）"
else
  fail "server 二进制不存在: ${SERVER_BIN}（先 build.sh）"
fi
[ -f "${LIBOMNI}" ] && ok "libomni 存在" || fail "libomni.so 不存在"

say "== 5. 端口占用 =="
PORT="${SERVER_PORT:-18093}"
if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then
  fail "端口 ${PORT} 已被占用"
else
  ok "端口 ${PORT} 空闲"
fi

say "== 6. 运行中 server =="
if pgrep -f llama-omni-server >/dev/null 2>&1; then
  warn "已有 llama-omni-server 进程在运行（可能干扰评测，建议 stop_server.sh）"
else
  ok "无运行中 server"
fi

say ""
if [ "${FAIL}" = "0" ]; then
  printf '\033[1;32mENV_CHECK=PASS\033[0m\n'
else
  printf '\033[1;31mENV_CHECK=FAIL\033[0m\n'
  exit 1
fi
