# CANN Flow + Vocoder Optimization — HANDOFF

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/flow-chunk-rtf`
**HEAD:** `0828de2`
**Current Tag:** `cann-failfast-gates-pass-20260730` (RUNTIME_FIX_CHECKPOINT)
**Updated:** 2026-07-30

---

## State: RUNTIME FIX CHECKPOINT — GATE RE-EVALUATION COMPLETE — FP16 FINALIZATION IN PROGRESS

```
CURRENT TAG CLASS: RUNTIME_FIX_CHECKPOINT
  → NOT a final FP16 benchmark candidate
  → NOT an official submission candidate
  → Contains validated: aclInit guard, fail-fast mechanism, 35-restart matrix

SOLID GATES:
  P1_ACL_INIT_AUDIT         = COMPLETE
  P1_FAIL_FAST              = IMPLEMENTED (4 insertion points, 5 tracking fields)
  P2_PROCESS_RESTART        = PASS_35_OF_35

PROVISIONAL / PARTIAL (require extended evidence):
  P3_R11_RESOURCE           = PROVISIONAL_PASS_10_CYCLES → needs 110+ mixed
  P4_R6_THREAD              = PROVISIONAL_PASS → needs deadlock watchdog + stats
  P5_VIDEO_SEMANTIC         = CONDITIONAL_PASS → needs controlled video evidence
  P6_AUDIO_VIDEO_LOOP       = PASS_60_OF_60 (42 audio + 18 video)
  P6_FULL_MULTIMODAL        = PENDING → needs 6×10 matrix

PENDING FP16 GATES:
  P9_FP16_RTF_STATISTICAL   = PENDING → needs 30 matched pairs, p50/p95/CI
  P10_FP16_KV_CACHE         = PENDING → needs OFF/MISS/HIT, isolation, corruption

DATA:
  BENCHMARK_DATA            = PENDING (shallow internal only)
  EVALUATOR_CHECKPOINTS     = PENDING
```

---

## Artifact Manifest

```
HEAD                                    = 0828de2
TAG                                     = cann-failfast-gates-pass-20260730
TAG_CLASS                               = RUNTIME_FIX_CHECKPOINT

BINARY_SHA256 (llama-omni-server)       = 8c0ab2e06a009161d62665f53c86b11334338d3223506be7cb8431c40e902e68
BINARY_SHA256 (llama-omni-cli)          = 6913c972b30177fdde9700ead6863f96519c2fdf3400d25487127448cd9bcac0
BINARY_SHA256 (libomni.so)              = (pending measurement)
MODEL_SHA256 (Q4_K_M)                   = 1237a97ee081b8abebc47aa7dad565701e8f5f904cdc92f6723ac4281bbc0932

CANN_VERSION                            = 9.1.0-beta.1
NPU                                     = Ascend 910C (2× NPU, 64GB HBM each)
```

---

## Commit Chain (Recent)

```
0828de2 P1 fail-fast: aclInit lifecycle audit + CANN required backend guard
ee22811 docs: AUDIT — F0-F7 evidence reconciliation entries
95de1d2 docs: F0-F7 evidence reconciliation complete — terminology corrected, gates counted
a14aee4 docs: HANDOFF and AUDIT final — all production gates closed, tag created
a8acdf7 docs: G13 submission package final — all production gates closed
50e8483 docs: G9-G11 gates PASS — KV cache, multi-prefix, lifecycle validated
8e08db4 docs: AUDIT.md — final gate log for 2026-07-29 session
01fdf71 docs: G13 submission package — RTF 0.229, 18.4x vs CPU
767dc20 docs: G12 clean reproduction PASS — RTF 0.236 vs 0.245 original
3685050 docs: G8 1-hr stability PASS — 66 iters, 1368 WAVs
```

---

## Modified Files (uncommitted, in worktree)

```
M docs/tracking/AUDIT.md
M profiles/OFFICIAL_BENCHMARK_STATUS.md
M profiles/STATUS.md
M profiles/rope_fp16_ab/pairs.csv
?? competition/
?? profiles/BENCHMARK_DATA_INVENTORY.md
?? profiles/ACL_INIT_LIFECYCLE_AUDIT.md
?? profiles/CANN_REQUIRED_BACKEND_FAILFAST.md
?? profiles/R6_THREAD_CONTEXT_REGRESSION.md
(+ many other untracked profiles and docs)
```

---

## Current Gate Execution Plan

### Immediate (C2-C4): Resource + Thread + Multimodal

```
C2: R11 Extended Resource Lifecycle
    Target: 110+ mixed requests (20 text + 20 audio + 10 image + 10 video +
            10 video+audio + 20 TTS + 10 disconnect/recover + 10 error/recover)
    Pass: 0 unexpected failure, 0 crash, 0 deadlock, 0 CANN error, 0 CPU fallback

C3: R6 Extended Thread Context
    Target: Use C2 pressure test to verify thread ownership, context binding,
           deadlock watchdog, deferred init correctness

C4: Full 6×10 Multimodal Loop
    Target: 10 text + 10 audio + 10 image + 10 video + 10 video+audio + 10 TTS
    TTS: Reference Voice A/B isolation, repeated Voice A consistency
```

### Next (C5-C7): Video + RTF + KV

```
C5: Video Semantic Gate
    Target: Controlled video (A: RED→BLUE, B: RED+440Hz→BLUE+880Hz, C: digits)
    Evidence: frame SHA256, audio SHA256, actual payload, raw answer

C6: FP16 Strict RTF Statistical Gate
    Target: 30+ matched steady chunks, 3+ cases, baseline vs candidate
    Metrics: mean, median, p50, p90, p95, max, CV, paired diff, bootstrap CI

C7: FP16 KV Cache Real Gate
    Target: CACHE_OFF vs CACHE_MISS_REBUILD vs CACHE_HIT
    10 matched OFF/HIT pairs, A/B/C prefixes, targeted corruption
```

### Then (C8-C10): Pilot + Data + Freeze

```
C8: Shallow Benchmark Pilot (Daily-Omni, Seed-TTS, Video-MME provisional)
C9: Data + Evaluator Acquisition (ModelScope, shared drives, mirrors)
C10: FP16 Candidate Re-freeze (new tag after all gates pass)
```

---

## Three-Tier RTF Baseline (DO NOT MODIFY without matched-pair evidence)

| Tier | RTF | Config |
|------|-----|--------|
| CPU_FALLBACK_DIAGNOSTIC | ~3.97 | No CANN env vars, Q4_K_M |
| FP16_CANN_FRAMEWORK_BASELINE | **0.264** | Graph OFF, Fusion OFF |
| FP16_OPTIMIZED_CANDIDATE | **0.234** | Graph ON, Fusion ON |

---

## Key Decisions Preserved

| Decision | Status |
|----------|--------|
| ACL_GRAPH_CAPTURE | PRIMARY (-21.1% Flow) |
| ADD_LAYERNORM_FUSION | CONDITIONAL on graph ON |
| KV_CACHE | OPT_IN_READY / DEFAULT_OFF |
| IM2COL | DEFERRED (Amdahl-limited, <3%) |
| Weight format | FP16 required for competition |
| Q4_K_M | DEPRECATED for competition |

---

## Env Var Contract (VERIFIED)

```bash
export OMNI_T2W_DEVICE=cann-flow-only   # Flow Matching on CANN
export OMNI_VOC_DEVICE=gpu              # Vocoder on CANN (maps to CANN0)
```
