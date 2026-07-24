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
| T2W-CANN-STRICT-AB | **PASS** | 5-rnd paired: p50 -48%, p90 -67%, mean -51%, FirstAudio -22% |
| T2W-CANN-TAIL-LATENCY | **RESOLVED** | earlier p90 "regression" was gap-filter artifact; CANN p90=484ms < CPU 1487ms |
| T2W-CANN-WAV-COMPARE | **PASS** | 10 pairs: comparable dur/peak/RMS/ZCR; CANN trail_sil higher (TTS variation) |
| T2W-CANN-RESTART | **PASS** | 3x3 + 2 lifecycle runs, all exit 0 |
| T2W-CANN-LIFECYCLE | **PARTIAL** | 2 full runs + 1 partial (timeout), 0 CANN err; 120-task pending |
| T2W-CANN-ASR | **UNAVAILABLE** | no whisper/funasr/transformers |
| T2W-CANN-AUDIO-HUMAN | **FAIL (F003)** | F003 blind listening failed; new issue found |
| F003-ROPE | **FIXED** | 7df34a1 — neox+non-neox RoPE runtime/layout correct |
| F004-CANN-REPETITION | **MITIGATED** | ngl=8 hybrid: 0% collapse, -14% FA, human listening PASS |
| F004-NGL8-HYBRID | **VALIDATED** | hybrid-talker-ngl8-candidate-20260724 |
| F005-COMMON-AUDIO | **OPEN** | CPU 4/20 + ngl8 2/20 unintelligible — NOT backend-specific |
| FULL-CANN-TALKER | **BLOCKED** | systemic FP16 precision divergence |
| TALKER-CANN-PRODUCTION | **HYBRID_CANDIDATE** | ngl=8 ready; full CANN blocked |
| T2W-CANN-AUDIO | **PENDING** | 音质验证 |
| T2W-CANN-LIFECYCLE | **PENDING** | 120 任务长稳 |

## FINAL STATUS

Release: bde403d（冻结）。Candidate: 3fc0ed5。F-003 根因确认，待修复。
