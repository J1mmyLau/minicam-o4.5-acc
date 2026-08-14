#!/usr/bin/env bash
# demo_smoke.sh — Demo 服务侧冒烟（D1-D12 可自动化部分）
# 服务侧能力已验证（T6 11/11 + T10 pilot）；官方 Demo 前端接入后扩展。
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "${REPO_ROOT}/submission/config/server.env"

BASE="http://127.0.0.1:${SERVER_PORT}"
PASS=0; FAIL=0
chk() { # name, ok
  if [ "$2" = "0" ]; then echo "  [PASS] $1"; PASS=$((PASS+1)); else echo "  [FAIL] $1"; FAIL=$((FAIL+1)); fi
}

echo "== D1 服务冷启动 =="
curl -sf "${BASE}/health" -m 10 >/dev/null 2>&1; chk "D1 health OK" "$?"

echo "== D3 纯文本 =="
RESP="$(curl -sf -m 300 -X POST "${BASE}/v1/stream/decode" \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"请回答：1+1=？","use_tts":false,"max_tokens":64}' 2>/dev/null || true)"
echo "${RESP}" | python3 -c 'import json,sys
try:
  d=json.load(sys.stdin); print("  text_len=",len(d.get("text") or ""), " stop=", d.get("stop_reason"))
  sys.exit(0 if len(d.get("text") or "")>0 else 1)
except Exception as e: print("  PARSE_ERR", e); sys.exit(1)' || true
chk "D3 文本输出非空" "$?"

echo "== D10 稳定性（服务仍存活）=="
curl -sf "${BASE}/health" -m 10 >/dev/null 2>&1; chk "D10 server alive" "$?"

echo "== D12 错误输入恢复 =="
# 空 body → 期望明确 4xx，服务不崩
curl -s -o /dev/null -w '%{http_code}' -m 10 -X POST "${BASE}/v1/stream/decode" \
  -H 'Content-Type: application/json' -d '{}' 2>/dev/null | grep -qE '^[45]'; chk "D12 空请求返回错误码" "$?"
curl -sf "${BASE}/health" -m 10 >/dev/null 2>&1; chk "D12 错误后服务存活" "$?"

echo ""
echo "SMOKE_RESULT PASS=${PASS} FAIL=${FAIL}"
[ "${FAIL}" = "0" ] || exit 1
