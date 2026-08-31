#!/usr/bin/env bash
# env_check.sh — 提交环境自检（硬件/CANN/模型/数据集/二进制 SHA）
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0

ok()   { echo "[OK]   $1"; PASS=$((PASS+1)); }
miss() { echo "[MISS] $1"; FAIL=$((FAIL+1)); }

echo "== NPU =="
if command -v npu-smi >/dev/null 2>&1; then
  npu-smi info -l 2>/dev/null | head -5 && ok "npu-smi"
else
  miss "npu-smi"
fi

echo "== CANN =="
if [ -f /usr/local/Ascend/cann/set_env.sh ]; then
  ok "CANN set_env.sh"
else
  miss "CANN set_env.sh"
fi

echo "== 模型 =="
for f in \
  /workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf \
  /workspace/models/token2wav-rts-nfe2/prompt_cache.gguf ; do
  [ -f "$f" ] && ok "$f" || miss "$f"
done

echo "== 数据集（bench-huawei appendix，见 config-local.env ASSETS_DIR）=="
for d in \
  /workspace/llama.cpp-omni-bench-huawei/evaluation/appendix/videomme \
  /workspace/llama.cpp-omni-bench-huawei/evaluation/appendix/daily-omni \
  /workspace/llama.cpp-omni-bench-huawei/evaluation/appendix/seedtts_testset_zh/zh \
  "$REPO_ROOT/evaluation/judge-final/assets/video/omni_duplex1.mp4" ; do
  [ -e "$d" ] && ok "$d" || miss "$d"
done

echo "== 候选二进制（对照 VERSION_MANIFEST）=="
for b in build/bin/llama-omni-server build/bin/libomni.so build/bin/llama-omni-eval-cli \
         build/bin/llama-omni-eval-daily-cli build/bin/llama-omni-tts-eval; do
  if [ -f "$REPO_ROOT/$b" ]; then ok "$b  $(sha256sum "$REPO_ROOT/$b" | cut -c1-16)…"; else miss "$b"; fi
done

echo "== TileLang AOT 核 =="
if ls "$REPO_ROOT"/build/bin/tilelang-aot/*.so >/dev/null 2>&1 || \
   ls "$REPO_ROOT"/tilelang-aot/*.so >/dev/null 2>&1; then
  ok "tilelang-aot .so 存在"
else
  miss "tilelang-aot .so（server 启动时按 OMNI_TL_* 加载）"
fi

echo
echo "PASS=$PASS MISS=$FAIL"
[ $FAIL -eq 0 ]
