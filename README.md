# docs/specdecode-migration — llama / vLLM / DSpark 迁移研究分支

> **本分支导读**：投机解码（speculative decoding）迁移研究文档分支。
> 内容 = llama.cpp-omni 比赛经验 → vLLM-Omni 迁移，以及 DSpark（上游 DFlash 之上）→ llama.cpp-omni 的 backport 计划。
> 纯文档研究分支，无实验代码。

## 从这里开始（导读）

### DSpark 投机解码（llama.cpp-omni 侧 backport 计划）

| 想做什么 | 去看 |
|---|---|
| DSpark 集成计划 | [`docs/speculative/DSpark_LLAMA_CPP_OMNI_INTEGRATION_PLAN.md`](docs/speculative/DSpark_LLAMA_CPP_OMNI_INTEGRATION_PLAN.md) |
| 队友 draft 产物契约 | [`docs/speculative/DSpark_DRAFT_ARTIFACT_CONTRACT.md`](docs/speculative/DSpark_DRAFT_ARTIFACT_CONTRACT.md) |
| 全链路 speculative pipeline | [`docs/speculative/OMNI_SPECULATIVE_FULL_PIPELINE.md`](docs/speculative/OMNI_SPECULATIVE_FULL_PIPELINE.md) |
| DSpark 最终报告 | [`docs/speculative/DSPARK_FINAL_REPORT.md`](docs/speculative/DSPARK_FINAL_REPORT.md) |

### vLLM-Omni 迁移（llama 经验 → vLLM）

| 想做什么 | 去看 |
|---|---|
| **迁移文档集入口（30 秒 / 10 分钟阅读序）** | [`docs/vllm-migration/README.md`](docs/vllm-migration/README.md) |
| 12 条核心经验迁移 | [`docs/vllm-migration/LLAMA_TO_VLLM_EXPERIENCE_MIGRATION.md`](docs/vllm-migration/LLAMA_TO_VLLM_EXPERIENCE_MIGRATION.md) |
| 组件映射 + 源码导航 | [`docs/vllm-migration/LLAMA_VLLM_COMPONENT_MAPPING.md`](docs/vllm-migration/LLAMA_VLLM_COMPONENT_MAPPING.md) |
| vLLM 优化执行计划 V0–V12 | [`docs/vllm-migration/VLLM_OPTIMIZATION_EXECUTION_PLAN.md`](docs/vllm-migration/VLLM_OPTIMIZATION_EXECUTION_PLAN.md) |
| 风险与验证矩阵 | [`docs/vllm-migration/VLLM_RISK_AND_VALIDATION_MATRIX.md`](docs/vllm-migration/VLLM_RISK_AND_VALIDATION_MATRIX.md) |
| 队友交接包 | [`docs/vllm-migration/VLLM_TEAM_HANDOFF.md`](docs/vllm-migration/VLLM_TEAM_HANDOFF.md) |
| 原始证据附录 | [`docs/vllm-migration/LLAMA_RAW_EVIDENCE_APPENDIX.md`](docs/vllm-migration/LLAMA_RAW_EVIDENCE_APPENDIX.md) |
| 实验模板 | [`docs/vllm-migration/EXPERIMENT_TEMPLATES.md`](docs/vllm-migration/EXPERIMENT_TEMPLATES.md) |

### 跨框架迁移方法论

| 想做什么 | 去看 |
|---|---|
| llama→vLLM 优化点映射 | [`docs/migration/LLAMA_CPP_OMNI_TO_VLLM_OMNI_OPTIMIZATION_MAP.md`](docs/migration/LLAMA_CPP_OMNI_TO_VLLM_OMNI_OPTIMIZATION_MAP.md) |
| 跨框架性能方法论 | [`docs/migration/CROSS_FRAMEWORK_PERFORMANCE_METHODOLOGY.md`](docs/migration/CROSS_FRAMEWORK_PERFORMANCE_METHODOLOGY.md) |

## 三支分支导航（仓库最终生命周期）

| 分支 | 用途 | 状态 |
|---|---|---|
| `competition/final-ascend-track-a` | 赛道一最终提交 | 🔒 FREEZE |
| `feat/dspark-llama-port` | DSpark 注意力加速移植（赛道二） | 队友 draft 到位后继续 |
| `docs/specdecode-migration` | llama / vLLM / DSpark 迁移研究 | 文档研究（**本分支**） |

## 原始 README（只读备份）

- 本引擎原版 README（llama.cpp-omni 架构说明）→ [`README-llama-cpp-omni.md`](README-llama-cpp-omni.md)
- 上游 ggml llama.cpp README → [`README_llama.cpp.md`](README_llama.cpp.md)
