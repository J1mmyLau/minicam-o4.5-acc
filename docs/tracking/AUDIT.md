# 审计日志（机读）

> 追加式。格式: `## YYYY-MM-DD HH:MM | TYPE | RESULT`
> TYPE ∈ {ITER, DECISION, FAILURE, CHECKPOINT, START, STOP, PHASE}

---

## 2026-07-25 09:49 | CHECKPOINT | F005_RETRY_FALLBACK_IMPLEMENTED

- c1d2af6: retry/fallback closed loop implemented
- Detection → re-seed RNG → regenerate → if persistent + F005_FALLBACK_CPU=1 → block output
- Verified: normal recovery (token 4137), persistent block (token 6486, 30 vs 60 WAVs)
- Opt-in: F005_RETRY_ON_DEGENERATE=1, F005_FALLBACK_CPU=1, F005_MAX_RETRIES=2
- F005 status: PROTECTION_IMPLEMENTED, RECALL_LIMITED (33%), OPT_IN_READY

## 2026-07-25 09:08 | CHECKPOINT | F005_ENTROPY_THRESHOLDS

- 88da7bb: per-backend entropy thresholds (ngl8 >5.8, CPU >4.0)
- Non-static evaluation for entropy detection
- Degeneration patterns differ by backend: CPU=low-entropy/repetition, ngl8=high-entropy drift

## 2026-07-25 02:07 | CHECKPOINT | F005_DETECTOR_DEFAULTS

- ac71c59: calibrate detector defaults, fix cycle len=1 redundancy
- 3-detector suite: consecutive ≥8, cycle len 2-4, sliding-window entropy

## 2026-07-25 02:04 | CHECKPOINT | F005_ENTROPY_DETECTOR

- 5a41839: sliding-window entropy detection added
- Per-backend entropy thresholds required (CPU vs ngl8 behavior differs)

## 2026-07-25 02:02 | DECISION | CHUNKING_REJECTED

- 26fe2a8: OMNI_SIMPLEX_CHUNK_TOKENS implemented
- Chunk=20 A/B: NEUTRAL (FA -8ms, -0.2%), n=57
- Chunk=5 smoke: FA -18.6% but TTS token divergence
- VERDICT: REJECTED for current simplex workload
- Chunking A/B v4 (30 paired): confirmed NEUTRAL (FA p50 delta -8ms)

## 2026-07-24 21:42 | CHECKPOINT | F005_REPETITION_DETECTOR

- 7cb1dd9: Talker token repetition detection added
- Foundation for F005 protection infrastructure

## 2026-07-24 17:21 | CHECKPOINT | E2E_INSTRUMENTATION_FIXES

- 6a5b6c3: remove duplicate CLI dump, fix per-run directory overwrite
- 4f0ba33: per-stream_decode dump for profiling

## 2026-07-24 16:50 | PHASE | E2E_P1_INSTRUMENTATION

- d1e89db: 16-stage E2E profiler, OMNI_E2E_PROFILE=1
- Stages: request_received → llm_first_token → talker_start → ... → client_first_audio

## 2026-07-24 10:45 | PHASE | F004_PRECISION_ABLATION

- e6151fb, f53e14f, 23dcff9: F004 precision switches (FP32_RMSNORM, MATMUL_CUBE_MATH)
- ngl=8 hybrid Talker VALIDATED as PRODUCTION_CANDIDATE
- Full CANN Talker: PRODUCTION_BLOCKED (numerical divergence/collapse risk)

## 2026-07-24 06:15 | CHECKPOINT | F003_LIFECYCLE_120_PASS

- Lifecycle: 15/15 runs, 255 WAVs+7 NoSpeech, 97.3% effective TTS, 0 CANN err, 0 crash
- 7df34a1: dual-path ROPE confirmed correct
- Note: 7df34a1 is RoPE fix only; NOT standalone Talker production candidate
- Full CANN Talker later BLOCKED by F004 findings

## 2026-07-24 03:45 | CHECKPOINT | F003_CORRECTNESS_CANDIDATE

## 2026-07-23 10:38 | CHECKPOINT | F003_RUNTIME_UNBLOCKED

- Root cause: cache_ne={tsl,1,pos,1} vs dest {rope_dims,1,pos,2} dim mismatch
- Fix (prototype): unified neox+non-neox to use aclnn_repeat CANN dim=3 ×2
- Source: acl_sin_tensor(cache_ne) → Dest: {rope_dims,1,pos,1}
- Verified: 3/3 PASS, exit=0, 19 WAVs, RTF p50=0.64
- Commit: 11a6dc8 (exp/f003-neox-layout) — RUNTIME_PROTOTYPE
- Talker NPU runtime: UNBLOCKED
- CORRECTNESS: neox CONFIRMED (CPU ref adjacent-duplicate), non-neox PENDING (whole-array-repeat via memcpy)
- 7df34a1: dual-path implementation — neox(aclnn_repeat) + non-neox(memcpy)
- DO NOT MERGE to release until correctness gates pass

## 2026-07-23 06:30 | DECISION | F003_ROOT_CAUSE_CONFIRMED

- GGML_CANN_LOWERING_BUG in ROPE repeat_interleave
- output_size: total_elements (wrong) → dim_size * repeats (correct)
- Dest tensor shape: dim=3 not updated after repeat
- Minimal repro: output_size=2 PASS, output_size=128 FAIL
- Talker NPU: BLOCKED pending fix
- Evidence: D-020, /tmp/test_ri3

## 2026-07-23 05:40 | PHASE | DUAL_T2W_PROCESS_C2_PASS

- 30 concurrent batches, 60/60 tasks PASS
- NPU0 30/30, NPU1 30/30
- Infer p50=1797ms NPU0=1810ms NPU1=1776ms
- Process-level parallelism confirmed
- Evidence: phase3-pipeline/dual-instance-t2w/

## 2026-07-23 04:30 | PHASE | CANN91_COMPATIBLE

- CANN 9.1.0-beta.1 migration complete
- 20-run: 19 TTS success, 1 NO_SPEECH, RTF p50=0.56
- No code changes required
- Evidence: CANN91_REPORT.json

## 2026-07-23 04:30 | PHASE | FIRST_CHUNK_REJECTED

- OMNI_T2W_FIRST_CHUNK_SIZE=16: +38% First Audio
- Root cause: T2W needs 28-token window regardless
- Decision: REJECTED, code reverted to 3fc0ed5

## 2026-07-23 04:00 | PHASE | LEVEL2_LATENCY_DONE

- First Audio p50=1928ms: Talker 1074ms(57%), T2W 465ms(24%), Worker 426ms
- Dominant bottleneck: Talker autoregressive (28 tokens × 36ms/token)

## 2026-07-21 09:45 | PHASE | T2W_CANN_BREAKTHROUGH

- ROOT_CAUSE_CONFIRMED_THREAD_OWNERSHIP — CANN backend 线程亲和性
- Thread matrix: A=PASS, B=FAIL(ctx=NULL/device=-1), C=PASS, D=PASS
- Fix commit: 3fc0ed5 (exp/token2wav-cann-runtime)
- CLI A/B: 8 CANN + 9 CPU — FA 3.2×, RTF 7.1×, RTF=0.65 < 1.0
- OMNI_T2W_DEVICE=cann-flow-only 开关，默认不变
- Server + Dual PENDING

## 2026-07-21 07:00 | PHASE | SERVICE_BASELINE_COMPLETE

- Text C2 dual-instance: 40/40, TTFT p50=408ms
- Single-process C2: BLOCKED (1 session per process)
- Dual-instance C2 with NPU binding: PARALLEL confirmed
- WebSocket audio streaming NOT AVAILABLE (WAV server-side)
- TTS CLI: First Audio=5921ms, RTF=4.19

## 2026-07-18 05:10 | CHECKPOINT | RELEASE_READY

- FINAL_RELEASE_READY marker written
- release-artifacts/ directory complete (15 files)
- Smoke test: PASS (exit=0, 36 WAVs, WAV format verified, NaN=0, Chinese output confirmed)
- All tracking files updated: STATUS=RELEASE_READY, TASKS=ALL_DONE
- Release branch: release/final-integration (bde403d)
- Release binary SHA256: f89c6651d3f1baa21110de083263a71ac75c3f1b4308c7752243295da45acff5
- No further experiments. Ready for final delivery.

## 2026-07-18 05:02 | CHECKPOINT | RELEASE_BUILT

- release/final-integration branch built from baseline 3f7a7f0
- Binary: /workspace/llama.cpp-omni-release/build/bin/llama-omni-cli
- SHA256: f89c6651d3f1baa21110de083263a71ac75c3f1b4308c7752243295da45acff5
- Rationale: FINAL-AB showed 16-thread NUMA no gain, release uses baseline config
- All FINAL-AB artifacts archived: comparison.csv/json, conclusion.md, correctness_summary.md, binary_manifest.json, checksums.txt

## 2026-07-18 05:00 | PHASE | FINAL_AB_COMPLETE

- FINAL-AB: Baseline (8t, no NUMA) vs Optimized (16t, NUMA node0)
- 20 runs (A1-A10, B1-B10): ALL exit=0, NaN=0, Inf=0, CANN error=0
- Primary conclusion (warmed_pairs): B +0.8% ms/audio-second, +1.1% RTF, +1.3% first audio
- 16-thread NUMA optimization: NO SIGNIFICANT GAIN for Full Omni pipeline
- T2W is CPU bottleneck, not LLM; vocoder thread counts inconsistent (A=16, B=8)
- Wall timer bug (F-009): run_ab.sh Python f-string syntax error, all wall=0
- Evidence: harness/experiments/FINAL-AB/
- Next: build release/final-integration branch

## 2026-07-18 05:00 | FAILURE | F-009_WALL_TIMER_BUG
- run_ab.sh line 52: Python f-string with shell vars in single quotes
- All 20 runs recorded wall=0; recovered from file birth→mtime

## 2026-07-17 09:25 | PHASE | ALL_DONE
- TASK-030 Harness alignment: DONE (WAV 1ch/24kHz/16-bit confirmed)
- TASK-040 Final acceptance: 5/5 PASS, NaN=0, per-WAV -30% vs baseline
- ALL tasks in TASKS.md: DONE or ARCHIVED
- Session: 20260717-041023-cc-autopilot, ITER-011
- Evidence: harness/experiments/TASK-040-final-acceptance/

## 2026-07-17 | PHASE | PHASE_5_CLOSED
- All CPU T2W optimization paths exhausted (9 directions)
- Cumulative gain: -5.2% T2W (-0.37% E2E)
- Accepted: V5 (16 threads, -1.2%), EXP-006 (NUMA binding, -4.07%)
- Rejected/Archived: Q8_0 (+19.8%), OpenBLAS (neutral), CONCAT (neutral), Pipeline V3/V3-B/V4 (all)
- TASK-026 E2E Integration: 6/6 PASS
- Next: TASK-030 Harness alignment, TASK-040 Final acceptance

## 2026-07-17 | ITER | TASK-026_COMPLETE
- Cumulative E2E integration: 6/6 PASS, NaN=0

## 2026-07-17 | ITER | TASK-025_ARCHIVED
- CONCAT optimization: NEUTRAL (-0.7%)

## 2026-07-17 | ITER | TASK-024_ARCHIVED
- Q8_0 quantization: NEGATIVE (+19.8%)

## 2026-07-17 | ITER | TASK-023_DONE
- Fused QKV attention: ALREADY UPSTREAM (3f7a7f0)

## 2026-07-17 | ITER | TASK-022_DONE
- CPU per-op profiling: MUL_MAT 73-75%, CONCAT 12-14%

## 2026-07-17 | ITER | TASK-021_ARCHIVED
- OpenBLAS for T2W: NEUTRAL (+0.28%)

## 2026-07-17 | ITER | E2E_NUMA_VALIDATION_DONE
- Full Omni + NUMA: 3/3 PASS

## 2026-07-17 | ITER | V3B_CLEANUP_DONE
- V3-B worker code removed

## 2026-07-17 | ITER | EXP-006_PROD_DONE
- OMNI_T2W_CPU_AFFINITY implemented

## 2026-07-17 | ITER | E2E_REGRESSION_DONE
- Full Omni 16 threads: 2/2 PASS

## 2026-07-17 | ITER | EXP-006_DONE
- NUMA: node0 -4.07%, cluster0 -3.08%

## 2026-07-17 04:34 | ITER | COMPLETE
- iter: 002, exit: 0, tasks: V3-B, V5, BACKEND-CONFIRM

## 2026-07-17 04:10 | START | UNLIMITED_MODE
- session: 20260717-041023-cc-autopilot, HOURS=0 MAX_ITERATIONS=0

## 2026-07-17 03:46 | ITER | COMPLETE
- iter: 001, exit: 0, V3 benchmark → REJECTED

## 2026-07-17 03:21 | START | SELF_TEST
- session: 20260717-032106-cc-autopilot

## 2026-07-16 16:48 | CHECKPOINT | SESSION_END
- EXP-001, EXP-002, EXP-005A done. CPU TTS 85% E2E.

## 2026-07-16 13:44 | START | AUTONOMOUS
- session: 20260716-134420-autonomous-optimization

## 2026-07-16 13:26 | DECISION | TASK-006_DONE
- AscendC Gate NOT SATISFIED

## 2026-07-16 12:33 | DECISION | TASK-004_DONE
- 14/14 PASS

## 2026-07-16 10:44 | DECISION | PHASE_B_DONE
- 4 baselines PASS
