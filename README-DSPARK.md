# feat/dspark-llama-port

> DSpark 投机解码研发主分支（从比赛 frozen candidate 派生）。

## BASE
- 分支：`feat/dspark-llama-port`
- 派生自 tag：`competition-final-20260814`（commit `fd3dd36870f60829e47cafffacc7027cf8eb21d4`）
- 上游 fork：`tc-mb/llama.cpp-omni`（本 fork 同步点 = llama.cpp `cb47092b0`, 2026-06-01）

## OWNER
- 队友（DSpark 训练产物提供）+ Claude（上游 backport + Omni 接线）

## GOAL
把上游 llama.cpp 已有的 DSpark（`--spec-type draft-dspark`，markov head + confidence head）backport 到 llama.cpp-omni，并接线到 `llama-omni-server` 的主 LLM decode 段。

**非目标**：不从头实现 DSpark；不迁移 vLLM；不加速 Talker/Token2Wav（那两段不是 DSpark 能碰的）。

## CURRENT_STATUS
- **PLANNING**。仅架构审计 + 分支准备 + 文档，未写任何 decode 循环代码。
- 队友 draft checkpoint **尚未到位**（`TEAMMATE_DRAFT_COMPATIBILITY = NOT_AVAILABLE`）。
- 上游 DSpark commit 集合**尚未定位**（本 fork 无 upstream remote，需先 `git remote add upstream`）。

## NEXT_GATE（解除阻塞顺序）
1. 队友 draft checkpoint + 结构 config 到位。
2. `git remote add upstream ggerganov/llama.cpp` + 定位 DSpark 引入 commit 集合。
3. backport 最小文件集到 `exp/dspark-upstream-port`，在 `llama-cli`/`llama-server` 跑通 `draft-dspark` 独立正确性。
4. 接线 `llama-omni-server`（`omni.cpp` decode 主循环 → `common_speculative`）。
5. Amdahl 重测（若主 LLM decode 占比仍 < 20%，期望压低到 ~3–5%）。

## DO_NOT_MERGE_TO_COMPETITION_FINAL
**绝对禁止** merge 回 `competition-final-20260814` / `fix/cann-fa-nan-ubatch16`。
比赛 frozen candidate 是 `fd3dd36`（tag `competition-final-20260814`），DSpark 研发只在以下分支进行：

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
