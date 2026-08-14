# feat/dspark-llama-port

> DSpark 投机解码研发主分支（从比赛 frozen candidate 派生）。

## BASE
- 分支：`feat/dspark-llama-port`
- 派生自 tag：`competition-final-20260814`（commit `fd3dd36870f60829e47cafffacc7027cf8eb21d4`）
- 上游 fork：`tc-mb/llama.cpp-omni`（本 fork 同步点 = llama.cpp `cb47092b0`, 2026-05-29, #23842）
- DSpark/DFlash 上游：`ggml-org/llama.cpp`

## OWNER
- 队友（DSpark 训练产物提供）+ Claude（上游 backport + Omni 接线）

## GOAL
把上游 llama.cpp 已有的 DSpark（`--spec-type draft-dspark`，markov head + confidence head）backport 到 llama.cpp-omni，并接线到 `llama-omni-server` 的主 LLM decode 段。

**非目标**：不从头实现 DSpark；不迁移 vLLM；不加速 Talker/Token2Wav（那两段不是 DSpark 能碰的）。

## CURRENT_STATUS
- **PLANNING**。仅架构审计 + 分支准备 + 文档，未写任何 decode 循环代码。
- Amdahl：主 LLM decode 仅 13.0%（Talker 27.3% + Token2Wav 21.9%），decode 2× 增益封顶 ~6.5%（现实 3–5%）→ 本项目是**研发/迁移项目**，非比赛急救优化。

## UPSTREAM_DFLASH / DSPARK_DEPENDENCIES
两阶段 backport（非「只加一个 enum」），`git remote add upstream https://github.com/ggml-org/llama.cpp.git` 已加：

| 阶段 | commit | PR | 说明 |
|---|---|---|---|
| ① DFlash 前置 | `d1b34251b` | #22105 | backbone，**本 fork 无**（14 文件 +712/−9） |
| ② K/V rotate | `571d0d540` | #25823 | DSpark 的**祖先**（DFlash 演进中途），非事后补丁 |
| ③ DSpark 目标 | `84075273c` | #25173 | 构建于 DFlash 之上（14 文件 +286/−33） |

- ancestry：`571d0d540` → +95 commits → `84075273c`。依赖 = DFlash substrate → K/V rotate 语义 → DFlash 演进 → DSpark。
- drift 实测：`cb47092b0..d1b34251b` = +1938/−579（8 个 speculative 文件），cherry-pick **必然冲突**。
- DSpark 不新增 `LLM_ARCH_DSPARK`；draft 转 DFlash GGUF，由 Markov head 张量存在识别，`block_size` 复用 `dflash.block_size`。
- **Required tensors**：`markov_w1` + `markov_w2` + `conf_proj`（Markov head 存在时 REQUIRED）+ `dflash.block_size`（metadata）。
- `conf_proj` 在最终 commit **参与推理**（confidence-based prefix pruning，threshold fold 进 `p_min`）。
- ⚠️ converter 仅 `Qwen3DSparkModel`（Qwen3-only）；MiniCPM-o 4.5 是 `minicpmo` → 需自写 converter。

## TEAMMATE_DRAFT_STATUS
- `TEAMMATE_DRAFT_COMPATIBILITY = NOT_AVAILABLE`（队友 checkpoint 不在本机，已全盘搜索无 DSpark/draft 产物）。
- 阻塞解除需队友提供：draft checkpoint/config、训练挂载的 target arch（minicpmo vs qwen3）、hidden/vocab/block_size/markov_rank、safetensors 键名、固定输入 golden 输出。
- 契约详情见 `docs/speculative/DSpark_DRAFT_ARTIFACT_CONTRACT.md`。

## NEXT_GATE（解除阻塞顺序）
1. **TEAMMATE_DRAFT_TARGET_ARCH** —— draft 训在哪个 target（MiniCPM-o vs Qwen3）。
2. **CHECKPOINT_TENSOR_CONTRACT** —— markov_w1/w2 + conf_proj + block_size。
3. **MINICPMO_CONVERTER_FEASIBILITY** —— MiniCPM-o → DFlash GGUF converter。
4. **DFLASH_SUBSTRATE_BACKPORT** —— `d1b34251b`，确保含 `571d0d540` K/V rotate 语义。
5. **DSPARK_DELTA** —— `84075273c`。
6. **LLAMA_CLI_STANDALONE** —— 在 `llama-cli`/`llama-server`（非 omni）先跑通 `draft-dspark`。
7. **CANN** —— 算子/图兼容 + FA NaN 回归。
8. **OMNI_INTEGRATION** —— 最后接线 `llama-omni-server`。
9. **ACCEPTANCE / AMDAHL** —— acceptance A/B + E2E 重测。

## DO_NOT_MERGE_TO_COMPETITION_FINAL
**绝对禁止** merge 回 `competition/final-ascend-track-a`（最终交付分支）/ `competition-final-20260814`（= `fd3dd36`，冻结 runtime）/ `fix/cann-fa-nan-ubatch16`。

比赛 frozen runtime 是 `fd3dd36`，DSpark 研发只在以下分支进行：

```
feat/dspark-llama-port
├── exp/dspark-upstream-port     上游 DSpark 代码 backport
├── exp/dspark-cann              CANN backend / 算子 / 图兼容
├── perf/dspark-acceptance       gamma / 置信度 / acceptance 调参
└── eval/dspark-official-ab      correctness / accuracy / RTF / E2E A/B
```

## 参考文档（docs/specdecode-migration 分支）
- `docs/speculative/DSpark_LLAMA_CPP_OMNI_INTEGRATION_PLAN.md`
- `docs/speculative/DSpark_DRAFT_ARTIFACT_CONTRACT.md`
- `docs/speculative/OMNI_SPECULATIVE_FULL_PIPELINE.md`
- `docs/migration/LLAMA_CPP_OMNI_TO_VLLM_OMNI_OPTIMIZATION_MAP.md`
- `docs/migration/CROSS_FRAMEWORK_PERFORMANCE_METHODOLOGY.md`
