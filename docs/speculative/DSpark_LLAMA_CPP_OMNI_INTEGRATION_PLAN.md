# DSpark → llama.cpp-omni 集成计划

> 分支：`feat/dspark-llama-port`（从 `competition-final-20260814` 派生）
> 状态：**PLANNING / ARCHITECTURE AUDIT**（未写任何 decode 循环代码）
> 原则：**Do Not Implement DSpark From Scratch** — 先 backport 上游 llama.cpp 已有的 DSpark，再做 Omni 接线。

---

## 1. 结论速览

| 判定 | 值 |
|---|---|
| `UPSTREAM_DSPARK_AVAILABLE` | **YES**（上游 llama.cpp 已有 `--spec-type draft-dspark` + markov/confidence head） |
| 本 fork DSpark | **NO**（`common/speculative` 只有 `DRAFT_SIMPLE / EAGLE3 / MTP / NGRAM_*`） |
| 本 fork 上游同步点 | llama.cpp `cb47092b0`（**2026-05-29**，`server: bump timeout #23842`） |
| `DSPARK_UPSTREAM_PORT_GAP` | **两阶段 backport**：先 DFlash（#22105，本 fork 无），再 DSpark（#25173，构建于 DFlash 之上）。K/V rotate（#25823，`571d0d540`）是 DSpark 的**祖先 commit**（DFlash 演进中途），非 DSpark 之后的补丁 —— 非「只加一个 enum」 |
| `MAIN_LLM_DSPARK_FEASIBLE` | **STRUCTURALLY_YES / AMDAHL_BOUNDED**（见 §4） |
| `TTS_DSPARK_FEASIBLE` | **UNKNOWN / LIKELY_NO**（Talker 输出 speech token，与主 LLM 不同 latent） |
| `GGUF_CONVERSION_REQUIRED` | **LIKELY_YES**（llama.cpp 路径吃 GGUF；除非直接 backport HF 加载器） |

---

## 2. Upstream 移植策略（First Principle）

```
UPSTREAM LLAMA DSPARK（上游 commit 含 dspark_markov_w1/w2 + dspark_conf_proj + dflash.block_size）
        ↓  git log/diff 定位 DSpark 引入的 commit 集合
        ↓  逐个 backport 最小文件集到 feat/dspark-llama-port
        ↓  在 llama.cpp-omni 的 decode 生命周期里接线
```

**明确禁止**：逐行翻译 SGLang 的 DSpark 实现。上游 llama.cpp 的 `common/speculative` 已经是成熟的 speculative 运行时，DSpark 只是往里面加一个 **draft 类型 + 模型加载器 + 头张量**。

### 2.0 上游 commit 集合（已定位，2026-08-14，`git remote add upstream https://github.com/ggml-org/llama.cpp.git`）

> **关键修正**：DSpark **不是**独立的新 arch，而是**构建在 DFlash 之上**。本 fork（同步点 `cb47092b0`）**连 DFlash 都没有** —— 所以 backport 是**两阶段**，不是「只加一个 enum」。

| 阶段 | commit | PR | 日期 | 规模 | 说明 |
|---|---|---|---|---|---|
| 0. fork 同步点 | `cb47092b0` | #23842 | 2026-05-29 | — | 本 fork 现状 |
| 1. **DFlash（前置）** | `d1b34251b` | #22105 | 2026-06-28 | 14 文件 +712/−9 | DSpark 的 backbone，**本 fork 无** |
| 2. DFlash p-min | `152d337fa` | #25246 | — | — | `spec-draft-p-min` in DFlash |
| 3. DFlash K/V rotate | `571d0d540` | #25823 | 2026-07-18 | — | 注入 KV 旋转，正确性必需 |
| 4. **DSpark** | `84075273c` | #25173 | 2026-07-28 | 14 文件 +286/−33 | 目标 commit（parent=`6ba5ef247`） |

> **ancestry 核对（2026-08-14）**：`571d0d540` 已是 `84075273c` 的**祖先**（`571d0d540` → +95 commits → `84075273c`）。
> 依赖模型应为「DFlash substrate → K/V injection rotate 语义 → 后续 DFlash 演进 → DSpark」，
> **不是**「DFlash → DSpark → K/V rotate」顺序。backport 时确保移植进来的 DFlash substrate 已含 `571d` 语义，
> **不要**移完 DSpark 后再机械 cherry-pick `571d`（会与已演进的 `dflash.cpp` / KV cache 接口重复冲突）。

**上游架构事实（来自 DSpark commit message）**：
- DSpark **不新增 `LLM_ARCH_DSPARK`**（review 时已删）：draft 转成 DFlash GGUF，markov 头张量（`markov_w1/w2`）按「存在即检测」（同 eagle3 d2t），`block_size` 复用既有 `dflash.block_size` key。
- `llama_model_dspark : llama_model_dflash`，复用 DFlash 图 + target 特征提取 + KV 注入 + verify/accept；仅 override `draft()`。
- `conf_proj`（confidence head）在最终 commit `84075273c` **参与推理**：`draft()` 读取 confidence，低于 `p_min` 时对 draft block 做**基于置信度的前缀截断**（threshold 已 fold 进 `p_min`）；Markov head 存在时 `conf_proj` 为 **REQUIRED**。（早期 PR 版本才是「加载但未使用」，已过时。）
- 语义 = anchor-first block + semi-autoregressive 前 token 条件 logit bias；无 confidence 截断时 **greedy 保持 lossless**。
- **converter 仅支持 Qwen3**（`Qwen3DSparkModel`）。⚠️ **MiniCPM-o 4.5 非 Qwen3** —— 队友 draft 若训在 MiniCPM-o hidden state 上，需自写 converter；若训在 Qwen3 上，则与 target 不匹配。这是比「checkpoint 未到位」更深的兼容性问题。

**backport 难度（实测 drift）**：`cb47092b0..d1b34251b`（约 1 个月上游 drift）在 8 个 speculative 相关文件上 = **+1938/−579**，仅 `common/speculative.cpp` 就 **~1443 行变更**。→ DFlash/DSpark cherry-pick **必然冲突**，需按 commit 顺序 rebase，不是干净 pick。

### 需要 backport 的最小文件集（已从上游 diff 精确定位）

| 区域 | 实际文件（来自上游 diff） | 内容 |
|---|---|---|
| 类型枚举 + draft 参数 | `common/common.h` | `COMMON_SPECULATIVE_TYPE_DRAFT_DFLASH` + `DRAFT_DSPARK`（枚举 + draft params） |
| draft 运行时 | `common/speculative.cpp` | DFlash 实现 + DSpark impl（override `draft()`，anchor-first block + markov bias） |
| 模型 arch | `src/llama-arch.{h,cpp}`、`src/models/models.h`、`src/models/dflash.cpp` | **DFlash 是新 arch**（dspark 不新增，fold 进 dflash） |
| 模型加载 / 图 | `src/llama-model.{h,cpp}`、`src/llama-context.cpp`、`src/llama-graph.cpp` | 张量加载 + encoder/decoder 图 + KV 注入 |
| GGUF 元数据 | `gguf-py/gguf/constants.py`、`gguf-py/gguf/tensor_mapping.py` | `dflash.block_size` + markov/conf 张量 key |
| GGUF 转换 | `conversion/qwen.py`、`conversion/__init__.py` | `Qwen3DSparkModel` converter（**Qwen3-only**） |
| CLI/server | `tools/server/server-schema.cpp` | `--spec-type draft-dspark` 入参接线 |

### 本 fork 已有的基础设施（可直接复用）

- `common/speculative.{h,cpp}`（59 KB，含 `common_speculative` 结构 + accept/reject + draft forward）。
- `tools/server/server-context.cpp` 已接 `common_speculative * spec`、`can_speculate()`、`n_draft_total/accepted`。
- `llama-omni-server` 的 decode 走 `omni.cpp` → `llama_decode` → sampling，speculative 需要插在这条链上（见 §3）。

---

## 3. DSpark 进入 Omni 的位置（integration gap）

### 3.1 现状：llama-omni-server 的 decode 链

```
llama-omni-server
  → omni.cpp (omni_duplex_decode / stream_decode)
    → llama_decode(target)          # 主 LLM 前向，KV 写 target context
    → sampling (greedy/nucleus)     # 每步取 1 token
    → duplex LISTEN/SPEAK 状态机
```

### 3.2 现状：llama-server 的 speculative 链（上游，本 fork 已有 common 层）

```
llama-server
  → common_speculative (proposer)
    → draft forward (draft model 或 n-gram)
    → target batched verification
    → accept/reject
    → commit target KV
```

### 3.3 集成缺口（精确）

`llama-omni-server` 的 decode **没有经过** `common_speculative` 的 proposer 循环。也就是说：

> 因为 `llama-server` 支持 `--spec-type draft-dspark`，就假设 `llama-omni-server` 自动支持 —— **错误**。

需要补的接线（不重写，只接）：

1. 在 omni decode 主循环里，把「单 token 采样」替换为「`common_speculative` 提议 → 校验 → 提交」。
2. duplex LISTEN/SPEAK 状态机在 speculative 下必须感知「本步提交了几个 token」（否则 chunk 边界/TTS 派发错位）。
3. TTS/Talker 的 `push_tokens_window` 与 speculative 提交的 token 流要对齐（Talker 自己也是 autoregressive，见 §4.3）。

---

## 4. Amdahl Gate（先于任何实现）

### 4.1 当前最终候选的 stage 占比（官方 RTF core.stage_rtf，实测）

| Stage | core RTF | 占比 | DSpark 可加速? |
|---|---|---|---|
| encode | 0.189 | 17.3% | NO |
| llm_prefill | 0.2236 | 20.5% | NO（prefill 是并行前向） |
| **llm_decode** | **0.142** | **13.0%** | **YES** |
| tts (Talker) | 0.2974 | 27.3% | MAYBE（见 §4.3） |
| token2wav | 0.2384 | 21.9% | NO |
| **Σ** | **1.0904** | 100% | |

### 4.2 E2E 增益上限（硬上界）

```
MAX_E2E_GAIN_IF_MAIN_DECODE_2X ≈ llm_decode_share / 2 = 13.0% / 2 = 6.5%
```

再扣掉 **draft 前向成本 + 校验成本 + scheduler/KV 开销**，现实增益 ~**3–5%**，且只作用于 **decode 密集** 的场景（长文本 SPEAK turn）。对于第一音频时延（D0→D2 ~72ms，prefill 主导），DSpark **几乎无收益**。

### 4.3 历史否决记录（必须诚实携带）

`docs/tracking/F6_R9_DSPARK_FINAL_RECORD.md`（2026-07-31）已按当时瓶颈证据判定 `DSPARK_FEASIBILITY = REJECTED_BY_CURRENT_BOTTLENECK_EVIDENCE`：

| 重评条件 | 阈值 | 当时值 |
|---|---|---|
| decode compute 占 first-audio 路径 | > 40% | ~13.7% |
| speak 前 decode steps p50 | ≥ 3 | ~5（边际） |
| oracle speculative 上界 | ≥ 15% | 未测 |
| verify 路径可测 | feasible | 未接入 |

**结论**：DSpark 不是当前瓶颈的答案。队友已训好的 draft 仍值得接，但期望值必须设为「**在 decode 密集的长文本 turn 上验证小增益**」，而不是「全局加速」。

---

## 5. CANN 专用集成审计（模板）

DSpark draft 图在 Ascend 上的算子清单（逐算子填表，`CPU_FALLBACK_COUNT = 0` 是硬门槛）：

| GGML OP | CANN lowering | dtype | shape | CPU fallback? | kernel | 时延 |
|---|---|---|---|---|---|---|
| MUL_MAT (markov W1) | aclnnMm | F16 | [rank, hidden] | ? | — | — |
| MUL_MAT (markov W2) | aclnnMm | F16 | [vocab, rank] | ? | — | — |
| MUL_MAT (conf proj) | aclnnMm | F16 | [1, hidden] | ? | — | — |
| ROW_MAX / SOFTMAX (sampling) | — | — | — | — | — | — |
| target verify batch (MUL_MAT) | aclnnMm | F16 | [γ, hidden] | — | — | — |
| KV append | scatter/update | — | — | — | — | — |

**已知 CANN 坑（本项目血泪教训，必须前置）**：
- `aclnnMm` 在特定 shape/上下文下产 NaN（`OMNI_CANN_FA_MAX_UBATCH=16` 是 workaround，见 `docs/F6_MUL_MAT_NODE27_ROOT_CAUSE` / `f6-fa-nan-final-verdict`）。DSpark 的 draft 前向与 verify batch 会引入**新的 MUL_MAT shape**，必须纳入同一 NaN 回归。
- FusedInferAttention 在 Q≥435 时 NaN，verify batch 的 Q=γ 较小，但 draft backbone 若复用 target FA 需复测。

### Draft 内存预算

```
TARGET_HBM / DRAFT_HBM / TARGET_KV / DRAFT_KV / VERIFY_WORKSPACE / TOTAL_HBM
```

**禁止** draft context 盲目继承 target 的巨大 context（draft 是小模型，只保存自己 γ 步的 KV）。

---

## 6. Lossless 正确性 Gate（先当正确性特性，不当速度特性）

greedy（`temperature=0, top_k=1`）下要求：

```
TARGET_ONLY  ==  DSPARK  →  TOKEN_IDS_IDENTICAL
```

跑：text / audio / 1-frame / multi-frame / full duplex / TTS / RTS + **此前的 FA NaN 回归用例**。记录 NaN / Inf / token collapse / KV corruption / session contamination。

> 上游近期有「draft speculation 在量化 target 上发散」的报告。**首轮集成目标保持 F16**（当前参赛候选即 F16），量化 target 后置。

---

## 7. Acceptance / 性能可观测性

```
DRAFT_TOKENS_PROPOSED / DRAFT_TOKENS_ACCEPTED
ACCEPTANCE_RATE / ACCEPTED_LENGTH_MEAN / P50 / P90
DRAFT_FORWARD_MS / TARGET_VERIFY_MS
TOKENS_PER_TARGET_FORWARD
MAIN_DECODE_MS / TTS_DECODE_MS
TPOT / ITL / SPEAK_TO_WAV_RTF
```

**注意**：高 acceptance ≠ E2E 加速。主方程：

```
Spec gain ≈ saved_sequential_target_forwards − draft_forward_cost − verify_cost − scheduler/KV_overhead
```

---

## 8. 参数 Sweep（正确性通过后）

```
n_max (gamma)  = 2 / 3 / 4 / 5 / 7
confidence threshold / verification length / draft device / draft NGL layers
concurrency = C1 / C2 / C4 / C8
```

低 QPS 下 speculative 降时延，高并发下可能损吞吐 —— 必须多并发点测。

---

## 9. 实验分支布局（不 merge 到比赛 final）

```
feat/dspark-llama-port
├── exp/dspark-upstream-port     上游 DSpark 代码 backport
├── exp/dspark-cann              CANN backend / 算子 / 图兼容
├── perf/dspark-acceptance       gamma / 置信度 / acceptance 调参
└── eval/dspark-official-ab      correctness / accuracy / RTF / E2E A/B
```

---

## 10. 下一步实现 Gate（NEXT_IMPLEMENTATION_GATE）

1. **TEAMMATE_DRAFT_TARGET_ARCH** —— 确认 draft 训在哪个 target（MiniCPM-o 4.5 Main LLM vs Qwen3-8B）。target ≠ MiniCPM-o 则此 draft 与 target 不匹配，直接停（见 §2.0 Qwen3-only converter 约束）。
2. **CHECKPOINT_TENSOR_CONTRACT** —— 索要 draft tensor 名/形状（markov_w1/w2 **+ conf_proj**，缺 conf_proj 非完整 DSpark），见 `DSpark_DRAFT_ARTIFACT_CONTRACT.md`。
3. **MINICPMO_CONVERTER_FEASIBILITY** —— MiniCPM-o → DFlash GGUF converter（上游 `Qwen3DSparkModel` 仅 Qwen3）。
4. **DFLASH_SUBSTRATE_BACKPORT** —— 先移植 DFlash substrate（`d1b34251b`），**确保含 `571d0d540` K/V rotate 语义**（571d 是 DSpark 祖先，非事后补丁）。
5. **DSPARK_DELTA** —— 再 backport DSpark delta（`84075273c`）。
6. **LLAMA_CLI_STANDALONE** —— 在 `llama-cli`/`llama-server`（**非 omni**）先跑通 `draft-dspark` 独立正确性。
7. **CANN** —— CANN 算子/图兼容 + FA NaN 回归。
8. **OMNI_INTEGRATION** —— 最后才接线 `llama-omni-server`。
9. **ACCEPTANCE / AMDAHL** —— acceptance A/B + E2E Amdahl 重测（decode 占比仍 < 20% 则压低期望）。

> 关键：**先让同一 target + draft 在普通 llama-cli 路径跑通**，否则 CANN / DSpark / Omni lifecycle 三变量齐进，极难 debug。
