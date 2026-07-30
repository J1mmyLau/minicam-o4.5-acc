# CANN Flow + Vocoder Optimization — STATUS

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/flow-chunk-rtf`
**HEAD:** `0828de2`
**Current Tag:** `cann-failfast-gates-pass-20260730` (RUNTIME_FIX_CHECKPOINT — NOT a final benchmark candidate)
**Updated:** 2026-07-30

---

## CORRECTED PROJECT PHASE: RUNTIME FIX CHECKPOINT — EVIDENCE GAPS IDENTIFIED — FP16 MULTIMODAL FINALIZATION IN PROGRESS

```
╔══════════════════════════════════════════════════════════════╗
║  CURRENT TAG = cann-failfast-gates-pass-20260730             ║
║  TAG STATUS  = RUNTIME_FIX_CHECKPOINT                       ║
║  NOT: FINAL_FP16_BENCHMARK_CANDIDATE                        ║
║  NOT: OFFICIAL_SUBMISSION_CANDIDATE                         ║
║  NOT: ALL_GATES_PASS                                        ║
╚══════════════════════════════════════════════════════════════╝
```

---

## CORRECTED GATE STATUS MATRIX (2026-07-30 re-evaluation)

### Solid Gates (evidence sufficient)

```
P1_ACL_INIT_LIFECYCLE_AUDIT              = COMPLETE  (10/10 Q answered)
P1_FAIL_FAST_MECHANISM                   = IMPLEMENTED (4 insertion points, 5 tracking fields)
P1_CANN_IS_AVAILABLE_API                 = IMPLEMENTED (ggml_backend_cann_is_available())
P2_PROCESS_RESTART_MATRIX                = PASS_35_OF_35 (7 modes × 5 cycles, 0 CANN re-init failures)
```

### Provisional / Partial Gates (evidence insufficient for PASS)

```
P3_R11_RESOURCE_LIFECYCLE                = PROVISIONAL_PASS_10_CYCLES
  Reason: Only 10 omni_init→free cycles. No coverage of 100+ mixed requests,
          disconnect/reconnect, TTS variety, Graph replay lifecycle.

P4_R6_THREAD_CONTEXT                     = PROVISIONAL_PASS
  Reason: Thread topology + deferred init confirmed, but no independent
          high-pressure mixed-request stats, no deadlock watchdog.

P5_VIDEO_SEMANTIC                        = CONDITIONAL_PASS
  Reason: Pipeline functional (extraction→prefill→decode→WAV), 3/3 tests succeed.
          Visual temporal understanding not yet demonstrated.
          Model quality issue, NOT infra failure.

P6_AUDIO_VIDEO_LOOP                      = PASS_60_OF_60
  Reason: 42 audio + 18 video samples, 0 failures, median 7487ms, 0 CANN errors.
          Valid partial evidence for audio+video stability.

P6_FULL_MULTIMODAL_LOOP                  = PENDING
  Reason: 6-category matrix (text/audio/image/video/video+audio/TTS) NOT executed.
          Need: 10× each category = 60 samples.

P9_FP16_RTF                              = SMOKE_CONFIRMED
  Reason: "Range consistent" confirmed. No 30 matched steady chunks,
          no p50/p95, no CI, no formal baseline-vs-candidate paired comparison.

P9_FP16_RTF_STATISTICAL_GATE             = PASS (C6: 140 chunks, -7.8% mean, 2.6× CV, CI [-25,-13]ms)
  Reason: Need: baseline warmup, candidate warmup, 30+ matched chunks,
          3+ cases, per-chunk breakdown, p50/p90/p95/CV/bootstrap CI.

P10_FP16_KV_CACHE                        = NOT_SUFFICIENTLY_TESTED
  Reason: "Audio output OK, no KV errors" proves nothing about:
          CACHE_OFF vs CACHE_MISS_REBUILD vs CACHE_HIT,
          key isolation, corruption recovery, unrelated entry retention,
          request-to-first-audio comparison.

P10_FP16_KV_CACHE_FINAL_GATE             = PASS (C7: 9/9 OK, 3 keys, corruption→rebuild, isolation verified, fix in omni.cpp)
  Reason: Need: OFF/MISS/HIT with matched pairs, A/B/C prefixes,
          targeted corruption, rebuild verification, first-audio benefit.

P11_CURRENT_TAG                          = RUNTIME_FIX_CHECKPOINT
  Reason: Tag cann-failfast-gates-pass-20260730 is a runtime fix checkpoint.
          NOT a final FP16 multimodal benchmark candidate.
```

### Pending Gates

```
R11_RESOURCE_LIFECYCLE_GATE              = CONDITIONAL_PASS (C2: 120/120 OK, 0 crash, RSS growth=TTS+glibc pattern)
R6_CANN_THREAD_CONTEXT_GATE              = AUDITED (C6: LLM single-owner ✅, TTS/T2W dual-owner ⚠️, join-order correct, no formal state machine)
FP16_FULL_MULTIMODAL_LOOP_PASS           = PASS (C4: 60/60 across 6 categories, 0 failures)
VIDEO_PIPELINE_GATE                      = PASS (C5: 3 controlled videos, extraction→prefill→decode→WAV confirmed)
VIDEO_REASONING_QUALITY                  = CONDITIONAL (model visual reasoning TBD, not infra issue)
FP16_RTF_STATISTICAL_GATE                = PASS (C6: 140 chunks, -7.8% mean, 2.6× CV, CI [-25,-13]ms)
FP16_KV_CACHE_GATE                       = PASS (C7: 9/9 OK, 3 keys, corruption→rebuild, isolation verified)
FP16_CLEAN_BUILD_PASS                    = PASS (llama-omni-server + libomni.so built 2026-07-30)
```

### Data / External

```
BENCHMARK_DATA_ACCESS                    = PENDING (shallow internal data available; official dataset needs download)
EVALUATOR_CHECKPOINT_ACCESS              = PENDING (Whisper/Paraformer/WavLM — separate scoring machine OK)
P12_DATA_INVENTORY                       = COMPLETE (BENCHMARK_DATA_INVENTORY.md)
```

---

## EXPLICITLY FORBIDDEN LABELS (DO NOT USE)

```
ALL_RUNTIME_GATES_PASS
FINAL_FP16_CANDIDATE_FROZEN
BENCHMARK_LOOP_READY
LOCAL_INFRASTRUCTURE_FULLY_OPERATIONAL
ALL_PRODUCTION_GATES_CLOSED
PRODUCTION_READY
OFFICIAL_SUBMISSION_PASS
```

---

## Three-Tier RTF Summary

| Tier | RTF | Flow | Vocoder | Config |
|------|-----|------|---------|--------|
| **CPU_FALLBACK_DIAGNOSTIC** | ~3.97 | CPU | CPU | No CANN env vars; Q4_K_M |
| **FP16_CANN_FRAMEWORK_BASELINE** | **0.264** | 0.146 | 0.118 | CANN Flow/Vocoder ON; Graph OFF; Fusion OFF |
| **FP16_OPTIMIZED_CANDIDATE** | **0.234** | 0.115 | 0.119 | CANN Flow/Vocoder ON; Graph ON; Fusion ON |

All RTF values are uniform per-chunk mean. See `FP16_RTF_METRIC_RECONCILIATION.md`.

---

## Current Artifacts

```
CURRENT_HEAD                          = 0828de2
CURRENT_TAG                           = cann-failfast-gates-pass-20260730
CURRENT_TAG_CLASS                     = RUNTIME_FIX_CHECKPOINT
CURRENT_BINARY_SHA256 (server)        = 8c0ab2e06a009161d62665f53c86b11334338d3223506be7cb8431c40e902e68
CURRENT_BINARY_SHA256 (cli)           = 6913c972b30177fdde9700ead6863f96519c2fdf3400d25487127448cd9bcac0
CURRENT_MODEL_Q4_K_M_SHA256           = 1237a97ee081b8abebc47aa7dad565701e8f5f904cdc92f6723ac4281bbc0932
CURRENT_WORKTREE                      = /workspace/llama.cpp-omni-operator
CURRENT_BRANCH                        = perf/flow-chunk-rtf
```

---

## Q4_K_M Internal (NOT competition — QUANTIZED_WEIGHT_INTERNAL_ONLY)

```
INTERNAL_PERFORMANCE_GATE         = PASS  (Q4_K_M)
INTERNAL_DEMO_GATE                = PASS  (Q4_K_M)
INTERNAL_STABILITY_GATE           = PASS  (Q4_K_M)
CLEAN_REPRODUCTION_GATE           = PASS  (Q4_K_M)
KV_CACHE_FUNCTIONAL_GATE          = PASS  (Q4_K_M)
MULTI_PREFIX_AND_CORRUPTION       = PASS  (Q4_K_M)
T2W_LIFECYCLE                     = PASS  (Q4_K_M)
```

---

## FP16 Modality Gates

```
FP16_CANN_MODEL_LOAD              = CONFIRMED (HBM 17-18%, ~22 GB)
FP16_CANN_LLM_DECODE              = CONFIRMED (Aicore 25-36%, NPU 44-48%)
FP16_TEXT_AUDIO_SMOKE             = PASS
FP16_IMAGE_GATE                   = PASS
FP16_IMAGE_AUDIO_GATE             = PASS
FP16_TTS_SMOKE                    = SMOKE_PASS
FP16_TTS_FLOW_CANN                = CANN_REACHABLE
FP16_TTS_VOCODER_CANN             = CANN_REACHABLE
FP16_TTS_EOS_DRAIN                = PASS
```

---

## Next Execution Order

```
✅ C2:  R11 Resource Lifecycle Extended Gate   → CONDITIONAL_PASS (120/120)
✅ C3:  R6 Thread Context Extended Gate        → DEFERRED (C6 audit pending)
✅ C4:  Full 6×10 Multimodal Loop              → PASS (60/60)
✅ C5:  Video Semantic Gate                    → PIPELINE_PASS + REASONING_CONDITIONAL
✅ C6:  FP16 Strict RTF Statistical Gate       → PASS (140 chunks, -7.8%)
✅ C7:  FP16 KV Cache Real Gate                → PASS (9/9, 3 keys)
✅ C4:  KV Cache Boundary Audit               → COMPLETE (10/10 Q answered, docs/tracking/C4_KV_CACHE_BOUNDARY_AUDIT.md)
✅ C6:  Thread Ownership Audit                 → COMPLETE (dual-owner TTS/T2W found, docs/tracking/C6_THREAD_OWNERSHIP_AUDIT.md)
✅ C12: Thread Lifecycle Regression            → PASS (60/60: 20 HIT + 10 MISS + 10 SWITCH + 5 CORRUPT + 10 TTS + 5 DISCON)
✅ C13: KV Performance Comparison              → PASS (2.9× speedup: 220ms MISS→76ms HIT, 15+15 matched pairs)
⬜ C8:  Shallow Benchmark Pilot                → CONDITIONAL_PASS (Daily-Omni pipeline OK, Seed-TTS/Video-MME blocked on data)
⬜ C9:  Data + Evaluator Acquisition           (ModelScope, shared drives, mirrors)
⬜ C10: FP16 Candidate Re-freeze               (new tag after all above pass)
⬜ C14: Split Commits                          (fix + test + docs, not mixed)
```

---

## Document Inventory

| Document | Status |
|----------|--------|
| `STATUS.md` | UPDATED (2026-07-30) — Corrected gate statuses, evidence gaps documented |
| `HANDOFF.md` | UPDATED (2026-07-30) — Runtime checkpoint handoff |
| `NEXT_ACTION.md` | UPDATED (2026-07-30) — Next execution targets |
| `AUDIT.md` | Appended (2026-07-30) — Gate re-evaluation checkpoint |
| `BENCHMARK_DATA_INVENTORY.md` | COMPLETE |
| `ACL_INIT_LIFECYCLE_AUDIT.md` | COMPLETE |
| `CANN_REQUIRED_BACKEND_FAILFAST.md` | COMPLETE |
| `R6_THREAD_CONTEXT_REGRESSION.md` | COMPLETE |
| `FP16_RTF_METRIC_RECONCILIATION.md` | COMPLETE |
| `FP16_RTF_MATCHED_PAIRS.csv` | COMPLETE |
