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
