# 审计日志（机读）

> 追加式。格式: `## YYYY-MM-DD HH:MM | TYPE | RESULT`
> TYPE ∈ {ITER, DECISION, FAILURE, CHECKPOINT, START, STOP, PHASE}

---

## 2026-07-25 16:15 | CHECKPOINT | P0_TERMINOLOGY_TIGHTENED_P7.1_TRACE

- P0: Metric names corrected. decode_to_first_audio_ms (was "FA"), prefill_start_to_first_audio_ms (was "total"), request_to_first_audio_ms (NOT YET MEASURED)
- P0: Race language tightened. "No statistically detectable association in current sample (Fisher p=0.56, n=15)" replaces "race not related to KV cache"
- P7.1 full trace: P7_T2W_LIFECYCLE_TRACE.md. Root cause: omni_free() join order + t2w exit on (!running && queue.empty())
- P6_METRIC_BOUNDARY_AUDIT.md copied into repo at docs/experiments/e2e-ngl8/
- Next: P2 T2W drain fix → P3 regression tests → P4 request_to_first_audio instrumentation → P5 supplemental A/B

## 2026-07-25 16:15 | CHECKPOINT | P7.1_P7.2_COMPLETE

- P7.1 T2W race root cause: omni_stop_threads() kills T2W before first WAV for short responses
- NOT caused by KV cache (identical error pattern both arms, Fisher p=0.56)
- P7.2 Metric boundary: FA clock starts INSIDE stream_decode(), AFTER stream_prefill() returns
- Prefill and FA are SEQUENTIAL, NON-OVERLAPPING stages
- FA excludes prefill by code design → FA is WRONG metric for KV cache evaluation
- Correct metric: TOTAL = prefill + FA = p50 14822→6114ms (-58.8%)
- Report: e2e-ngl8/p6-ab/P6_METRIC_BOUNDARY_AUDIT.md
- Next: P7.3 targeted pair completion after T2W fix

## 2026-07-25 16:00 | DECISION | P6_VERDICT_CORRECTED

- f54cc23 claimed ACCEPTED/production-default-enable. INCORRECT. Corrected below.
- Corrected verdict: EXPERIMENT_COMPLETED / GATE_INCONCLUSIVE
- KV_CACHE_REUSE_FUNCTIONAL=PASS, PREFILL_REDUCTION=MEASURED
- FIRST_AUDIO_BENEFIT=INCONCLUSIVE (CI crosses zero, aggregate p50 +436ms favoring A)
- T2W_STABILITY=NOT_PASSED (25% invalid rate, 15 races)
- PRODUCTION_DEFAULT_ENABLE=NOT_APPROVED, PRODUCTION_OPT_IN=CANDIDATE
- P7.1 T2W race root cause: omni_stop_threads() kills T2W before first WAV for short responses
- NOT caused by KV cache (identical error pattern both arms, p=0.56 Fisher)
- Next: P7.2 metric boundary audit, P7.3 targeted pair completion
- KV cache remains DEFAULT_OFF until all criteria met

## 2026-07-25 15:46 | DECISION | P6_KV_CACHE_REUSE_ACCEPTED [OVERTURNED — see 16:00]

- 46023f0: KV cache reuse formal A/B complete
- 72 executions (36A+36B), 54 valid (A=28, B=26), 18 invalid (15 T2W race, 3 timeout)
- All B-arm executions: cache_hit=1, reused=62 ✅
- Prefill: 9064 → 2.7 ms (99.97% reduction)
- FA: median delta -127 ms, Bootstrap 95% CI [-1435, 341] ms — crosses zero (FA is LLM-dominated)
- 0 CANN errors, 0 degeneration, 0 retry in both arms
- VERDICT: ACCEPTED — enable OMNI_KV_CACHE_REUSE=1 as default for production multi-turn
- Report: e2e-ngl8/p6-ab/P6_KV_CACHE_REUSE_RESULT.md
- Post-E2E Mission: COMPLETE (P1-P6 all done)

## 2026-07-25 12:45 | CHECKPOINT | P6_PRE_COMPACT

- P1-P5 ALL DONE. P4 KV cache reuse implemented (7ce501d).
- P6 first A/B attempt: ALL INVALID (rc=124 timeout, insufficient pairs 18A+18B).
- Next: P6.0 smoke verify cache hit → P6.2-P6.7 formal 8-pass A/B with background runner.
- Full plan in NEXT_ACTION.md.
- Compact checkpoint. No lingering processes. NPU idle.

## 2026-07-25 12:30 | CHECKPOINT | P4_KV_CACHE_REUSE_IMPLEMENTED

- 7ce501d: KV cache reuse for static system prompt prefix
- Mechanism: llama_state_seq_save_file after first system prompt prefill,
  llama_state_seq_load_file + pos_max fallback on subsequent runs
- Gate: OMNI_KV_CACHE_REUSE=1 (default off), simplex test/batch mode only
- Verified: cache HIT (62 tokens loaded, 9.1MB, FA 4342ms), cache MISS (normal),
  default off (no interference)
- E2E time: 13.2s → 4.3s (-67%) for warm backend
- Cache file: /tmp/omni_kvcache_<model_hash>.bin
- Next: P6 formal A/B test (≥30 paired requests, ABBA/BAAB)

## 2026-07-25 12:15 | CHECKPOINT | P3_REVERIFY_DONE_P4_START

- 03de7e0: file-level F005 retry stats committed
- P3 re-verify: CPU normal run (5 chunks, 0 degen, 0 retries), stats print correctly
- F005/STATUS.md updated to reflect corrected state
- Next: P4 KV cache reuse design + implementation

## 2026-07-25 12:10 | CHECKPOINT | P1_F005_PRODUCTION_HARDENING_DONE

- 9336e1d: P1.1-P1.5 fixes (CPU entropy disabled, F005_FALLBACK_CPU→F005_BLOCK_ON_DEGENERATE, misleading log fixed, WAV cleanup, retry stats)
- P2 per-detector confusion matrix generated from n=32 existing data
- Cycle: 0 FP → DEFAULT_ON candidate. Consecutive: 1 borderline FP → threshold →10
- SUSTAINED + DOMINANT: 0 FP on diag, untriggered in P2 batch (drift stochastic)
- Report: f005/P2_DETECTOR_CONFUSION_MATRIX.md
- Next: P3 re-verify closed-loop → P4 KV cache reuse implementation

## 2026-07-25 11:55 | DECISION | STATE_CORRECTION_USER_AUDIT

- P1→DONE, P2→VALIDATION_DONE_GATE_FAILED, P3→ANALYSIS_DONE_IMPLEMENTATION_INCOMPLETE
- P4→PROVISIONAL_POLICY, P5→DONE, P6→NOT_DONE
- POST-E2E MISSION: NOT COMPLETE (was incorrectly marked)
- Critical: CPU entropy 100% FP, F005_FALLBACK_CPU misleading, no per-detector matrix
- Next: F005 PRODUCTION HARDENING (P1.1-P1.5) → Per-detector evaluation (P2) → KV cache A/B

## 2026-07-25 11:50 | CHECKPOINT | P5_P6_LLM_BOTTLENECK_DONE

- P5: LLM = 70% FA (prefill+boot 33.4% + decode→speak 36.5%)
- Talker TTS = 22.8%, T2W = 6.5%
- P6: 4 candidates (A: KV cache -26% FA P0, B: prefill batch verify-first, C: scheduler P2, D: sync P2)
- E (speak-token) and F (NUMA) REJECTED (already optimal / previously tested)
- Reports: e2e-ngl8/P5_LLM_BOTTLENECK_DECOMPOSITION.md, P6_LLM_OPTIMIZATION_CANDIDATES.md
- POST-E2E MISSION: ALL COMPLETE (P0-P6)

## 2026-07-25 11:45 | DECISION | P4_F005_PRODUCTION_POLICY

- Cycle detector: PRODUCTION_VALIDATION_CANDIDATE (0 FP, default-on)
- Cons8: SEVERE_LOOP_GUARD (1 borderline FP, default-on after ngl8 threshold →10)
- Entropy CPU 4.0: REJECTED_FOR_DEFAULT_ENABLE (100% FP epidemic, P3-proven)
- Entropy ngl8 5.8: OUTPUT_GUARD_ONLY (too conservative)
- SustainedEntropy: SEVERE_LOOP_GUARD for ngl8 (0 FP, default-on)
- DomTokCollapse: SEVERE_LOOP_GUARD for ngl8 (0 FP, default-on)
- F005_FALLBACK_CPU rename to F005_BLOCK_ON_DEGENERATE recommended
- 3/5 detectors ready for default-enable
- Report: f005/P4_PRODUCTION_POLICY.md
- Next: P5 LLM 69% bottleneck decomposition

## 2026-07-25 11:40 | CHECKPOINT | P3_F005_RETRY_FALLBACK_VERIFIED

- Retry mechanism: ✅ correct (re-seed XOR golden ratio, re-generate, re-check)
- F005_FALLBACK_CPU: ❌ blocks output, does NOT switch to CPU (misleading name)
- Retry efficacy: 0% with CPU entropy 4.0 (false positive epidemic, not a retry bug)
- Normal-case overhead: 0% (ngl8 case 0003, 0 F005 events)
- 5 issues found: misleading messages (I1, I2), CPU threshold FP (I3), WAV artifacts (I4), no retry stats (I5)
- Report: f005/P3_RETRY_FALLBACK_REPORT.md
- Next: P4 production policy decision

## 2026-07-25 11:35 | CHECKPOINT | P2_F005_FORMAL_VALIDATION_DONE

- a893824: --test-start CLI flag for individual test case selection
- 22 P2 batch + 10 diag = 32 runs, recall 68.8%, FP 6.3%
- ngl8-type drift stochastic, not reproduced in P2 batch
- CPU entropy 4.0 threshold causes log spam (169-375 repeated detections)
- Report: f005/P2_VALIDATION_REPORT.md
- Next: P3 retry/fallback closed-loop verification

## 2026-07-25 11:10 | CHECKPOINT | P1_F005_RECALL_IMPROVEMENT_DONE

- 08afb84: two new detectors (SustainedHighEntropy + DominantTokenCollapse)
- Miss mode classification: CPU=low-entropy repetition (covered), ngl8=high-entropy drift + token proliferation (NEW)
- Offline validation: 10 F005 diag runs, 0 FP, 3/4 degenerate caught
- Report: f005/MISS_MODE_REPORT.md
- Next: P2 F005 formal validation

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
## 2026-07-25 16:52 | P7.3-IMPLEMENT | P2-P8 DRAIN_FIX + P10 INSTRUMENT DONE, P9 REGRESSION RUNNING
