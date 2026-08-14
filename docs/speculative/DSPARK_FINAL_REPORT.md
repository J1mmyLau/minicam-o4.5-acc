# DSpark 研发启动 — 阶段收口报告

> 日期：2026-08-14 · 阶段：**架构审计 + 分支准备 + 文档 + 实验计划**（未写 decode 循环代码）
> 冻结候选：`competition-final-20260814` = `fd3dd36870f60829e47cafffacc7027cf8eb21d4`

---

## 1. 冻结身份（Freeze Competition Candidate）

```text
COMPETITION_FINAL_BRANCH = fix/cann-fa-nan-ubatch16
COMPETITION_FINAL_COMMIT  = fd3dd36870f60829e47cafffacc7027cf8eb21d4
COMPETITION_FINAL_TAG     = competition-final-20260814
SERVER_SHA256             = 4694cb589b61fbc3d9c26508dbfb044ae06f07395ca409659dbb0f066a28815f
LIBOMNI_SHA256            = 3f3e1e636f66e81501eeda9285e1228e14da542211292a67f8bae70fbdf822ec
OFFICIAL_ACCURACY         = Daily 79.43% / VideoMME 69.8% / Seed-TTS WER 1.422% SIM 0.969
OFFICIAL_RTF              = core.rtf_aggregate 1.09–1.17（parity baseline 1.087）
```

> 真正最终 commit **不是** `a77d6a8`。它是 `a77d6a8` + `trackA_fixes.patch`（已 applied）+ 本 session 的 RTF/LISTEN-wedge 修复 + stage_timing 发射，统一提交为 `fd3dd36`。

## 2. 分支 / Worktree 布局

```text
competition-final-20260814 (tag → fd3dd36)      ← 冻结，禁止 DSpark 开发
        ├── feat/dspark-llama-port (cc15dda)     ← 队友 DSpark 主分支
        │     └── exp/dspark-upstream-port / exp/dspark-cann /
        │         perf/dspark-acceptance / eval/dspark-official-ab
        └── docs/specdecode-migration (fd4d41a)  ← 文档分支（5 份迁移/规划文档）
```

## 3. 上游 DSpark 审计

```text
UPSTREAM_DSPARK_AVAILABLE = YES（ggml-org/llama.cpp）
DSPARK_UPSTREAM_PORT_GAP  = 两阶段 backport：
                            ① DFlash #22105 (d1b34251b, 14文件+712)  ← 本 fork 连 DFlash 都没有
                            ② DFlash K/V rotate #25823 (571d0d540)  ← DSpark 的祖先（DFlash 演进中途）
                            ③ DSpark #25173 (84075273c, 14文件+286)  ← 构建于 DFlash 之上
                            ancestry: 571d0d540 → +95 commits → 84075273c
                            预期 cherry-pick 冲突（drift +1938/−579）
```

- 本 fork 同步点 = llama.cpp `cb47092b0`（**2026-05-29**，#23842）。
- 本 fork 已有 `common/speculative`（SIMPLE/EAGLE3/MTP/ngram），**缺 DRAFT_DFLASH 与 DRAFT_DSPARK**。
- DSpark 不新增 arch（fold 进 DFlash）；markov 头按存在检测；conf head 参与推理（confidence-based prefix pruning，`conf_proj` 在 Markov head 存在时 REQUIRED）；无 confidence 截断时 greedy lossless。
- ⚠️ converter 仅支持 Qwen3；MiniCPM-o 4.5 非 Qwen3 → 需自写 converter 或队友 draft 训在 Qwen3。
- `server-context.cpp` 已接 `common_speculative`，接线缺口 = omni decode 主循环未走 speculative proposer。

## 4. Draft Artifact 契约

```text
TEAMMATE_DRAFT_COMPATIBILITY = NOT_AVAILABLE   # 队友 checkpoint 不在本机
GGUF_CONVERSION_REQUIRED     = LIKELY_YES       # llama.cpp 路径吃 GGUF
```

- Target 已核实：MiniCPM-o 4.5（vocab 151748 / hidden 4096 / 36L / 32h / 8kv / ffn 12288）。
- 解除阻塞的最小信息清单 + HF→GGUF 张量映射 + 数值校验 gate 已写入 `DSpark_DRAFT_ARTIFACT_CONTRACT.md`。

## 5. Speculative 适用性 + Amdahl

```text
MAIN_LLM_DSPARK_FEASIBLE = STRUCTURALLY_YES / AMDAHL_BOUNDED
TTS_DSPARK_FEASIBLE      = UNKNOWN / LIKELY_NO
CURRENT_DECODE_AMDAHL    = llm_decode 13.0%（core RTF 0.142/1.0904）
MAX_E2E_GAIN_IF_DECODE_2X = ~6.5%（现实 3–5%）
```

- 主 LLM decode 只占 13.0%；Talker(27.3%) + Token2Wav(21.9%) 才是大头，但非 DSpark 可加速形态。
- 一个 draft **不可能**同时加速主 LLM 和 Talker（不同 vocab/latent）。
- 历史 `F6_R9_DSPARK_FINAL_RECORD`（REJECTED_BY_BOTTLENECK）诚实携带进计划。

## 6. 文档产出

```text
VLLM_MIGRATION_DOC   = docs/migration/LLAMA_CPP_OMNI_TO_VLLM_OMNI_OPTIMIZATION_MAP.md
LLAMA_FULL_PIPELINE_DOC = docs/speculative/OMNI_SPECULATIVE_FULL_PIPELINE.md
+ DSpark_LLAMA_CPP_OMNI_INTEGRATION_PLAN.md / DSpark_DRAFT_ARTIFACT_CONTRACT.md
+ CROSS_FRAMEWORK_PERFORMANCE_METHODOLOGY.md / feat/dspark-llama-port/README-DSPARK.md
```

## 7. NEXT_IMPLEMENTATION_GATE

```text
NEXT_IMPLEMENTATION_GATE =
  1) TEAMMATE_DRAFT_TARGET_ARCH：确认 draft 训在哪个 target（MiniCPM-o vs Qwen3）
  2) CHECKPOINT_TENSOR_CONTRACT：markov_w1/w2 + conf_proj（缺 conf_proj 非完整 DSpark）
  3) MINICPMO_CONVERTER_FEASIBILITY（上游 Qwen3DSparkModel 仅 Qwen3）
  4) DFLASH_SUBSTRATE_BACKPORT（d1b34251b，确保含 571d0d540 K/V rotate 语义）
  5) DSPARK_DELTA（84075273c）
  6) LLAMA_CLI_STANDALONE（先 llama-cli/server 跑通，非 omni）
  7) CANN（算子/图兼容 + FA NaN 回归）
  8) OMNI_INTEGRATION（最后接线）
  9) ACCEPTANCE / AMDAHL 重测
```

## 8. 阶段遵守声明（Current Stage Restriction）

- ✅ 分支/worktree 准备、上游 DSpark 审计、draft 契约、架构图、转换计划、性能方法论、文档。
- ❌ 未 merge 到 competition final、未重写 Omni decode 循环、未改 evaluation 受保护文件、未假设 draft 兼容、未宣称无 A/B 的收益、未把量化当首选。
