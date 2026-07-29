# CANN Flow + Vocoder Optimization — STATUS

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/flow-chunk-rtf`
**HEAD:** `4a2cbcd` (P19: CANN ACL graph capture — t2m.compute -23.1%)
**Updated:** 2026-07-29 10:45 UTC
**Competition Metric:** PER-CHUNK RTF = 0.229 (vs 0.274 baseline)

---

## BREAKTHROUGH STATUS

```
CANN_FLOW       = INTEGRATION_CANDIDATE  (24.1× speedup, 3,726→155ms→111ms with graph)
CANN_VOCODER    = INTEGRATION_CANDIDATE  (2.92× speedup, 348→119ms)
COMBINED_INTERNAL_STEADY_RTF ≈ 0.229    (n=16+ steady, with CANN ACL graph capture)
PRODUCTION_READY  = NO                  (Phase 2 gates pass, Phase 3 in progress)
OFFICIAL_RTF      = NOT_AVAILABLE       (external validation pending)
GUARANTEED_15×    = NO                  (pending external benchmark)
```

---

## Phase Status

| Gate | Status | Key Finding |
|------|--------|-------------|
| P0-P12: CANN Vocoder optimization | COMPLETE | 2.92× local, 7.0% total T2W. INTEGRATION_CANDIDATE |
| P13: Flow architecture audit | COMPLETE | Conformer encoder + 16-block ODE DiT, 11,740-node ggml graph |
| P14: Flow canonical baseline | COMPLETE | CPU Flow 3,723ms steady (p50=3,644ms), CV=0.047 |
| P15: Flow CANN discovery | COMPLETE | BREAKTHROUGH: `cann-flow-only` → 24.1× speedup |
| P15-A: Correctness | COMPLETE | 60/60 wavs valid, 0 silence, 0 clipping |
| P15-B: Stability | COMPLETE | 5 batches, 68 steady chunks, 0 failures, RTF=0.274 |
| P15-C: msprof profiling | COMPLETE | Im2col 42% NPU, launch overhead 72% Flow wall |
| BREAKTHROUGH_CHECKPOINT | **IN PROGRESS** | 4 audits complete, writing evidence manifest + checkpoint files |

---

## 4 Completed Audits

| Audit | Document | Status |
|-------|----------|--------|
| 1. Number reconciliation | `PERFORMANCE_NUMBER_RECONCILIATION.md` | ✅ 24.1×/2.92×/14.8× corrected |
| 2. Reachability audit | `FLOW_CANN_REACHABILITY_AUDIT.md` | ✅ Path confirmed, fallback=0 |
| 3. Env semantics | `CANN_BACKEND_ENV_SEMANTICS.md` | ✅ `gpu`→CANN mapping documented |
| 4. Profile percentage audit | `FLOW_PROFILE_PERCENTAGE_AUDIT.md` | ✅ Im2col 42% ≠ launch overhead 73% |

---

## Competition Metric

```
Per-Chunk RTF = (flow + vocoder) / audio_duration_ms
              = (154.9 + 119.1) / 1000.0
              = 0.2740 (mean, n=65 steady)
              = 0.2737 (median, n=65 steady)
```

---

## Future Work

### Phase 1: Freeze Complete ✅
- ✅ Evidence manifest + SHA256SUMS
- ✅ 4 audits complete
- ✅ Checkpoint files updated
- ✅ Git tag `cann-flow-vocoder-rtf027-20260729`

### Phase 2: Production Gates ✅ (ALL PASS)
- ✅ Demo smoke: 16 WAVs, RTF=0.28
- ✅ Bucket characterization: steady RTF=0.261
- ✅ KV Cache regression: HIT/MISS/OFF all compatible
- ✅ 30min stability: 59/59 PASS, 302 WAVs
- ✅ T2W lifecycle L2-L6: rapid 5/5, coverage via stability
- ✅ 1hr stability: 118/118 PASS, 594 WAVs
- ⏭️ Multi-prefix: deferred to KV cache branch

### Phase 3: Further Optimization (CURRENT)

| Rank | Task | Status | Impact |
|------|------|--------|--------|
| 1 | Graph execution reuse | ✅ DONE (P19) | t2m.compute -23.1%, 34ms savings per chunk |
| 2 | Operator fusion | ✅ DONE (P20) | ADD+NORM fusion implemented (257 pairs). ~1ms gain: diminishing returns with graph capture |
| 3 | Im2col custom kernel / FusedCausalConv1d | ⚡ NEXT | 5-8ms est. `aclnnFusedCausalConv1d` exists in CANN 9.1 |
| 4 | Async H2D/D2H | PENDING | 1-2ms est. |

**Rank 1 results:**
- ACL capture mode: RELAXED (avoids H2D interference)
- t2m.compute: 144.0ms → 110.8ms p50 (-23.1%)
- Per-chunk RTF: 0.250 → 0.229 (-8.4%)
- Flow graph reuse: 1 capture → 19+ cache HITs
- Config: `GGML_CANN_ACL_GRAPH=on`, `GGML_CANN_GRAPH_MIN_NODES=100`
