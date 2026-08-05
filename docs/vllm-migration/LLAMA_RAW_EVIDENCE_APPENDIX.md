# llama 原始证据附录（事实与假设）

> **用途**：队友在 vLLM 中做 baseline / A/B / 打点时，用这里的具体数字作为"什么样的测量才算可信"的参考标尺。
> **硬性口径**：这些全部是 **llama 侧实测**，**不是 vLLM 结果**。迁移到 vLLM 前必须重新测量。
> **状态标签（vLLM 侧只能从这 4 个选）**：
> - `CONFIRMED_FROM_DEPLOY_DOC` = 现有 vLLM 部署文档已写明
> - `TO_AUDIT_IN_SOURCE` = 需在 vLLM 源码核实
> - `TO_MEASURE_AT_RUNTIME` = 需在 vLLM 运行时测量
> - `UNPROVEN` = 尚无任何证据

---

## 0. 实验环境（本附录所有 llama 数字的统一定义）

| 项 | 值 |
|---|---|
| 硬件 | 1× Ascend 910C（dual-die），CANN 9.1.0-beta.1 |
| 模型 | `MiniCPM-o-4_5-F16.gguf`（llama 侧）/ `OpenBMB/MiniCPM-o-4_5`（vLLM 侧） |
| llama 运行 env | `OMNI_KV_CACHE_REUSE=1 OMNI_T2W_DEVICE=cann-flow-only OMNI_VOC_DEVICE=gpu ASCEND_RT_VISIBLE_DEVICES=0` |
| llama 运行参数 | `-c 4096 -b 512 -ub 512 --split-mode layer` |
| llama 候选二进制（**冻结，最终**） | `llama-omni-server db258375` + `libomni.so c4b16937`（REPRODUCIBLE_BINARY=PASS：两次干净重建 SHA 逐字节一致；前序 `594920b6`/`f1d2f86d`/T5 `e77b43c3` 仅历史参考） |
| llama 源码/文档 commit | CANDIDATE_SOURCE_COMMIT `bdd4550`；EVIDENCE_DOCS_COMMIT `adb9bb6`+`d5cc978`（交接时分开标注，不笼统写 HEAD） |
| llama T6 冻结二进制重跑 | **11/11 GATES PASS, ACCEPT=True**（binary_sha=db258375；S13 120/120、Ext 30/30、Voice 5/5、Disc 5/5、KV A/B 28/30、Smoke 5/5；cpu_fallback=0/cann_error=0） |

---

## A. 静态前缀 KV Cache A/B（PreFill）

| # | 数值 | 指标定义 | 样本 | 来源 | 适用范围 | 是否可迁移 | vLLM 状态 |
|---|---|---|---|---|---|---|---|
| A1 | MISS p50 **206 ms** | 未复用前缀的 prefill 阶段 p50 | 30/30 strict matched | `docs/tracking/F6_PHASE3_STEP9_STATIC_PREFIX_REPORT.md` | 仅 prefill 阶段，**非端到端** | 否（机制可迁移，数字不可） | `TO_MEASURE_AT_RUNTIME` |
| A2 | HIT p50 **85 ms** | 复用前缀的 prefill p50 | 同上 | 同上 | 同上 | 同上 | `TO_MEASURE_AT_RUNTIME` |
| A3 | 绝对减少 **121 ms** | A1−A2 | 同上 | 同上 | — | 同上 | `TO_MEASURE_AT_RUNTIME` |
| A4 | 阶段降幅 **58.7%** | (A1−A2)/A1 | 同上 | 同上 | 仅 Prefill，**不是端到端收益** | 同上 | `TO_MEASURE_AT_RUNTIME` |
| A5 | 阶段加速 **2.4×** | A1/A2 | 同上 | 同上 | 同上 | 同上 | `TO_MEASURE_AT_RUNTIME` |
| A6 | 复验 210→86ms（2.5×） | 独立第二次 A/B | 30/30 | Step 8 报告 | 同 A4 | 同上 | `TO_MEASURE_AT_RUNTIME` |
| A7 | T6 内联 201.7→83.1ms（2.43×，Δ119ms） | 与回归同跑的 KV A/B | 30/30 | `docs/f6-s13-closure/phase2/T6_INTEGRATED_REGRESSION_REPORT.md` | 同 A4 | 同上 | `TO_MEASURE_AT_RUNTIME` |
| A8 | reused ≈130 tokens | 单个 HIT 请求复用的前缀 token 数 | 单请求观测 | R13 报告 | llama 前缀长度语义 | **旧 CLI 62 tokens 结果不得混用** | `TO_MEASURE_AT_RUNTIME` |

**注意**：58.7% / 2.4× 是 **prefill 阶段**的改善。llama 端到端（含 TTS）中该收益被下游摊薄；**vLLM 端必须报端到端 TTFT / audio TTFP 是否真的下降**，不能只报 "Hit"。

---

## B. CANN Token2Wav 设备放置 A/B（CPU → NPU）

| # | 数值 | 指标定义 | 样本 | 来源 | 适用范围 | 是否可迁移 | vLLM 状态 |
|---|---|---|---|---|---|---|---|
| B1 | W0 p50 CPU **4798 ms** | 首个有效语音 token 延迟（T2W 在 CPU） | 32/32 pairs | `docs/F6_PHASE2_STEP6_CANN_T2W_AB.md` | llama 设备放置收益 | 否（数字） | `TO_MEASURE_AT_RUNTIME` |
| B2 | W0 p50 CANN **894 ms** | 同上（T2W 在 NPU） | 32/32 | 同上 | 同上 | 否 | `TO_MEASURE_AT_RUNTIME` |
| B3 | 相对改善 **−81.4%** | (B2−B1)/B1 | 32/32 | 同上 | CI95 [−4220, −3732] ms | 否 | `TO_MEASURE_AT_RUNTIME` |
| B4 | T4 严格复核 19/19 全负 | 排除 LLM 随机 preamble 后的 T2W-only delta | 19/19 | `docs/f6-s13-closure/phase2/t4_strict_cann_t2w.json` | 同 B | 否 | `TO_MEASURE_AT_RUNTIME` |
| B5 | T2W-only p50 **−4215.8 ms** | CI95 [−4395.6, −4085.4] | 19/19 | 同上 | 同 B | 否 | `TO_MEASURE_AT_RUNTIME` |
| B6 | W0 E2E p50 **−3946 ms** | CI [−4379, −3799] | 同 B4 | 同上 | 同 B | 否 | `TO_MEASURE_AT_RUNTIME` |
| B7 | correlation gates **10/10** | echo/single_w0/gen_match/wav_req_bind/reqidx_e2e_bind/wav_count/d2fa_cross/d2fa_e2e_audio/audio_valid/stale_cross | — | 同上 | 事件关联可信度 | 否 | `TO_MEASURE_AT_RUNTIME` |

---

## C. Phase 2 瓶颈拆分（为什么"先打点再优化"）

| # | 数值 | 指标定义 | 来源 | 适用范围 | 可迁移 | vLLM 状态 |
|---|---|---|---|---|---|---|
| C1 | Decode→Speak **~2.9%** | LLM 主链路占端到端 | `docs/F6_PHASE2_STEP3_DECODE_SPEAK_BREAKDOWN.md` | 该 llama 请求形态 | 否（数字） | `TO_MEASURE_AT_RUNTIME` |
| C2 | T2W inference **~93%** | Flow/Vocoder 占端到端 | 同上 | 同上 | 否 | `TO_MEASURE_AT_RUNTIME` |
| C3 | B6b 无稳定收益 | 提前 5 token 触发 TTS 的端到端 A/B | `docs/F6_PHASE2_STEP6_CANN_T2W_AB.md` | 负结果，教训 | **是（教训）** | `TO_MEASURE_AT_RUNTIME` |

---

## D. S13 冻结基线（120 请求长稳）

| # | 数值 | 指标定义 | 来源 | 可迁移 | vLLM 状态 |
|---|---|---|---|---|---|
| D1 | **120/120 valid** | 4 类 case（short_cn/long_cn/english/number_mix ×30） | `docs/tracking/f6_lifecycle/S13_120_BASELINE_FINAL.md` | 方法可迁移 | `TO_MEASURE_AT_RUNTIME` |
| D2 | E2E p50 **17.0 s** | 含 TTS 生成的端到端 p50 | 同上 | 否（数字） | `TO_MEASURE_AT_RUNTIME` |
| D3 | E2E p95 **121.6 s** | 长 TTS 尾部 | 同上 | 否 | `TO_MEASURE_AT_RUNTIME` |
| D4 | TTS WAV 有效 | 16-bit@24k | 同上 | 是（校验口径） | `TO_MEASURE_AT_RUNTIME` |

---

## E. T6 最终集成回归（11/11 Gates，ACCEPT=True）— 冻结二进制重跑（最终口径）

> 下表为**冻结源码 bdd4550 重建二进制**上的 T6 完整重跑（re-run #3，binary_sha=db258375）；这是最终口径。
> 前序 re-run #2（@ 91797e6+未提交 diff，libomni c075c535）的 KV A/B 为 27 valid（3 对排除，见 `t6_kv_ab_27of30.md`），仅历史参考。

| # | 项 | 数值 | 来源 | vLLM 状态 |
|---|---|---|---|---|
| E1 | S13_STRICT_BASELINE | 120/120，err=0，runaway=0，prompt_modified=0，first_attempt_ok=120 | `docs/f6-s13-closure/phase2/T6_INTEGRATED_REGRESSION_REPORT.md` + `t6_integrated_regression.json` | `TO_MEASURE_AT_RUNTIME` |
| E2 | Extended | 20 long + 10 mixed = 30/30 | 同上 | 同上 |
| E3 | Voice-switch | 5/5 + 目录隔离（5 distinct hashes） | 同上 | 同上 |
| E4 | Disconnect | 5/5 存活 + followup OK | 同上 | 同上 |
| E5 | KV Cache A/B（冻结口径） | 30 pairs / **28 valid**（2 对 C2-R2/C5-R3 按预声明 A_ERR 排除，机制 30/30；202.8→82.0ms，2.47×，loaded=130） | 同上 | 同上 |
| E6 | 重启 | 3 会话重启 | 同上 | 同上 |
| E7 | CPU fallback / CANN error | **0 / 0**（cann_ok=4） | 同上 | 同上 |
| E8 | stop 分布 | eos=81 / max_tokens=39 | 同上 | 同上 |
| E9 | decode_wall p50 | 5437ms | 同上 | 同上 |

---

## F. 请求→首音 E2E

| # | 数值 | 指标定义 | 来源 | vLLM 状态 |
|---|---|---|---|---|
| F1 | 前 p50 **4.69 s** → 后 **4.59 s**（−120ms） | request→W0 端到端 | `docs/f6-s13-closure/phase2/F6_FINAL_DELIVERY_REPORT.md` §6 | `TO_MEASURE_AT_RUNTIME` |

---

## G. TTS/Talker 独立上下文上限（最新坑）

| # | 现象 | 数值 | 说明 | 来源 | vLLM 状态 |
|---|---|---|---|---|---|
| G1 | `tts_n_past_accumulated` | **4096** | = TTS 自身 KV context（与 llama 主模型同 4096） | `docs/f6-s13-closure/phase2/t6_evidence_f9/`、`tools/omni/omni.cpp` `eval_tokens_tts` | `TO_MEASURE_AT_RUNTIME` |
| G2 | `decode: failed to find a memory slot` | — | llama_decode 打进满 KV | 同上 | 同上 |
| G3 | 单请求累积 | **3815 tokens** | 一个长请求内撞顶（**非跨请求**） | 同上 | 同上 |
| G4 | 修复（F6 T11） | bounds guard | `eval_tokens_tts`/`prefill_with_emb_tts`：`n_past+batch > llama_n_ctx` 提前 return false | 同上 | — |
| G5 | 修复闭环验证 | **TTS_KV_GUARD_IMPLEMENTED=YES / RUNTIME_COVERAGE=PASS** | 常规 T6 回归 + T13 确定性边界测试（guard=39 全来自 prefill_with_emb_tts，cap=256）+ followup 复用 + 正式源码去除测试钩子 | `docs/f6-s13-closure/phase2/tts_boundary/tts_boundary_20260804_170049.json` | — |

**迁移问题（vLLM 必答，TO_AUDIT）**：Talker KV / Token2Wav 内部 buffer / Block Manager / `max_num_batched_tokens` / `max_num_seqs` / output token cap —— 哪一级先满？不能把所有 memory-slot 类错误归因主模型 KV。

---

## H. 参考版本/二进制（llama 侧冻结基线示例）

见 §0 环境表。冻结基线必须至少记录：`run_id / server pid / server instance id / source HEAD / deploy YAML SHA / model revision / binary version / 启动命令 / NPU 拓扑 / raw 路径`。

---

## I. llama 结论状态总表（事实 vs 假设 vs 历史）

| 结论 | 状态 | 依据 |
|---|---|---|
| 静态前缀可复用（机制） | **CONFIRMED**（llama 侧） | R13 30/30 A/B |
| 静态前缀 58.7% 收益（数字） | **llama 事实 / vLLM 假设** | 仅 prefill 阶段 |
| T2W 设备放置是首音大头（llama） | **CONFIRMED**（llama 侧） | Phase 2 STEP3/6 |
| T2W 设备放置是 vLLM 大头 | **UNPROVEN** | 需 V4 实测 |
| decode→speak 是瓶颈 | **REJECTED**（llama 侧） | 2.9% |
| B6b 有效 | **REJECTED**（llama 侧） | 无稳定收益 |
| request 完成 = 全部 Stage 完成 | **REJECTED** | R7 drain 教训 |
| TTS 有独立 context 上限 | **CONFIRMED**（llama 侧） | tts_n_past_accumulated=4096 |
| TTS KV guard 已实现并覆盖 | **CONFIRMED**（llama 侧，T11+T13） | G5；正式冻结源码无测试钩子 |
| vLLM Prefix Cache 覆盖多模态/TTS 前缀 | **UNPROVEN** | 需 V5 审计 |
| vLLM 组件名/函数（组件映射中所有 TO_AUDIT 项） | **UNPROVEN** | 需源码审计 |

> **llama 侧最终状态（2026-08-05）**：内部候选已真正冻结完成——源码 bdd4550、二进制 SHA 固化、T6 冻结二进制 11/11 PASS、工作树 clean、无遗留 server 进程。后续只剩官方评测与提交（官方 Daily-Omni / Seed-TTS / Video-MME / 官方提交包核验），不再属于候选研发。llama 侧任何数字在本附录均为"参考标尺"，vLLM 侧必须重新测量。

> 状态标签只用于本附录结论行。正文每节的"证据状态"同理：`CONFIRMED / INFERENCE / HISTORICAL / UNPROVEN`。
