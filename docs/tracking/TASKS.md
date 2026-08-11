# TASKS

## Phase 0–3：已完成 ✅

| ID | 状态 | 说明 |
|----|------|------|
| TASK-000 | DONE | 工作区冻结 |
| TASK-001 | DONE | clean-tree 验收 |
| TASK-002 | DONE | debug patch 验证 |
| TASK-003A | DONE | Full Omni Baseline |
| TASK-003B | DONE | Audio-only Baseline |
| TASK-003E | DONE | Duplex RT Baseline |
| TASK-003F | DONE | Duplex B2B Baseline |
| TASK-004 | DONE | 30-min Stability — PASS 14/14 |
| TASK-005 | DONE | CANNBot 安装与索引 |

## Phase 4：Profiling（已完成 ✅）

| ID | 状态 | 说明 |
|----|------|------|
| TASK-006 | **DONE** | msprof 采集 + CANN-level 分析完成 |
| — | — | model-infer-perf-breakdown Skill: NOT APPLICABLE (PyTorch-only) |

## Phase 5–7：优化

| ID | 状态 | 说明 |
|----|------|------|
| TASK-007 | **DONE** | 候选排序 + 实验设计完成 |
| EXP-001 | **ARCHIVED** | D2D async stream (CORRECTNESS PASS) |
| EXP-002 | **ARCHIVED** | Buffer free-list cache (CORRECTNESS PASS) |
| EXP-005A | **DONE** | T2W localization: encoder+flow graph ALREADY cached |
| EXP-005-V1 | **REDUNDANT** | Graph cache — already done upstream |
| EXP-005-V3 | **REJECTED_CORRECTNESS_AND_PERFORMANCE** | Audio -5.3%, perf +1.4% per-unit |
| EXP-005-V3-B | **ARCHIVED** | Persistent worker — CORRECTNESS PASS, PERF NEUTRAL (+0.3%) |
| EXP-005-V5 | **DONE** | CPU threads sweep — optimal 16 threads, +1.2% vs 8 |
| TASK-BACKEND-CONFIRM | **DONE** | Confirmed: encoder+flow+vocoder ALL CPU on CANN |
| EXP-006 | **DONE** | NUMA affinity: node0 -4.07%, cluster0 -3.08%, correctness PASS |
| E2E-REGRESSION-16t | **DONE** | Full Omni 2/2 PASS with 16 threads, NaN=0 |
| TASK-020 | BLOCKED | AscendC（Gate NOT SATISFIED） |
| EXP-006-PROD | **DONE** | OMNI_T2W_CPU_AFFINITY implemented, correctness PASS |
| V3-B-CLEANUP | **DONE** | ARCHIVED worker code removed, unified sync path |
| E2E-NUMA-VALIDATION | **DONE** | Full Omni + NUMA affinity E2E validation — 3/3 PASS, NaN=0 |
| TASK-021 | **ARCHIVED** | EXP-007: OpenBLAS for T2W MatMul — NEUTRAL (+0.28%), correctness PASS |
| TASK-022 | **DONE** | CPU Profile: MUL_MAT=73-75%, REPEAT(vocoder)=41-44%, CONCAT=12-14% |
| TASK-023 | **DONE** | Fused Attention MatMul — ALREADY UPSTREAM (852 calls with fusion, 1012 without). Perf NEUTRAL. No further MUL_MAT fusion possible without model change. |
| TASK-024 | **ARCHIVED** | Q8_0 Quantization — NEGATIVE (+19.8%), compute-bound MUL_MAT |
| TASK-025 | **ARCHIVED** | CONCAT optimization — NEUTRAL (-0.7%), graph infra dominates |
| TASK-026 | **DONE** | Full cumulative optimization E2E integration test — 6/6 PASS, NaN=0 |

## Phase 5 Closure

Phase 5 is COMPLETE. All CPU-level T2W optimization paths exhausted (MUL_MAT, CONCAT, BLAS, Q8_0).
Cumulative gain: -5.2% T2W (-0.37% E2E).

## Phase 8–10

| ID | 状态 | 说明 |
|----|------|------|
| TASK-030 | **DONE** | 官方 Harness 对齐 — WAV format verified (1ch, 24kHz, 16-bit), test protocol documented |
| TASK-040 | **DONE** | 最终验收 — Full Omni 5/5 PASS, NaN=0, exit=0, per-WAV improvement confirmed |

## Phase 11: FINAL-AB

| ID | 状态 | 说明 |
|----|------|------|
| FINAL-AB | **DONE** | Baseline (8t, no NUMA) vs Optimized (16t, NUMA node0) — 20 runs, all PASS. No significant gain. |
| FINAL-AB-PARSE | **DONE** | Results parsed: comparison.csv/json, conclusion.md, correctness_summary.md, binary_manifest.json |
| F-009 | **DOCUMENTED** | Wall timer bug in run_ab.sh (Python f-string syntax error) |
| RELEASE | **DONE** | Build release/final-integration from baseline 3f7a7f0 — f89c6651d3f1baa21110de083263a71ac75c3f1b4308c7752243295da45acff5 |
| RELEASE-SMOKE | **DONE** | Smoke test PASS — exit=0, 36 WAVs, NaN=0, Chinese OK, WAV format verified |
| RELEASE-ARTIFACTS | **DONE** | release-artifacts/ generated — 15 files |
| RELEASE-READY | **DONE** | FINAL_RELEASE_READY marker written, all tracking updated |

## Phase 12: Token2Wav CANN 迁移

| ID | 状态 | 说明 |
|----|------|------|
| T2W-CANN-ROOTCAUSE | **DONE** | ROOT_CAUSE_CONFIRMED_THREAD_OWNERSHIP — CANN backend 线程亲和性 |
| T2W-CANN-MICROBENCH | **DONE** | Single-thread flow_matching CANN 17× faster |
| T2W-CANN-THREAD-MATRIX | **DONE** | A/B/C/D 线程矩阵：A=PASS, B=FAIL(ctx=NULL), C=PASS, D=PASS |
| T2W-CANN-FIX | **DONE** | 3fc0ed5 — worker 线程内延迟初始化 backend |
| T2W-CANN-CLI-AB | **DONE** | 8 CANN + 9 CPU runs: FA 3.2×, RTF 7.1×, RTF<1.0 ✓ |
| T2W-CANN-DUAL-T2W | **DONE** | 双实例 T2W process C2: 60/60, NPU0+NPU1 concurrent ✓ |
| T2W-CANN-LEVEL2 | **DONE** | First Audio 分解: Talker 1074ms(57%), T2W 465ms(24%), Worker 426ms |
| T2W-CANN-FIRST-CHUNK | **REJECTED** | Smaller first chunk: FC=16 → +38% FA |
| T2W-CANN-F003-ROOTCAUSE | **DONE** | F-003 根因: output_size bug + dest tensor shape in repeat_interleave |
| T2W-CANN-F003-RUNTIME | **DONE** | 7df34a1 dual-path ROPE repeat |
| T2W-CANN-F003-CORRECTNESS | **DONE** | neox CPU ref match, non-neox construction proof |
| T2W-CANN-F003-BASIC-STABILITY | **DONE** | 68+ streams, 0 CANN errors |
| T2W-CANN-WAV-SANITY | **DONE** | 1ch/24kHz, non-silent, no NaN/Inf |
| T2W-CANN-STRICT-AB | **PRELIMINARY** | n=5 paired: FirstAudio 6539→5095ms(-22%), inter-token p50 -48%, p90 -67% |
| T2W-CANN-AB-CAVEAT | **NOTE** | inter-token p90 may include chunk boundaries; final metrics: First28, steady ms/token, FirstAudio |
| T2W-CANN-TAIL-LATENCY | **RESOLVED** | earlier "regression" was gap-filter artifact; CANN p90=484ms < CPU 1487ms |
| T2W-CANN-WAV-SANITY | **PASS** | format/dur/peak/RMS/ZCR comparable; not content equivalence |
| T2W-CANN-RESTART | **PASS** | 3x3 + 2 short lifecycle runs, 0 CANN err |
| T2W-CANN-LIFECYCLE-120 | **PASS** | 15/15 runs, 255 WAVs+7 NoSpeech, 97.3% effective, restart PASS, 0 CANN err |
| T2W-CANN-ASR | **UNAVAILABLE** | no whisper/funasr/transformers |
| T2W-CANN-AUDIO-HUMAN | **SUPERSEDED** | F003-era blind listening; full CANN Talker BLOCKED by F004 |
| T2W-CANN-PRODUCTION | **SUPERSEDED** | 7df34a1 is RoPE fix only, NOT standalone Talker candidate |
| T2W-CANN-AUDIO | **SUPERSEDED** | Replaced by F004 ngl=8 hybrid validation |
| T2W-CANN-LIFECYCLE | **DONE** | 15/15 runs, 255 WAVs, 0 CANN err |

## Phase 13: F003/F004/F005 + E2E Profiling

| ID | 状态 | 说明 |
|----|------|------|
| F-003 | **FIXED** | 7df34a1 dual-path ROPE repeat（RoPE 修复，非完整 Talker candidate） |
| Full CANN Talker | **PRODUCTION_BLOCKED** | F004 发现 full CANN 数值分叉/坍缩风险 |
| F-004 | **VALIDATED** | ngl=8 hybrid Talker PRODUCTION_CANDIDATE（`e6151fb`） |
| F-005 detectors | **IMPLEMENTED** | consecutive + cycle + entropy, recall 33%, FP 0% |
| F-005 retry/fallback | **IMPLEMENTED** | `c1d2af6`, opt-in via `F005_RETRY_ON_DEGENERATE=1` |
| F-005 deployment | **RECALL_LIMITED / OPT_IN_READY** | recall 33%，不建议默认开启 |
| E2E-P1-INSTRUMENT | **DONE** | 16-stage profiler (d1e89db) |
| E2E-P2-BASELINE | **DONE** | n=34, FA p50=7280ms: LLM 69% + Talker 22% + T2W 6% |
| E2E-P3-EXPERIMENT | **REJECTED** | Chunking A/B v4: chunk=20 NEUTRAL（FA -8ms）, chunk=5 TTS 分歧 |
| E2E-P4-F005 | **DONE** | Recall 33%, FP 0%. Degeneration is stochastic. |

## Phase 14: P6 KV Cache Reuse A/B

| ID | 状态 | 说明 |
|----|------|------|
| P6-KV-CACHE-AB | **EXPERIMENT_COMPLETED / GATE_INCONCLUSIVE** | 46023f0: 72 runs, 54 valid. decode_to_first_audio neutral, prefill_start_to_first_audio -58.8% (COMPUTED), T2W 25% invalid. |
| P7.1-T2W-RACE | **DONE** | Root cause candidate: omni_free() join order kills T2W before first WAV. Full trace at P7_T2W_LIFECYCLE_TRACE.md. No statistically detectable arm association (Fisher p=0.56). |
| P7.2-METRIC-BOUNDARY | **DONE** | decode_to_first_audio clock starts inside stream_decode(), excludes prefill. request_to_first_audio not yet instrumented. |
| P0-TERMINOLOGY | **DONE** | Metric names corrected. Race language tightened. Report copied into repo. |
| P7.3-P2-DRAIN-FIX | **DONE (91bbcc9)** | T2W drain-before-stop state machine — T2WDrainState enum, EOS protocol, bounded timeout, terminal output classification |
| P7.3-P3-REGRESSION | **DONE ✅** | P9: 150/150 PASS, rc0_without_audio=0, 100% audio success |
| P7.3-P4-INSTRUMENT | **DONE (10e63ec)** | request_to_first_audio_ms from request boundary (before stream_prefill) |
| P7.3-P5-SUPPLEMENTAL | **DONE ✅** | P5: 64 executions, 62 valid (96.9%), req_fa improvement 9642ms p50 (59.0% reduction), prefill 2772x |
| P7.3-P6-DECISION | **PASS_FOR_TESTED_STATIC_PREFIX_WORKLOAD** | KV Cache ON: 9642ms p50 improvement, bootstrap 95% CI [8742, 11470]ms, 0 rc0_without_audio. 8 boundary conditions NOT_TESTED. |

## FINAL STATUS

Release: `bde403d`（冻结）。
Production candidate: ngl=8 hybrid（Talker ngl=8, Flow CANN, Vocoder CPU, F005 opt-in）。
Full CANN Talker: PRODUCTION_BLOCKED。
Chunking: REJECTED。
F003 7df34a1: RoPE fix only, not standalone Talker production candidate.
P7.3: ALL GATES PASSED — T2W drain fixed, 214 validated requests, 0 rc0_without_audio.
KV Cache: RECOMMEND_OPT_IN (OMNI_KV_CACHE_REUSE=1), 2772x prefill reduction, -60% request_to_first_audio.

## Phase 15: F6 — LLM Decode → First Speak Token Optimization

| ID | 状态 | 说明 |
|----|------|------|
| F6-0 | **PASS** | Baseline provenance frozen |
| F6-1 | **PASS** | Event semantic audit (S1-S8) — 6 semantic errors in draft V1 identified and corrected |
| F6-2-S9 | **CHECKPOINT_COMPLETE** | Instrumentation implemented: reset(), 4 new stages (D0/D1/G0/G2), D3 guard, STAGE_COUNT=20, build PASS |
| F6-2-S10 | **PROVISIONAL** | Correctness: 2 requests insufficient — need 20 mixed requests (A7) |
| F6-2-S11 | **NOT_RUN** | Overhead gate — need ≥20 matched pairs (A9) |
| F6-2-S12 | **PENDING** | Final: requires A7 + A9 PASS |
| F6_INSTRUMENTATION_CORRECTNESS | **PENDING** | Blocked by A3 (generation-safe), A5 (callsite audit), A6 (smoke reconciliation), A7 (20-request gate) |
| F6_INSTRUMENTATION_OVERHEAD | **NOT_RUN** | Blocked by A9 |
| F6_BASELINE_120 | **NOT_STARTED** | Blocked by A7 + A9 |
| F6-3-L7+ | **PENDING** | Autonomous optimization mission (L7-L31) |

## Phase 2：Decode→Speak Bottleneck 分析（6 步指令，全部完成 ✅）

| ID | 状态 | 说明 |
|----|------|------|
| P2-S1 | DONE | Phase 1 冻结（closure doc + raw data + scripts + SHA manifest, git clean） |
| P2-S2 | DONE | Latency budget — decode→speak=142ms(2.9%), T2W CPU=4490ms(93%) (f9a6241) |
| P2-S3 | DONE | Decode→Speak 内部分解 — 12 类未插桩 → DEFER (06f261a) |
| P2-S4 | DONE | MTP reachability audit — MTP_NOT_REACHABLE (1916743) |
| P2-S5 | DONE | Amdahl ranking — T2W CANN move #1 OPTIMIZE_FIRST (7c0aa56) |
| P2-S6 | DONE | CANN T2W A/B — W0 4798→894ms (−81.4%), 32/32, CI95 [−4220,−3732] (271265b) |

## Phase 3：最终集成候选与证据 Gate（T1–T8）

| ID | 状态 | 说明 |
|----|------|------|
| T1 | DONE | 统一状态文档 — S13_FROZEN_STRICT_BASELINE=PASS_120_OF_120；新 Gate=PENDING |
| T2 | DONE | baseline 设备口径审计 — CPU T2W=默认回退+实测参考 baseline；候选=DEVICE_PLACEMENT_CORRECTION |
| T3 | DONE | 严格事件关联 — 埋点实现并提交 (510a9f0): decode-start 打印 round_idx/gen/reqidx；W0/wav 行打印 req/gen；decode 响应回显 round_idx/generation_id/wav_count/decode_to_first_audio_ms；E2EStageTiming::decode_to_first_audio_ms()。smoke 验证通过：value-bound 证据全渠道一致 |
| T4 | **DONE** | CANN T2W 严格复核 — FULL PASS：20 对 / 19 active / 1 NoSpeech；10 correlation gates 19/19（echo/single_w0/gen_match/wav_req_bind/reqidx_e2e_bind/wav_count/d2fa_cross/d2fa_e2e_audio/audio_valid/stale_cross）；0 fallback / 0 error / 0 timeout；RSS+HBM 单调；**T2W-only delta 19/19 全负**（p50 −4215.8ms, CI95 [−4395.6,−4085.4]，排除 LLM 随机 preamble），W0 E2E p50 −3946ms (CI [−4379,−3799])；修复服务端 wav_count 跨轮累计 bug（is_final 不再提前 last_round_idx）；NoSpeech 分类改用 e2e_audio JSON 缺失（talker_token_count 不可靠：round 302 说话却报 0）；证据 `docs/f6-s13-closure/phase2/t4_strict_cann_t2w.json` |
| T5 | **DONE** | 最终集成候选冻结 = INTERNAL_PASS — 组合 KV Cache + HTTP token cap + 生命周期 + CANN Flow/Vocoder；freeze 文档 `docs/F6_PHASE3_T5_FINAL_INTEGRATED_CANDIDATE.md`（binary e77b43c3, libomni f1d2f86d, HEAD b043257, 组件 commit chain + 未验证边界诚实披露） |
| T6 | **DONE** | 最终集成回归 — ALL 11 GATES PASS, ACCEPT=True：S13 120/120 (err=0, eos=86/max_tokens=34, 0 runaway)；Extended 20 long + 10 mixed = 30/30；Voice-switch 5/5 + 目录隔离；Disconnect 5/5 存活 + followup OK（修复：不再 recovery re-init，弃用 omni_free 与在途 decode 竞争）；KV A/B 30/30 (MISS 201.7→HIT 83.1ms, Δ119ms, 2.43×)；3 会话重启；0 CPU fallback / 0 CANN error。证据 `docs/f6-s13-closure/phase2/t6_integrated_regression.json` |
| T7 | **DONE** | 质量/比赛 Gate 可行性评估 — 官方资产部分到达；Daily-Omni **输入路径 CONFIRMED**（修正协议：两次 prefill，首次被 system-prompt init 吞内容），但**文本输出路径损坏**（SSE 崩溃 std::bad_alloc 2/2 + 非流式无 text 字段）→ OFFICIAL_ACCURACY=BLOCKED_BY_CANDIDATE_LIMITATION；seed-tts-eval=PENDING_EXTERNAL_ASSETS（Drive 不可达）；COMPETITION_COMPLETE=NOT_CLAIMED。报告 `docs/f6-s13-closure/phase2/T7_QUALITY_GATES_ASSESSMENT.md` |
| T8 | **DONE** | 最终口径 — FINAL_INTEGRATED_CANDIDATE=FINAL（内部闭环）；OFFICIAL_ACCURACY/BENCHMARK=BLOCKED_BY_CANDIDATE_LIMITATION、COMPETITION_COMPLETE=NOT_CLAIMED（不宣称）。最终口径文档 `docs/f6-s13-closure/phase2/F6_PHASE3_FINAL_FRAMING.md` |
