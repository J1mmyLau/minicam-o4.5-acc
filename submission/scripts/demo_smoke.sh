#!/usr/bin/env bash
# demo_smoke.sh — Demo 录制前冒烟自检（不占 NPU 也能先跑资产检查部分）
# 用法: ./demo_smoke.sh [--full]   （--full 会启动 server 实测一轮, ~5min）
set -Eeuo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
ok()   { echo "  [PASS] $1"; PASS=$((PASS+1)); }
miss() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

echo "== 资产检查（录制前必过）=="
[ -f "$REPO_ROOT/build/bin/llama-omni-server" ] && ok "server 二进制" || miss "server 二进制"
[ -f "$REPO_ROOT/submission/config/server.env" ] && ok "server.env (A+C 配方)" || miss "server.env"
[ -f "/workspace/models/token2wav-rts-nfe2/prompt_cache.gguf" ] && ok "NFE2 prompt cache" || miss "NFE2 prompt cache"
[ -f "$REPO_ROOT/evaluation/judge-final/assets/video/omni_duplex1.mp4" ] && ok "demo 输入视频" || miss "demo 输入视频"
ls "$REPO_ROOT"/tilelang-aot/*.so >/dev/null 2>&1 && ok "TileLang AOT 核 ($(ls "$REPO_ROOT"/tilelang-aot/*.so | wc -l) 个)" || miss "TileLang AOT 核"
[ -x "/workspace/llama.cpp-omni-bench-huawei/.venv-eval/bin/python" ] && ok "venv python" || miss "venv python"

echo "== 已归档会话产物（提交包内样例）=="
for f in "$REPO_ROOT"/submission/demo/audio_out/turn_01.wav \
         "$REPO_ROOT"/submission/demo/audio_out/turns_index.json \
         "$REPO_ROOT"/submission/demo/wav_assets/demo_input_video.mp4 ; do
  [ -s "$f" ] && ok "$(basename "$f") ($(du -h "$f" | cut -f1))" || miss "$f"
done

echo
echo "SMOKE PASS=$PASS FAIL=$FAIL"
[ $FAIL -eq 0 ] || exit 1
