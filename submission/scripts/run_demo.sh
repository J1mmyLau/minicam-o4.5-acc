#!/usr/bin/env bash
# run_demo.sh — 完整 Demo 演示驱动（录像辅助）
# 按 DEMO_VIDEO_SCRIPT.md 分段执行并记录。录像需人工窗口操作。
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "== Demo 演示流程（对照 docs/competition-submission/DEMO_VIDEO_SCRIPT.md）=="
echo "1. 启动服务    → bash submission/scripts/start_server.sh"
echo "2. 冒烟 D1-D12 → bash submission/scripts/demo_smoke.sh"
echo "3. 各模态交互  → 浏览器操作（纯文本/单图/单音频/视频视听/多轮/TTS 流式）"
echo "4. 长稳        → ≥10 min 连续交互"
echo "5. 断连恢复    → 中断 → 新会话"
echo "6. 收尾        → npu-smi + 日志无错误 + commit/SHA 复显"
echo ""
echo "录像产出放 submission/demo/，登记到 submission/demo/video_manifest.md"
echo "RUN_DEMO_PENDING（需人工+录像）"
