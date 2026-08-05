#!/usr/bin/env bash
# stop_server.sh — 停止 llama-omni-server（幂等）
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "${REPO_ROOT}/submission/config/server.env"

pids="$(pgrep -f "llama-omni-server.*--port ${SERVER_PORT}" 2>/dev/null || true)"
if [ -n "${pids}" ]; then
  echo "== 停止 server pid(s): ${pids} =="
  echo "${pids}" | xargs -r kill 2>/dev/null || true
  sleep 2
  still="$(pgrep -f "llama-omni-server.*--port ${SERVER_PORT}" 2>/dev/null || true)"
  [ -n "${still}" ] && echo "${still}" | xargs -r kill -9 2>/dev/null || true
else
  echo "== 无运行中 server（端口 ${SERVER_PORT}）=="
fi
