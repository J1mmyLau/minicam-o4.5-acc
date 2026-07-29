# CANN Flow + Vocoder Optimization — STATUS

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/flow-chunk-rtf`
**HEAD:** `7f5f349` (P15-C: CANN Flow msprof — Im2col 42%, kernel launch overhead 73%)
**Updated:** 2026-07-29 14:00 UTC
**Competition Metric:** PER-CHUNK RTF = 0.274

---

## BREAKTHROUGH STATUS

```
CANN_FLOW       = INTEGRATION_CANDIDATE  (24.1× speedup, 3,726→155ms)
CANN_VOCODER    = INTEGRATION_CANDIDATE  (2.92× speedup, 348→119ms)
COMBINED_INTERNAL_STEADY_RTF ≈ 0.274    (n=65, 5 independent batches)
PRODUCTION_READY  = NO                  (Phase 2 gates pending)
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

## Future Work (Next Session)

### Phase 1: Freeze Complete (CURRENT)
- ✅ Evidence manifest + SHA256SUMS
- ✅ 4 audits complete
- ✅ Checkpoint files updated
- ⬜ Git tag + commit all docs

### Phase 2: Production Gates (NEXT SESSION)
- Internal audio correctness (blind A/B listening)
- First/warmup/steady/tail chunk characterization
- Demo smoke test
- 30min + 1hr stability
- KV Cache HIT/MISS/OFF regression
- Multi-prefix + T2W lifecycle

### Phase 3: Further Optimization
- Flow graph execution reuse (launch overhead #1 target)
- Im2col fusion
- Custom AscendC Kernel
