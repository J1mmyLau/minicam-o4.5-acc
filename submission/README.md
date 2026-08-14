# submission/ — 赛道一 llama.cpp-omni 最终提交包

> 本目录为**比赛最终提交包**（代码/配置/脚本/Benchmark 结果/性能/ Demo/文档）。
> 候选冻结口径见 `VERSION_MANIFEST.md`。当前状态：`FINAL_INTERNAL=PASS`、`COMPETITION_COMPLETE=NOT_CLAIMED`。

## 目录

```
submission/
├── README.md                 ← 本文件（入口）
├── VERSION_MANIFEST.md       ← commit/SHA 一一对应（溯源唯一权威）
├── environment/              ← env_check.sh / requirements.txt / system_info.txt
├── config/                   ← server.env（冻结启动 env）/ benchmark.yaml
├── scripts/                  ← 全部执行脚本（set -Eeuo pipefail）
├── benchmark_results/
│   ├── baseline/             ← 官方基线原始结果
│   └── candidate/            ← 优化候选原始结果
├── performance/              ← chunk_rtf_raw.csv + chunk_rtf_summary.json + PERFORMANCE_REPORT.md
├── demo/                     ← DEMO_GUIDE.md + video_manifest.md + 视频
└── docs/                     ← OPTIMIZATION_REPORT / REPRODUCTION_GUIDE / KNOWN_LIMITATIONS / CHANGELOG
```

## 快速上手

```bash
# 1. 环境检查
bash submission/environment/env_check.sh

# 2. 构建（可选：已提供冻结二进制）
bash submission/scripts/build.sh

# 3. 启动服务
bash submission/scripts/start_server.sh

# 4. 健康检查
bash submission/scripts/health_check.sh

# 5. 冒烟
bash submission/scripts/demo_smoke.sh --smoke

# 6. 性能（逐 chunk RTF）
bash submission/scripts/run_performance.sh
```

## 状态

| 块 | 状态 | 说明 |
|---|---|---|
| 代码与配置 | ✅ 冻结 | source `bdd4550` / server `db258375…` / libomni `c4b16937…` |
| 三项 Benchmark | 🔴 NOT_RUN | 官方 Starter Kit 未到（BLOCKED_BY_ASSET），脚本骨架已建 |
| 性能报告 | 🟡 管线就绪 | 日志已含逐 chunk RTF，官方计时口径待定 |
| Demo | 🟡 服务侧 PASS | 官方 Demo 前端接入待做 |
| 复现 | 🟡 构建侧 PASS | 官方环境复现待做 |

> 详细状态见 `docs/competition-submission/OFFICIAL_GATE_STATUS.md`。
