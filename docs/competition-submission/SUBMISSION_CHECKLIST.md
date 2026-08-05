# Submission Checklist — llama.cpp-omni 子赛道

> 依据官方赛事规则整理。最终提交材料对照。
> 状态: `F6_OFFICIAL_SUBMISSION_PACKAGE = NOT_READY`

---

## 1. 完整代码与配置

| 提交项 | 路径 | 状态 |
|--------|------|------|
| 推理适配与性能优化代码 | `src/`, `tools/omni/`, `ggml/src/ggml-cann/` — 冻结于 bdd4550 | ✅ |
| llama.cpp-omni 配置文件 | `submission/config/server.env`, `submission/config/benchmark.yaml` | ✅ |
| 服务启动脚本 | `submission/scripts/start_server.sh`, `stop_server.sh` | ✅ |
| Benchmark 执行脚本 | `submission/scripts/run_daily_omni.sh`, `run_tts_seed.sh`, `run_video_mme.sh` | ✅ |
| Demo 启动脚本 | `submission/scripts/start_demo.sh`, `run_demo.sh`, `run_demo_gate.sh`, `demo_smoke.sh` | ✅ |
| 依赖与环境配置文件 | `submission/environment/requirements.txt`, `env_check.sh`, `system_info.txt` | ✅ |

---

## 2. Benchmark 评测结果

| Benchmark | 测试命令 | 参数配置 | 原始输出 | 结果汇总 | 状态 |
|-----------|---------|---------|---------|---------|------|
| Daily-Omni | `run_daily_omni.sh` | `benchmark.yaml` | `benchmark_results/candidate/daily_omni/` | — | `NOT_RUN` |
| TTS-Seed | `run_tts_seed.sh` | `benchmark.yaml` | `benchmark_results/candidate/tts_seed/` | — | `NOT_RUN` |
| Video-MME | `run_video_mme.sh` | `benchmark.yaml` | `benchmark_results/candidate/video_mme/` | — | `NOT_RUN` |

全部 `BLOCKED_BY_OFFICIAL_STARTER_KIT`。

---

## 3. 性能测试报告

| 报告项 | 路径 | 状态 |
|--------|------|------|
| 内部 RTF（历史参考） | `docs/F6_OPTIMIZATION_AND_RESULTS.md` | `INTERNAL_ONLY` |
| 内部 Request→W0 A/B | `docs/F6_PHASE2_STEP6_CANN_T2W_AB.md` | `HISTORICAL_INTERNAL_RESULT` |
| 官方 per-chunk RTF | — | `NOT_RUN` |
| 测试环境 | `submission/environment/system_info.txt` | ✅ |
| 测试数据 | 同官方统一数据 | `NOT_RUN` |
| 测试次数与统计方式 | 见方法论: `docs/F6_METHODOLOGY.md` | ✅ (内部) |
| 优化前后对比 | `docs/F6_PHASE2_STEP6_CANN_T2W_AB.md` | ✅ (内部) |
| 资源使用情况 | — | `NOT_MEASURED` |
| 异常情况说明 | `docs/F6_LIMITATIONS_AND_OFFICIAL_GATES.md` | ✅ |

---

## 4. 可运行 Demo

| 提交项 | 路径 | 状态 |
|--------|------|------|
| Demo 使用说明 | `docs/competition-submission/DEMO_USER_GUIDE.md` | ✅ |
| 启动与访问方式 | `docs/competition-submission/DEMO_USER_GUIDE.md` | ✅ |
| 核心交互流程 | `docs/competition-submission/DEMO_VALIDATION_PLAN.md` | ✅ |
| Demo Gate 检查表 | `submission/demo/DEMO_GATE_CHECKLIST.md` | ✅ |
| 演示视频 | `submission/demo/video/` | `NOT_RECORDED` |

---

## 5. 优化与复现说明

| 提交项 | 路径 | 状态 |
|--------|------|------|
| 原始性能瓶颈分析 | `docs/F6_OPTIMIZATION_AND_RESULTS.md` | ✅ |
| 采用的优化方法 | `docs/F6_OPTIMIZATION_AND_RESULTS.md`, `docs/F6_ARCHITECTURE.md` | ✅ |
| 各项优化带来的性能变化 | `docs/F6_OPTIMIZATION_AND_RESULTS.md` | ✅ |
| 效果保持情况 | T6 集成回归: `docs/f6-s13-closure/phase2/T6_INTEGRATED_REGRESSION_REPORT.md` | ✅ |
| 完整复现步骤 | `docs/F6_REPRODUCTION_GUIDE.md` | ✅ |
| 关键技术说明 | `docs/F6_ARCHITECTURE.md`, `docs/audit/CANN_CPU_NPU_PLACEMENT_AUDIT.md` | ✅ |

---

## 6. 提交材料覆盖度

| 类别 | 官方要求 | 已有 | 缺失 |
|------|---------|------|------|
| 代码与配置 | 6 项 | 6 | 0 |
| Benchmark 结果 | 3 × (命令+配置+raw+汇总) = 12 项 | 0 (脚本有) | 12 |
| 性能报告 | 8 项 | 4 (内部) | 4 (官方 RTF + 资源 + 数据 + 对比) |
| 可运行 Demo | 4 项 | 3 | 1 (视频) |
| 优化与复现 | 6 项 | 6 | 0 |
| **合计** | **36 项** | **19** | **17** |

缺失的 17 项全部因为官方 Starter Kit / 资产未到位。

---

## 状态

```
SUBMISSION_SCRIPTS_READY              = YES
SUBMISSION_DOCS_READY                 = YES
SUBMISSION_BENCHMARK_RESULTS_READY    = NO  (BLOCKED_BY_OFFICIAL_STARTER_KIT)
SUBMISSION_PERFORMANCE_OFFICIAL_READY = NO  (BLOCKED_BY_OFFICIAL_STARTER_KIT)
SUBMISSION_DEMO_VIDEO_READY           = NO  (BLOCKED_BY_OFFICIAL_STARTER_KIT)

F6_OFFICIAL_SUBMISSION_PACKAGE        = NOT_READY
```

**不得在官方资产到位前填写任何伪结果。所有 NOT_RUN = 诚实 NOT_RUN。**
