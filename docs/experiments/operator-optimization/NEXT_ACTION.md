# NEXT ACTION — CANN Vocoder → Flow Model Transition

**CANN_VOCODER_FINAL_VERDICT.md written.** Continue from `perf/operator-decode-speak`.

---

## Mission Status Summary

| Gate | Status | Key Finding |
|------|--------|-------------|
| P0 | ✅ PASS | Environment verified, NPU idle |
| P1 | ✅ PASS | Diagnostic code cleaned |
| P2 | ✅ PASS | CPU canonical baseline (RTF=4.21) |
| P3 | ✅ PASS | Path audit + counters |
| P4 | ✅ PASS | CANN vocoder reachable |
| P5 | ✅ PASS (corrected) | CANN correct, vocoder RTF=0.12 vs CPU 0.35 |
| P6 | ✅ COMPLETE | P6-E: framework overhead analysis |
| P7 | ✅ FINAL | Paired A/B: 2.96×, d≈5.5, bootstrap CI, full bucketing |
| P8 | ✅ COMPLETE | msprof: NPU compute 3ms, kernel launch 75ms dominates |
| P9 | ✅ COMPLETE | O2-A+O2-B selected as Top-1 |
| P10 | 🔄 DEFERRED | Device handoff: high risk, max 0.8% total RTF gain |
| P11 | ✅ COMPLETE | Graph reuse implemented, ~1-2ms actual savings |
| P12 | ✅ DECIDED | CANN_VOCODER = INTEGRATION_CANDIDATE |
| P13-P24 | ⏳ PENDING | Flow model optimization (see below) |

---

## CANN Vocoder Final Verdict

**Verdict**: `CANN_VOCODER = INTEGRATION_CANDIDATE`
**Local speedup**: 2.96× (346→117ms, steady-state)
**Total T2W speedup**: 1.075× (4.21→3.92 RTF, -7.0%)
**Graph reuse**: INFRASTRUCTURE_ONLY, default OFF
**Routing**: `OMNI_VOC_DEVICE=gpu` explicit opt-in, NOT default
**Document**: `CANN_VOCODER_FINAL_VERDICT.md`

### Corrected T2W Breakdown (CANN, steady-state)

```
Total T2W per chunk: 3,915ms
├── Flow model (token2mel): 3,798ms (97.0%) ← TRUE BOTTLENECK
└── Vocoder (HiFi-GAN2):     117ms (3.0%)  ← RESOLVED
```

**Even 100× vocoder speedup only improves total by ~3%. Flow model is the only path to competition-significant improvement.**

---

## Flow Model Optimization — Next Mission

### Target

Reduce token2mel time from 3,798ms/chunk (RTF=3.80).

### Planned Phases (User's P13-P17 spec)

| Phase | Name | Description |
|-------|------|-------------|
| P13 | Flow Architecture Audit | Model structure, CANN backend utilization, operator graph |
| P14 | Flow Canonical Baseline | Per-operator timing, kernel breakdown, memory footprint |
| P15 | Flow Profiling | msprof on Flow model ops, identify top operators |
| P16 | Flow Candidate Ranking | Optimization candidates ranked by ROI |
| P17 | Cross-Chunk State | Semantic equivalence verification for cross-chunk caching |

### Branch

New branch `perf/flow-chunk-rtf` from current `perf/operator-decode-speak`.

---

## Immediate Next Action

1. **Commit CANN vocoder final verdict** → `docs(P12-final): CANN_VOCODER = INTEGRATION_CANDIDATE, 2.96× local, 7.0% total`
2. **Create branch** `perf/flow-chunk-rtf` from `perf/operator-decode-speak`
3. **P13: Flow architecture audit** — Read `token2wav-impl.cpp` Flow model section, map operator graph

---

## Key Files

| File | Content |
|------|---------|
| `CANN_VOCODER_FINAL_VERDICT.md` | Final verdict with full bucketing, bootstrap CI |
| `P7_CANN_VS_CPU_PAIRED_AB.md` | Paired A/B updated with bucketing |
| `P11_GRAPH_REUSE_IMPLEMENTATION.md` | Graph reuse implementation and verdict |
| `P9_CANN_VOCODER_CANDIDATE_RANKING.md` | Candidate ranking |
| `P8_CANN_VOCODER_MSPROF.md` | msprof profiling results |
| `CANN_VOCODER_CORRECTNESS.md` | Correctness gate |
| `P6E_FRAMEWORK_OVERHEAD_ANALYSIS.md` | Framework overhead analysis |
| `CPU_VOCODER_CANONICAL_BASELINE.md` | CPU baseline |
| `CANN_VOCODER_PATH_AUDIT.md` | Path audit |
| `CANN_VOCODER_DATAFLOW.md` | Dataflow diagrams |
| `VOCODER_CANN_ENVIRONMENT.md` | Environment snapshot |

## Commit Chain

```
(current)   → P12 final verdict
88d5c43     → P7-final: paired A/B
be44a40     → P11: graph reuse
9b677bc     → P9: candidate ranking
dea690a     → P8: msprof
4b4c4e5     → P5-correction, P6-E, P7-prelim
14de4ef     → P5: correctness gate
c3279ad     → P4: CANN reachability
a39b0d0     → P3: path audit
ac8653c     → P2: CPU baseline
59926cd     → P1: diag cleanup
```
