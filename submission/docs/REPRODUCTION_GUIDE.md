# 复现指南（提交物）

> 面向主办方的从零复现步骤。对应 `docs/competition-submission/REPRODUCTION_AUDIT.md`。

## 一键路径

```bash
git clone <repo> && cd llama.cpp-omni-f6 && git checkout bdd4550
bash submission/environment/env_check.sh          # 环境/NPU/模型/端口
bash submission/scripts/build.sh                  # 构建（期望 SHA=db258375…）
bash submission/scripts/start_server.sh           # 启动（冻结 env）
bash submission/scripts/health_check.sh           # 健康
bash submission/scripts/demo_smoke.sh             # 冒烟 D1-D12
bash submission/scripts/run_performance.sh        # 逐 chunk RTF
bash submission/scripts/run_daily_omni.sh         # 官方脚本到达后
```

## 版本
见 `VERSION_MANIFEST.md`（source bdd4550 / server db258375… / libomni c4b16937… / model d1e69845…）。

## 复现校验点
- server 重建 SHA == `db258375…`（REPRODUCIBLE_BINARY=PASS）
- 结果 run_id / binary_sha / model_sha 齐全
- 无 /tmp 持久化依赖、无私有绝对路径唯一默认值
