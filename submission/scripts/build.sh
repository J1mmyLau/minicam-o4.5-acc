#!/usr/bin/env bash
# build.sh — 冻结候选源码构建（复刻 REPRODUCIBLE_BINARY=PASS 的目标构建）
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

# CANN 环境
if [ -f /usr/local/Ascend/cann/set_env.sh ]; then
  # shellcheck disable=SC1091
  source /usr/local/Ascend/cann/set_env.sh
else
  echo "[FAIL] CANN set_env.sh 不存在" >&2
  exit 1
fi

JOBS="${JOBS:-$(nproc)}"
BUILD_DIR="${BUILD_DIR:-build}"
TARGET="${TARGET:-llama-omni-server}"

echo "== configure (${BUILD_DIR}/) =="
cmake -B "${BUILD_DIR}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_CANN=ON

echo "== build target ${TARGET} (-j${JOBS}) =="
cmake --build "${BUILD_DIR}" -j "${JOBS}" --target "${TARGET}"

echo "== SHA（期望 server=db258375… libomni=c4b16937…） =="
[ -f "${BUILD_DIR}/bin/llama-omni-server" ] && sha256sum "${BUILD_DIR}/bin/llama-omni-server"
[ -f "${BUILD_DIR}/bin/libomni.so" ]         && sha256sum "${BUILD_DIR}/bin/libomni.so"
echo "BUILD_DONE"
