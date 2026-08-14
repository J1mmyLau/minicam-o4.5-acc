#!/usr/bin/env bash
# start_demo.sh — 启动 Demo（推理服务 + 官方 Demo 前端）
# 官方 Demo = OpenBMB/MiniCPM-o-Demo，commit ba7fa9c。
# 若 DEMO_DIR 不存在，先运行 fetch_demo.sh 获取前端。
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "${REPO_ROOT}/submission/config/server.env"
# DEMO_DIR 来自 server.env（默认 ${REPO_ROOT}/third_party/MiniCPM-o-Demo）

DEMO_COMMIT="ba7fa9cc6ad63c894f1bd5e5afac28466953519d"

# 1) 前端获取（如需）
if [ ! -d "${DEMO_DIR}/.git" ]; then
  echo "== Demo 前端未找到，运行 fetch_demo.sh =="
  bash "${REPO_ROOT}/submission/scripts/fetch_demo.sh"
fi

# 验证 commit
ACTUAL="$(cd "${DEMO_DIR}" && git rev-parse HEAD 2>/dev/null || echo 'MISSING')"
if [ "${ACTUAL}" != "${DEMO_COMMIT}" ]; then
  echo "[FAIL] Demo commit 不匹配: expected ${DEMO_COMMIT:0:7}, got ${ACTUAL:0:7}" >&2
  echo "  修复: rm -rf ${DEMO_DIR} && bash submission/scripts/fetch_demo.sh" >&2
  exit 2
fi
echo "== Demo 前端 OK (${ACTUAL:0:7}) =="

# 2) 环境检查
bash "${REPO_ROOT}/submission/environment/env_check.sh"

# 3) 推理服务（后台）
echo "== 启动推理服务 =="
bash "${REPO_ROOT}/submission/scripts/start_server.sh" &
SERVER_PID=$!
sleep 1

# 等待 health
for i in $(seq 1 120); do
  if curl -sf "http://127.0.0.1:${SERVER_PORT}/health" -m 5 >/dev/null 2>&1; then
    echo "== 推理服务就绪 (port ${SERVER_PORT}) =="
    break
  fi
  if [ "$i" = "120" ]; then
    kill "${SERVER_PID}" 2>/dev/null || true
    echo "[FAIL] 服务未在 120s 内就绪" >&2
    exit 1
  fi
  sleep 1
done

# 4) Demo 前端
echo "== Demo 前端已就绪 =="
echo ""
echo "  DEMO_DIR          = ${DEMO_DIR}"
echo "  DEMO_COMMIT       = ${DEMO_COMMIT:0:7}"
echo "  SERVER_PORT       = ${SERVER_PORT}"
echo "  SERVER_PID        = ${SERVER_PID}"
echo ""
echo "  Demo 前端技术栈（来自 ${DEMO_DIR}）："
echo "    - Python gateway (FastAPI + uvicorn): gateway.py"
echo "    - Node.js frontend: frontend/"
echo "    - Worker: worker.py"
echo ""
echo "  启动前端（参考官方 README）："
echo "    cd ${DEMO_DIR}"
echo "    # 安装依赖"
echo "    pip install -r requirements.txt       # Python 后端"
echo "    cd frontend && npm install && cd ..   # Node.js 前端"
echo "    # 启动（需配置 server endpoint 指向 localhost:${SERVER_PORT}）"
echo "    cp config.example.json config.json    # 编辑 llm_server URL"
echo "    bash install.sh                       # 官方安装脚本"
echo ""
echo "  详细说明: ${DEMO_DIR}/README.md"
echo "  Demo Gate 检查表: submission/demo/DEMO_GATE_CHECKLIST.md"
echo ""
echo "SERVER_PID=${SERVER_PID}"
