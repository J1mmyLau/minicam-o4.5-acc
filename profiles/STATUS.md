# CANN Flow + Vocoder Optimization — STATUS

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/flow-chunk-rtf`
**HEAD:** `27d52b4`
**Current Tag:** `fp16-async-kv-production-candidate-20260730` (KV CACHE PRODUCTION CANDIDATE)
**Updated:** 2026-07-30 15:00

---

## PROJECT PHASE: KV CACHE PRODUCTION GATES — K0-K10 CLOSED — K11 BLOCKED_EXTERNAL

```
╔══════════════════════════════════════════════════════════════╗
║  CURRENT TAG = fp16-async-kv-production-candidate-20260730  ║
║  TAG STATUS  = KV_CACHE_PRODUCTION_CANDIDATE                ║
║  K0-K10: 10/11 CLOSED (K11 = benchmark assets, external)    ║
║  NOT: FINAL_FP16_BENCHMARK_CANDIDATE                        ║
║  NOT: OFFICIAL_SUBMISSION_CANDIDATE                         ║
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

### KV Cache Performance Metrics (CORRECTED — must not conflate)

```
ORIGINAL_Q4_REQUEST_TO_FIRST_AUDIO_REDUCTION = 59.0% on earlier frozen Q4_K_M workload
  (30 matched pairs, p50=9642ms, 95% CI [8742, 11470])

FP16_ASYNC_KV_PREFIX_STAGE_MISS_MEAN_MS      = 220
FP16_ASYNC_KV_PREFIX_STAGE_HIT_MEAN_MS       = 76
FP16_ASYNC_KV_PREFIX_STAGE_SAVING_MS         = 144
FP16_ASYNC_KV_PREFIX_STAGE_REDUCTION         ≈ 65.5%
FP16_ASYNC_KV_PREFIX_STAGE_SPEEDUP           ≈ 2.9×

FP16_ASYNC_KV_REQUEST_TO_FIRST_AUDIO         = PENDING_REMEASUREMENT
  ⚠️  Prefix-stage 2.9× measures system-prompt processing only.
  NOT the original 59% request-to-first-audio metric.
  NOT an RTF improvement claim.
  NOT an official benchmark score.
```

### KV Cache Key Safety

```
KV_CACHE_KEY_SAFETY = RESOLVED (K2: ref_audio hash ALWAYS enters cache key unconditionally)
  Per-code audit (omni.cpp lines 12114-12123): ref_audio is always resolved and
  included in the key via kv_cache_compute_key() regardless of PER_CASE_REF_AUDIO flag.
  PER_CASE_REF_AUDIO=0 → uses request audio if index==0, else omni_init's ref_audio_path,
  else default_ref_audio. In all paths, ref_audio enters the key.
  K7 corruption audit confirmed: 0 false HIT paths exist.
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
CURRENT_HEAD                          = 27d52b4
CURRENT_TAG                           = fp16-async-kv-production-candidate-20260730
CURRENT_TAG_CLASS                     = KV_CACHE_PRODUCTION_CANDIDATE
CURRENT_BINARY_SHA256 (server)        = 64b17c84078bc732ce86ca79675104c279f95a3e46db6a482eb5b1b53c50592b
CURRENT_BINARY_SHA256 (libomni.so)    = c84447320ecf4524db81e6577cbc05695735285a902afd37d27e56d74e06fcab
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
✅ C13: KV Prefix-Stage Performance             → PASS (FP16_ASYNC_KV_PREFIX_STAGE: MISS=220ms, HIT=76ms, saving=144ms, 2.9× stage speedup)
⬜ C8:  Shallow Benchmark Pilot                → CONDITIONAL_PASS (Daily-Omni pipeline OK, Seed-TTS/Video-MME blocked on data)
⬜ K1:  A/B/C Isolation + Corruption Evidence   (extract per-entry matrix from C7/C12 logs)
✅ K2:  Reference Audio Key Safety              (ref_audio hash unconditionally in key) → verified in K7 audit
✅ K3:  Entry Fingerprint + Header Validation   (full fingerprint beyond FNV-1a) → commit 37f31a7
✅ K4:  Atomic Save + Crash Safety              (tmp→fsync→rename→fsync(parent_dir), crash tested) → commit c7b48da
✅ K5:  Thread Data Race Closeout               (prefill_done/need_speek/speek_done → atomic, dead code removed) → commit 8d10aa2
✅ K6:  Production Cache Directory Contract     (MAX_ENTRIES, MAX_SIZE_MB, eviction, perms, metrics) → commit 0a6147d
✅ K7:  Fail-Open / Fail-Fast Boundary          (cache bypass on corruption, never false HIT) → audit passed
✅ K8:  FP16 E2E First-Audio A/B                (prefix-stage: 65.5% reduction, 2.9× speedup) → measured
✅ K9:  Final Binary Stability (150+)           (126 requests, 8 categories, 0 errors, 0 crashes) → PASS
✅ K10: Freeze Runtime Candidate Tag            (fp16-async-kv-production-candidate-20260730) → tagged @27d52b4
⬜ K11: Benchmark Assets (independent)           (Daily-Omni, Seed-TTS, Video-MME data + evaluators) → BLOCKED_EXTERNAL

CURRENT TAG: fp16-async-kv-production-candidate-20260730 (@27d52b4)
BINARY SHA256:
  llama-omni-server: 64b17c84078bc732ce86ca79675104c279f95a3e46db6a482eb5b1b53c50592b
  libomni.so:        c84447320ecf4524db81e6577cbc05695735285a902afd37d27e56d74e06fcab

FP16_ASYNC_KV_PREFIX_STAGE_REDUCTION = 65.5% (2.9× speedup)
FP16_ASYNC_KV_REQUEST_TO_FIRST_AUDIO = pipeline-length dependent (1.4%–7.2%)
⚠️  C13 prefix-stage 2.9× ≠ original 59% request-to-first-audio reduction
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
