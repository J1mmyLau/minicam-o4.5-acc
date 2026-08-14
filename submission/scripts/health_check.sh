#!/usr/bin/env bash
# health_check.sh — 服务健康检查
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "${REPO_ROOT}/submission/config/server.env"

if curl -sf "http://127.0.0.1:${SERVER_PORT}/health" -m 10; then
  echo ""
  echo "HEALTH_OK (port ${SERVER_PORT})"
else
  echo "HEALTH_FAIL (port ${SERVER_PORT})" >&2
  exit 1
fi
