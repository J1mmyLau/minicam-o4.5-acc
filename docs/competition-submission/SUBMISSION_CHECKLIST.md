# Submission Checklist — llama.cpp-omni 子赛道

> 依据官方赛事规则整理。最终提交材料对照。
> 状态: `F6_OFFICIAL_SUBMISSION_PACKAGE = NOT_READY`

---

## 状态约定

每项使用两层标记:

- **READY / NOT_READY**: 工程准备度（脚本、文档、工具链在自己侧是否就绪）
- **PASS / NOT_RUN / BLOCKED**: 实际执行状态（是否在目标环境运行过并拿到结果）

`READY` ≠ `PASS`。脚本写好了但没跑过 → `READY + NOT_RUN`。
`NOT_READY` = 该项本质上还无法开始（缺上游资产/缺定义/缺环境）。

---

## 1. 完整代码与配置

| 提交项 | 路径 | 工程准备 | 执行状态 |
|--------|------|---------|---------|
| 推理适配与性能优化代码 | `src/`, `tools/omni/`, `ggml/src/ggml-cann/` — 冻结于 bdd4550 | `READY` | `INTERNAL_PASS` |
| llama.cpp-omni 配置文件 | `submission/config/server.env`, `submission/config/benchmark.yaml` | `READY` | `INTERNAL_PASS` |
| 服务启动脚本 | `submission/scripts/start_server.sh`, `stop_server.sh` | `READY` | `INTERNAL_PASS` |
| Benchmark 执行脚本 | `submission/scripts/run_daily_omni.sh`, `run_tts_seed.sh`, `run_video_mme.sh` | `READY` | `OFFICIAL_NOT_RUN` |
| Demo 启动脚本 | `submission/scripts/start_demo.sh`, `run_demo.sh`, `run_demo_gate.sh`, `demo_smoke.sh`, `fetch_demo.sh` | `READY` | `OFFICIAL_NOT_RUN` |
| 依赖与环境配置文件 | `submission/environment/requirements.txt`, `env_check.sh`, `system_info.txt` | `READY` | `INTERNAL_PASS` |

---

## 2. Benchmark 评测结果

| Benchmark | 测试命令 | 参数配置 | 原始输出 | 结果汇总 | 工程准备 | 执行状态 |
|-----------|---------|---------|---------|---------|---------|---------|
| Daily-Omni | `run_daily_omni.sh` | `benchmark.yaml` | `benchmark_results/candidate/daily_omni/` | — | `READY` | `NOT_RUN` |
| TTS-Seed | `run_tts_seed.sh` | `benchmark.yaml` | `benchmark_results/candidate/tts_seed/` | — | `READY` | `NOT_RUN` |
| Video-MME | `run_video_mme.sh` | `benchmark.yaml` | `benchmark_results/candidate/video_mme/` | — | `READY` | `NOT_RUN` |

全部 `BLOCKED_BY_OFFICIAL_STARTER_KIT`。

---

## 3. 性能测试报告

| 报告项 | 路径 | 工程准备 | 执行状态 |
|--------|------|---------|---------|
| 内部 RTF（历史参考） | `docs/F6_OPTIMIZATION_AND_RESULTS.md` | `READY` | `INTERNAL_ONLY` |
| 内部 Request→W0 A/B | `docs/F6_PHASE2_STEP6_CANN_T2W_AB.md` | `READY` | `HISTORICAL_INTERNAL_RESULT` |
| 官方 SPEAK→WAV RTF (baseline=1.087) | — | `READY` (script); parser 需 SPEAK 分类升级 | `NOT_RUN` |
| 测试环境 | `submission/environment/system_info.txt` | `READY` | `INTERNAL_PASS` |
| 测试数据 | 同官方统一数据 | `PENDING` | `NOT_RUN` |
| 测试次数与统计方式 | 见方法论: `docs/F6_METHODOLOGY.md` | `READY` | `INTERNAL_PASS` |
| 优化前后对比 | `docs/F6_PHASE2_STEP6_CANN_T2W_AB.md` | `READY` | `INTERNAL_PASS` |
| 资源使用情况 | — | `NOT_READY` | `NOT_MEASURED` |
| 异常情况说明 | `docs/F6_LIMITATIONS_AND_OFFICIAL_GATES.md` | `READY` | `INTERNAL_PASS` |

---

## 4. 可运行 Demo

| 提交项 | 路径 | 工程准备 | 执行状态 |
|--------|------|---------|---------|
| Demo 前端代码 | `third_party/MiniCPM-o-Demo/` @ ba7fa9c (422 files) | `READY` | `CLONED` |
| Demo 获取脚本 | `submission/scripts/fetch_demo.sh` | `READY` | `VERIFIED` (HTTPS shallow clone) |
| Demo 使用说明 | `docs/competition-submission/DEMO_USER_GUIDE.md` | `READY` | `INTERNAL_PASS` |
| 启动与访问方式 | `docs/competition-submission/DEMO_USER_GUIDE.md` | `READY` | `INTERNAL_PASS` |
| 核心交互流程 | `docs/competition-submission/DEMO_VALIDATION_PLAN.md` | `READY` | `INTERNAL_PASS` |
| Demo Gate 检查表 | `submission/demo/DEMO_GATE_CHECKLIST.md` | `READY` | `DEMO_INTEGRATION_NOT_VERIFIED` |
| Demo 集成验证 | D1-D12 端到端 | `READY` (scripts) | `NOT_RUN` (缺推理环境/模型) |
| 演示视频 | `submission/demo/video/` | `NOT_READY` | `NOT_RECORDED` |

---

## 5. 优化与复现说明

| 提交项 | 路径 | 工程准备 | 执行状态 |
|--------|------|---------|---------|
| 原始性能瓶颈分析 | `docs/F6_OPTIMIZATION_AND_RESULTS.md` | `READY` | `INTERNAL_PASS` |
| 采用的优化方法 | `docs/F6_OPTIMIZATION_AND_RESULTS.md`, `docs/F6_ARCHITECTURE.md` | `READY` | `INTERNAL_PASS` |
| 各项优化带来的性能变化 | `docs/F6_OPTIMIZATION_AND_RESULTS.md` | `READY` | `INTERNAL_PASS` |
| 效果保持情况 | T6 集成回归: `docs/f6-s13-closure/phase2/T6_INTEGRATED_REGRESSION_REPORT.md` | `READY` | `INTERNAL_PASS` |
| 完整复现步骤 | `docs/F6_REPRODUCTION_GUIDE.md` | `READY` | `INTERNAL_PASS` |
| 关键技术说明 | `docs/F6_ARCHITECTURE.md`, `docs/audit/CANN_CPU_NPU_PLACEMENT_AUDIT.md` | `READY` | `INTERNAL_PASS` |

---

## 6. 提交材料覆盖度

| 类别 | 官方要求 | READY (工程) | NOT_RUN/BLOCKED | 缺失 |
|------|---------|-------------|-----------------|------|
| 代码与配置 | 6 项 | 6 | 0 | 0 |
| Benchmark 结果 | 3 × (命令+配置+raw+汇总) = 12 项 | 3 (scripts) | 9 (no harness) | 0 |
| 性能报告 | 8 项 | 6 | 1 (资源) | 1 (官方对比) |
| 可运行 Demo | 5 项 | 4 | 1 (integration) | 0 |
| 优化与复现 | 6 项 | 6 | 0 | 0 |

Demo 前端已 clone 并 pin 在 ba7fa9c，`fetch_demo.sh` 提供可复现获取方式。
缺失项全部因为官方 Starter Kit / 推理环境 / 模型权重不在当前机器上。

---

## 状态

```
SUBMISSION_SCRIPTS_READY              = YES
SUBMISSION_DOCS_READY                 = YES
DEMO_ASSETS_CLONED                    = YES (ba7fa9c, 422 files)
DEMO_INTEGRATION_SCRIPTS              = READY
DEMO_INTERNAL_INTEGRATION             = NOT_VERIFIED
SUBMISSION_BENCHMARK_RESULTS_READY    = NO  (BLOCKED_BY_OFFICIAL_STARTER_KIT)
SUBMISSION_PERFORMANCE_OFFICIAL_READY = NO  (BLOCKED_BY_OFFICIAL_STARTER_KIT)
SUBMISSION_DEMO_VIDEO_READY           = NO  (BLOCKED_BY_INFRA_AND_STARTER_KIT)

F6_OFFICIAL_SUBMISSION_PACKAGE        = NOT_READY
```

**不得在官方资产到位前填写任何伪结果。所有 NOT_RUN = 诚实 NOT_RUN。**
