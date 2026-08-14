# feat/dspark-llama-port — DSpark 投机解码研发分支

> **本分支导读**：把上游 llama.cpp 的 DSpark 投机解码（`--spec-type draft-dspark`，markov head + confidence head）
> backport 到 llama.cpp-omni 的研发分支。**非比赛急救优化**（decode 只占 E2E ~13%，增益封顶 ~6.5%）。
> 当前状态 **PLANNING**，未写 decode 循环代码。

## 从这里开始（导读）

| 想做什么 | 去看 |
|---|---|
| **完整入口**（BASE/OWNER/GOAL/NEXT_GATE/项目结构/参考文档） | [`README-DSPARK.md`](README-DSPARK.md) |
| 上游 backport 两阶段 + 依赖 | `README-DSPARK.md` §UPSTREAM_DFLASH |
| 队友 draft 契约（阻塞解除） | [`docs/speculative/DSpark_DRAFT_ARTIFACT_CONTRACT.md`](docs/speculative/DSpark_DRAFT_ARTIFACT_CONTRACT.md)（在迁移分支） |
| DSpark 集成计划 | [`docs/speculative/DSpark_LLAMA_CPP_OMNI_INTEGRATION_PLAN.md`](docs/speculative/DSpark_LLAMA_CPP_OMNI_INTEGRATION_PLAN.md)（在迁移分支） |

## 三支分支导航（仓库最终生命周期）

| 分支 | 用途 | 状态 |
|---|---|---|
| `competition/final-ascend-track-a` | 赛道一最终提交 | 🔒 FREEZE |
| `feat/dspark-llama-port` | DSpark 注意力加速移植（赛道二） | 队友 draft 到位后继续（**本分支**） |
| `docs/specdecode-migration` | llama / vLLM / DSpark 迁移研究 | 文档研究 |

## 原始 README（只读备份）

- 本引擎原版 README（llama.cpp-omni 架构说明）→ [`README-llama-cpp-omni.md`](README-llama-cpp-omni.md)
- 上游 ggml llama.cpp README → [`README_llama.cpp.md`](README_llama.cpp.md)
