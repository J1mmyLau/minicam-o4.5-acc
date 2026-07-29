# CANN Flow + Vocoder Optimization — STATUS

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/flow-chunk-rtf`
**HEAD:** `6154b85` (Phase 3 FREEZE — graph capture + fusion)
**Tag candidate:** `cann-flow-vocoder-aclgraph-rtf0229-20260729`
**Updated:** 2026-07-29 12:45 UTC

---

## COMPETITION METRIC

```
Per-Chunk RTF = (flow_compute + vocoder_compute) / audio_duration_ms

CPU baseline:                 RTF ≈ 4.21
Phase 2 (CANN Flow+Vocoder):  RTF ≈ 0.274
Phase 3 (+ACL Graph+Fusion):  RTF ≈ 0.229

Total speedup vs CPU:  18.4×  (4.21 / 0.229)
Phase 3 relative:      -16.4% ((0.274 - 0.229) / 0.274)
```

---

## PHASE 3 FREEZE STATUS

```
CANN_FLOW                  = INTEGRATION_CANDIDATE  (24.1×, 3,726→155→111ms)
CANN_VOCODER               = INTEGRATION_CANDIDATE  (2.92×, 348→119ms)
ACL_GRAPH_CAPTURE          = INTEGRATION_CANDIDATE  (RELAXED mode, Flow n_nodes=11740)
ADD_LAYERNORM_FUSION       = WEAK_POSITIVE_INTEGRATED  (~1ms, 257 pairs)

COMBINED_STEADY_RTF        ≈ 0.229  (n=29, 4 test cases)
PHASE3_CANDIDATE_FROZEN    = YES
OFFICIAL_SCORE             = NOT_AVAILABLE
BENCHMARK_GATE             = PENDING
DEMO_GATE                  = PENDING
STABILITY_GATE             = PENDING
CLEAN_MACHINE_GATE         = PENDING
```

**Explicitly NOT declared:**
- ❌ PRODUCTION_READY
- ❌ OFFICIAL_RTF
- ❌ FULLY_OPTIMIZED
- ❌ GUARANTEED_18X

---

## Phase 3 Technical Summary

### Rank 1: ACL Graph Capture (PRIMARY GAIN)

| Change | Detail |
|--------|--------|
| Capture mode | `ACL_MODEL_RI_CAPTURE_MODE_RELAXED` (avoids H2D interference) |
| Stream sync | `aclrtSynchronizeStream` before capture begin |
| Min nodes filter | `GGML_CANN_GRAPH_MIN_NODES=100` (skips LLM decode tokens) |
| LRU cache | Capacity 12, per-context isolation |

**Result:** Flow t2m.compute **154.9ms → 111.3ms mean (-28.2%, -43.6ms)**
Flow graph (n_nodes=11740): 1 capture → 19+ cache HITs across all test cases.

### Rank 2: ADD+NORM Fusion (SECONDARY, DIMINISHING RETURNS)

| Change | Detail |
|--------|--------|
| Fused op | `aclnnAddLayerNorm` for ADD + NORM (LayerNorm) |
| Pairs fused | 257 in Flow graph (n_nodes=11740) |
| Gain | ~1ms → graph capture already reduces launch overhead |

---

## Phase History

| Phase | Status | Key Result |
|-------|--------|------------|
| P0-P12: CANN Vocoder | COMPLETE ✅ | 2.92× local, INTEGRATION_CANDIDATE |
| P13-P15: CANN Flow | COMPLETE ✅ | 24.1× speedup, BREAKTHROUGH |
| Phase 1: Freeze | COMPLETE ✅ | Tag: `cann-flow-vocoder-rtf027-20260729` |
| Phase 2: Production Gates | COMPLETE ✅ | All 7 gates PASS (1 deferred) |
| **Phase 3: Optimization** | **FROZEN ✅** | **RTF 0.229, 18.4× vs CPU** |

---

## Next Session: Gate Sequence

1. Restore Phase 3 candidate tag
2. Graph Capture correctness extended tests (10 boundary conditions)
3. First / warmup / steady / tail chunk statistics
4. Official Benchmark harness audit
5. Demo full validation
6. 30-min + 1-hr stability
7. KV Cache HIT/MISS/OFF regression
8. Multi-prefix + corruption
9. T2W lifecycle
10. Clean-machine reproduction
11. Submission package
12. Im2col ONLY if all gates pass AND wall-time benefit ≥ 3%

---

## Document Inventory

| Document | Status |
|----------|--------|
| `PHASE3_PERFORMANCE_RECONCILIATION.md` | COMPLETE |
| `ACL_GRAPH_CAPTURE_CORRECTNESS_AUDIT.md` | INITIAL (10 tests pending) |
| `PHASE3_EVIDENCE_MANIFEST.md` | COMPLETE |
| `P19_GRAPH_EXECUTION_REUSE.md` | COMPLETE |
| `P16-P18` (Phase 2 gates) | COMPLETE |
| `STATUS.md` | Updated |
| `HANDOFF.md` | Updated |
