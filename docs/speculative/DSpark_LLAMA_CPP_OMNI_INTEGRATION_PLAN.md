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
| 本 fork 上游同步点 | llama.cpp `cb47092b0`（2026-06-01，距今 ~2.5 月） |
| `DSPARK_UPSTREAM_PORT_GAP` | backport `COMMON_SPECULATIVE_TYPE_DRAFT_DSPARK` + DSpark draft loader + GGUF 元数据 + CLI flag + server 接线 |
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

### 需要 backport 的最小文件集（待从上游 diff 精确定位）

| 区域 | 预期文件 | 内容 |
|---|---|---|
| 类型枚举 | `common/common.h` | `COMMON_SPECULATIVE_TYPE_DRAFT_DSPARK` |
| draft 参数 | `common/common.h` / `common/arg.cpp` | `--spec-type draft-dspark`、`--spec-draft-n-max` 等已有 |
| 模型加载 | `src/llama-model.cpp` / `src/llama.cpp` | DFlash backbone + markov head + confidence head 张量加载 |
| 运行时 | `common/speculative.cpp` | draft 前向：`dspark_markov_w1/w2`、`dspark_conf_proj`、`dflash.block_size` |
| GGUF 转换 | `convert_hf_to_gguf.py`（或独立 converter） | HF DSpark → GGUF 张量映射 |
| CLI/server | `tools/server/` | 现有 `server-context.cpp` 已接 `common_speculative`，需补 DSpark 分支 |

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

1. 队友 draft checkpoint 到位（解除 `TEAMMATE_DRAFT_COMPATIBILITY=NOT_AVAILABLE`）。
2. 上游 DSpark commit 集合定位（`git log upstream --grep dspark`）。
3. backport 最小文件集，在 **`llama-cli`/`llama-server`**（非 omni）先跑通 `draft-dspark` 独立正确性。
4. 再接线 `llama-omni-server`。
5. Amdahl 前提重测：若 decode 占比仍 < 20%，继续压低期望（见 §4.2）。
