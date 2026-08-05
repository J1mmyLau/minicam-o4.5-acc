#!/usr/bin/env bash
# start_demo.sh — 启动 Demo（推理服务 + 官方 Demo 前端）
# 官方 Demo = OpenBMB/MiniCPM-o-Demo。前端仓库 clone 位置用 DEMO_DIR 配置。
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEMO_DIR="${DEMO_DIR:-/workspace/MiniCPM-o-Demo}"

# 1) 环境检查
bash "${REPO_ROOT}/submission/environment/env_check.sh"

# 2) 推理服务（后台）
bash "${REPO_ROOT}/submission/scripts/start_server.sh" &
sleep 1
# 等待 health
for i in $(seq 1 120); do
  bash "${REPO_ROOT}/submission/scripts/health_check.sh" >/dev/null 2>&1 && break
  [ "$i" = "120" ] && { echo "[FAIL] 服务未就绪" >&2; exit 1; }
  sleep 1
done
echo "== 推理服务就绪 =="

# 3) Demo 前端
if [ -d "${DEMO_DIR}" ]; then
  echo "== 启动官方 Demo 前端（${DEMO_DIR}）=="
  # 按官方 MiniCPM-o-Demo README 的启动方式接入
  echo "DEMO_FRONTEND_START: 参照官方 README 启动（接口连 ${REPO_ROOT}/submission/scripts/start_server.sh 启动的服务）"
else
  echo "[BLOCKED_BY_ASSET] 官方 Demo 目录不存在: ${DEMO_DIR}（git clone https://github.com/OpenBMB/MiniCPM-o-Demo）" >&2
  exit 2
fi
