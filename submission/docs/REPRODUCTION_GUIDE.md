# 复现指南（提交物）

> 面向主办方的从零复现步骤。对应 `docs/competition-submission/REPRODUCTION_AUDIT.md`。

## 一键路径

```bash
git clone <repo> && cd llama.cpp-omni-bench-huawei
git checkout fd3dd36                              # fix/cann-fa-nan-ubatch16（冻结 commit，tag competition-final-20260814）
bash submission/environment/env_check.sh          # 环境/NPU/模型/端口
bash submission/scripts/build.sh                  # 构建（期望 SHA 见 VERSION_MANIFEST）
bash submission/scripts/start_server.sh           # 启动（冻结 env，Config D）
bash submission/scripts/health_check.sh           # 健康
bash submission/scripts/demo_smoke.sh             # 冒烟 D1-D12
bash submission/scripts/run_performance.sh        # 逐 chunk RTF
bash submission/scripts/run_daily_omni.sh         # Daily-Omni 准确率
bash submission/scripts/run_video_mme.sh          # VideoMME 准确率
bash submission/scripts/run_tts_seed.sh           # Seed-TTS WER/SIM
```

## 版本
见 `VERSION_MANIFEST.md`（source fd3dd36 / server 4694cb58… /
libomni 3f3e1e63… / model d1e69845…）。

## 复现校验点
- server 重建 SHA == `4694cb589b61fbc3d…`，libomni.so == `3f3e1e636f66e815…`（REPRODUCIBLE_BINARY=PASS）
- 结果 run_id / binary_sha / model_sha 齐全
- 无 /tmp 持久化依赖、无私有绝对路径唯一默认值
- `evaluation/` + 4 保护工具 byte-identical to `c9785cc`（0 行改动）
