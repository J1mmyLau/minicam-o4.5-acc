# F6 优化与结果

> **候选源码**: `bdd4550` | **所有结果标签**: `INTERNAL`（非官方）
> **统计纪律**: p50/p95/CI95, 预声明排除规则, 配对比较, 不挑 best-case

---

## 1. 原始 Baseline

| 指标 | 值 | 配置 |
|------|-----|------|
| Request→W0 p50 | ~4,800 ms | 910C, CANN 9.0, -ngl 999, CPU T2W |
| Decode→Speak 分界 | 142 ms (2.9% of W0) | Talker token generation 耗时 |
| T2W CPU 占比 | ~93% of W0 | Flow+Vocoder 全在 CPU |
| Per-chunk RTF (内部) | N/A | 无 chunk 级测量 |

**瓶颈判定**: T2W (Flow+Vocoder) 在 CPU 上运行是 Amdahl #1 瓶颈（占比 93%），主 LLM decode 占比 <3%。

---

## 2. Profiling 与瓶颈排序

| 阶段 | 占比 (W0) | 设备 | Amdahl 排名 |
|------|----------|------|------------|
| T2W Flow+Vocoder | 93% | CPU | **#1** (唯一值得优化的) |
| Talker token generation | 2.9% | CANN | #2 (已足够快) |
| Prefill | 不定 | CANN | #3 (KV HIT 后已优化) |
| 其他 | <1% | — | REJECT_BY_AMDAHL |

**决策**: 只优化 #1 (T2W)。#2 和 #3 占比不足，不投入。

证据: `docs/F6_PHASE2_STEP2_LATENCY_BUDGET.md`, `docs/F6_PHASE2_STEP5_AMDAHL_RANKING.md`

---

## 3. 优化 #1: CANN T2W (Flow+Vocoder)

**问题**: T2W 默认使用 `ggml_backend_cpu_buffer_type()`，即使主 LLM 在 CANN。

**方案**: env-only 配置开关，零代码修改:
```bash
OMNI_T2W_DEVICE=cann-flow-only
OMNI_VOC_DEVICE=gpu
```

**结果** (Phase 2, Step 6):

| 指标 | Baseline | Candidate | Δ | 状态 |
|------|---------:|----------:|----:|------|
| Request→W0 p50 | 4,798 ms | 894 ms | −3,904 ms (−81.4%) | `INTERNAL` |
| CI95 (bootstrap) | — | [−4,220, −3,732] | 不含 0 | `PASS` |
| 样本 | 32 pairs | 32 pairs | 同 binary/硬件/模型/输入 | `PASS` |
| 4 种 case 类型 | — | 全部 −79%~−83% | 一致 | `PASS` |
| WAV 有效性 | — | 32/32 16-bit PCM @24kHz | 无损 | `PASS` |
| CPU fallback | — | 0 | 全部在 CANN | `PASS` |

**计时口径**: HTTP request arrival → 首个 WAV 文件 mtime。同 binary (e159b3ee)、同 910C、同 MiniCPM-o-4_5-F16.gguf、同 32 组 prompt。

> ### −81.4% 完整指标定义
>
> | 字段 | 值 |
> |------|-----|
> | **Metric** | Request→W0 p50（HTTP request arrival → first WAV file mtime，wall clock） |
> | **Baseline** | 4,798 ms（CPU T2W） |
> | **Candidate** | 894 ms（CANN T2W: `OMNI_T2W_DEVICE=cann-flow-only`，`OMNI_VOC_DEVICE=gpu`） |
> | **Δ** | −3,904 ms（−81.4%） |
> | **n** | 32 strict matched pairs |
> | **CI95** | [−4,220, −3,732]（bootstrap，10,000 resamples），不含 0 |
> | **Commit** | e159b3ee（收益在 bdd4550 中保持） |
> | **Hardware** | Ascend 910C dual-die，CANN 9.1.0-beta.1 |
> | **Evidence** | `docs/F6_PHASE2_STEP6_CANN_T2W_AB.md` + `docs/f6-s13-closure/phase2/step6_cann_t2w_ab.json` |
> | **Status** | `HISTORICAL_INTERNAL_RESULT` — 非官方 chunk RTF、非全请求 E2E、非 vLLM 结果 |

**证据**: `docs/F6_PHASE2_STEP6_CANN_T2W_AB.md`, `docs/f6-s13-closure/phase2/step6_cann_t2w_ab.json`

**决策**: **ACCEPT** ✅

---

## 4. 优化 #2: Static Prefix KV Cache

**问题**: 每次请求重新 prefill 系统 prompt + reference audio embedding，210ms p50。

**方案**: 首次 prefill → save KV cache to CANN buffer → 后续请求 load + skip prefill (仅在 prefix 后 decode)。

**结果** (Phase 3, R13 Canonical):

| 指标 | MISS (无 cache) | HIT (有 cache) | Δ | 状态 |
|------|----------------:|---------------:|----:|------|
| Prefill p50 | 206 ms | 85 ms | −121 ms (−58.7%, **2.4×**) | `INTERNAL` |
| 样本 | 30 strict matched pairs | 30 strict matched pairs | — | `PASS` |
| First-Audio W0 p50 | 4,606 ms | 4,486 ms | −120 ms | `PASS` |
| CI95 (bootstrap) | — | [37, 249] ms | 不含 0 | `PASS` |
| KV integrity | — | 30 SAVED + 30 HIT | 0 NOT_REUSABLE | `PASS` |
| CPU fallback | — | 0 | — | `PASS` |

**T6 Frozen-Binary 集成** (28/30 valid, 2 A_ERR pairs documented):

| 指标 | MISS | HIT | Δ |
|------|-----:|----:|----:|
| Prefill p50 | 202.8 ms | 82.0 ms | −120.8 ms (**2.47×**) |

**注意**: R13 Canonical (30/30) 是正式机制证明；T6 (28/30) 是冻结 binary 回归再确认。不得用 T6 的 28/30 覆盖 Canonical 的 30/30。

**证据**: `docs/tracking/f6_lifecycle/R13_CANONICAL_STATIC_PREFIX_AB_FINAL.md`, `docs/f6-s13-closure/phase2/T6_INTEGRATED_REGRESSION_REPORT.md`

**决策**: **ACCEPT** ✅ (DEFAULT_OFF, OPT_IN via `OMNI_KV_CACHE_REUSE=1`)

---

## 5. 优化 #3: Persistent Server 生命周期

**问题**: 早期版本每次请求后 ctx 失效，drain timeout 导致后续请求失败。

**方案**: 修复 drain 逻辑、timeout 处理、ctx validity 检查。

**结果**:

| 指标 | 结果 |
|------|------|
| 3 sequential decode requests | **ALL PASS** |
| ctx validity across requests | **PASS** |
| drain timeout | **FIXED** |
| Cross-request contamination | **0** (R7/R9 fix) |

**证据**: `docs/tracking/F6_C6_PROFILE_LIFECYCLE_STATE_MACHINE.md`

**决策**: **ACCEPT** ✅

---

## 6. 负实验 #4: B6b (早期 TTS 阈值)

**问题**: TTS chunk 调度阈值从 10 降到 5，试图更早触发 TTS。

**方案**: 降低 `speak_threshold` → 更早进入 T2W pipeline。

**结果**:

| 指标 | 值 |
|------|-----|
| 收益 | 不显著 |
| CI95 | **跨 0** |
| 决策 | **REJECT_BY_AMDAHL** |

**证据**: `docs/tracking/F6_B6B_REJECTED_CANDIDATE.md`, `docs/tracking/F6_B6B_ENGINEERING_THRESHOLD_ANALYSIS.md`

**决策**: **REJECT** ❌

---

## 7. 优化 #5: TTS KV Bounds Guard

**问题**: 单请求内 n_past 可能达到 n_ctx=4096 上限，导致 KV cache overflow。

**方案**: Prefill guard (cap `prefill_with_emb_tts` at 256 tokens) + T13 确定性边界测试。

**结果**:

| 指标 | 结果 |
|------|------|
| T13 boundary test | **PASS** (guard=39, cap=256) |
| n_past overflow | **0** |

**证据**: `docs/tracking/` F6 T13 memory

**决策**: **ACCEPT** ✅

---

## 8. 优化 #6/#7: 非流式 Text + SSE 修复

**问题**:
- 非流式 decode 缺少 text 输出字段
- SSE + `bad_alloc` crash (sink.done after worker exit)

**方案**: T9 server fixes (worker-once + sink.done guard + text field in non-streaming response)。

**结果**: 两项 crash 均已修复；非流式 text 输出正常工作。

**证据**: `docs/tracking/` F6 T9 memory

**决策**: **ACCEPT** ✅

---

## 9. CANN CPU/NPU 放置审计

详见 `docs/audit/CANN_CPU_NPU_PLACEMENT_AUDIT.md`。

| 状态 | 含义 |
|------|------|
| `CANN_STATIC_CAPABILITY_AUDIT=PASS` | supports_op 60+ / offload 规则 / sync/copy 调用点 / KV buffer 已查清 |
| `MAIN_LLM_STATIC_PLACEMENT=PASS` | -ngl 999 模型 weight tensor 在 CANN，scheduler Pass 1.wgt 可追踪 |
| `MAIN_LLM_RUNTIME_PLACEMENT=PARTIAL` | 静态放置 PASS 但缺直接 profiler 证据（msprof/CANN timeline/backend 分配日志） |
| `MAIN_LLM_CPU_FALLBACK_OBSERVED=NO` | 冻结日志未观察到 CPU fallback（不等于证明无） |
| `GRAPH_SPLIT_RUNTIME_COUNT=NOT_MEASURED` | 待 GGML_SCHED_DEBUG=1 测量 |
| `CPU_PER_CHUNK_CRITICAL_PATH=TO_MEASURE` | 需逐 chunk 运行时预算完成 Amdahl 判定 |

**关键发现**: `caps.async=false` / `offload_op ne[1]>=32` gate / FLASH_ATTN_EXT 仅支持 F16 Q/K/V

---

## 10. T6 集成回归（最终）

| Gate | 结果 |
|------|------|
| S13 120/120 稳定性 | **PASS** (p50=17.0s, 4 case types) |
| Extended 30/30 | **PASS** |
| Voice 5/5 + isolation | **PASS** |
| Disconnect 5/5 + follow-up | **PASS** |
| KV A/B | **28/30 valid** (2 A_ERR documented, mechanism 30/30) |
| Smoke 5/5 | **PASS** |
| cpu_fallback | **0** |
| cann_error | **0** |
| **ACCEPT** | **True** / **11/11 PASS** |

**证据**: `docs/f6-s13-closure/phase2/T6_INTEGRATED_REGRESSION_REPORT.md`

---

## 11. Daily-Omni 内部 Pilot

| Gate | 结果 |
|------|------|
| 6/6 server gates | **PASS** |
| 3 P0 fixes | user_text drop / media_type=2 prompt identity / image+audio think-loop format |
| whisper ceiling | ~24-26s (已知限制) |

**注意**: 这是内部 pilot，不是官方 Daily-Omni 准确率评测。官方评测 `NOT_RUN`。

**证据**: `docs/f6-s13-closure/phase2/daily_omni_pilot/pilot_run.log`

---

## 12. 官方结果 — 待执行

| Gate | 状态 |
|------|------|
| 官方 Daily-Omni | `NOT_RUN` |
| 官方 TTS-Seed | `NOT_RUN` |
| 官方 Video-MME | `NOT_RUN` |
| 官方 Demo | `NOT_RUN` |
| 官方 per-chunk RTF | `NOT_RUN` |

全部 `BLOCKED_BY_OFFICIAL_STARTER_KIT`。`COMPETITION_COMPLETE=NOT_CLAIMED`。

---

## 13. 最终优化组合

| 优化 | 决策 | 收益 |
|------|------|------|
| CANN T2W (env-only) | ACCEPT | W0 −81.4% |
| Static Prefix KV | ACCEPT | Prefill 2.4× |
| Persistent 生命周期 | ACCEPT | 多请求复用 |
| TTS KV bounds | ACCEPT | 防 overflow |
| Text + SSE fixes | ACCEPT | 功能正确 |
| B6b | REJECT | CI 跨 0 |
| **T6 总体 ACCEPT** | **11/11** | — |

**未纳入的潜在优化**（Amdahl REJECT 或未验证）:
- MTP (multi-token prediction): `NOT_REACHABLE_WITH_CURRENT_MODEL`
- Chunk size 调整: REJECT (B6b 负实验)
- O1 等参数调优: REJECT (不改变瓶颈)

---

## 统计纪律

- 所有数字附 commit / binary SHA / 配置 / raw 路径 / 状态标签
- `INTERNAL`: 内部验证结果，不宣称官方
- `LLAMA_CONFIRMED`: 冻结日志实测值，可引用
- `NOT_MEASURED`: 未测量
- `NOT_RUN`: 官方 Gate 未执行
