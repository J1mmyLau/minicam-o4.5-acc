# CANN Flow + Vocoder Optimization — HANDOFF

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/flow-chunk-rtf`
**HEAD:** `6154b85` (Phase 3 FREEZE — graph capture + fusion)
**Updated:** 2026-07-29 12:45 UTC

---

## Commit Chain

```
6154b85 (HEAD -> perf/flow-chunk-rtf) docs: HANDOFF — Phase 3 final commit chain updated
9aa54f9 docs: Phase 3 final status — RTF 0.229 (-16.4%), all optimizations documented
7e46faf docs: Phase 3 Rank 2 complete — ADD+NORM fusion, ~1ms gain
9a7f5c2 feat(P20): ADD+NORM (Add+LayerNorm) operator fusion for CANN backend
4a2cbcd feat(P19): CANN ACL graph capture for Flow model — RELAXED mode + min_nodes filter
4f27f96 docs(status): Phase 2 complete — all 7 gates PASS
0973299 docs(P18): 1hr stability PASS — Phase 2 production gates complete
3000af5 docs(P16-P17): Phase 2 gates — demo smoke, bucket, KV cache, 30min stability
189fc96 docs(checkpoint): BREAKTHROUGH_CHECKPOINT — CANN Flow+Vocoder RTF=0.274 candidate freeze
7f5f349 docs(P15-C): CANN Flow msprof — Im2col 42%, kernel launch overhead 73%
822d2e0 docs(status): COMPETITION METRIC RTF=0.27 — below realtime
fff6ab0 docs(P15-A,P15-B): CANN Flow correctness + stability verification
660fe91 docs(P15): Flow model CANN discovery — 21.9x speedup via cann-flow-only
edf0661 docs(P13,P14): Flow model architecture audit + canonical baseline
8a4de90 docs(P12-final): CANN_VOCODER = INTEGRATION_CANDIDATE
88d5c43 docs(P7-final): CANN vocoder paired A/B
```

### Previous Tag

`cann-flow-vocoder-rtf027-20260729` (HEAD: 189fc96)

### New Tag Candidate

`cann-flow-vocoder-aclgraph-rtf0229-20260729` (HEAD: 6154b85)

---

## Current State — PHASE 3 FROZEN

```
CPU_BASELINE_RTF             ≈ 4.21
PHASE2_CANN_FLOW_VOCODER_RTF ≈ 0.274  (Flow 155ms + Vocoder 119ms)
PHASE3_GRAPH_FUSION_RTF      ≈ 0.229  (Flow 111ms + Vocoder 118ms)

TOTAL_INTERNAL_SPEEDUP       ≈ 18.4×  (4.21 / 0.229)
PHASE3_RELATIVE_REDUCTION    ≈ 16.4%  ((0.274 - 0.229) / 0.274)

CANN_FLOW                  = INTEGRATION_CANDIDATE  (24.1×, 3,726→155→111ms)
CANN_VOCODER               = INTEGRATION_CANDIDATE  (2.92×, 348→119ms)
ACL_GRAPH_CAPTURE          = INTEGRATION_CANDIDATE  (RELAXED, 1 capture → 19+ HITs)
ADD_LAYERNORM_FUSION       = WEAK_POSITIVE_INTEGRATED  (~1ms, 257 pairs)

PHASE3_CANDIDATE_FROZEN    = YES
OFFICIAL_SCORE             = NOT_AVAILABLE
BENCHMARK_GATE             = PENDING
DEMO_GATE                  = PENDING
STABILITY_GATE             = PENDING
CLEAN_MACHINE_GATE         = PENDING
```

**Explicitly NOT declared:** PRODUCTION_READY, OFFICIAL_RTF, FULLY_OPTIMIZED, GUARANTEED_18X

---

## Completed

### Phase 1: BREAKTHROUGH_CHECKPOINT ✅
- 4 audits, evidence manifest, SHA256SUMS
- Git tag: `cann-flow-vocoder-rtf027-20260729`

### Phase 2: Production Gates ✅ (ALL 7 PASS)
| Gate | Result | Key Data |
|------|--------|----------|
| Demo smoke | ✅ | 16 WAVs, RTF=0.28, 0 CANN errors |
| Bucket characterization | ✅ | Steady RTF=0.261 (call≥4) |
| KV cache regression | ✅ | HIT/MISS/OFF all compatible |
| 30-min stability | ✅ | 59/59 PASS, 302 WAVs |
| T2W lifecycle L2-L6 | ✅ | Rapid 5/5, 59 transitions |
| 1-hr stability | ✅ | 118/118 PASS, 594 WAVs |
| Multi-prefix | ⏭️ | Deferred to KV cache branch |

### Phase 3: Optimization ✅ (FROZEN)
| Rank | Task | Impact | Status |
|------|------|--------|--------|
| 1 | Graph execution reuse | **-28.2% Flow compute** (-43.6ms) | ✅ DONE |
| 2 | Operator fusion | ~1ms (diminishing returns) | ✅ DONE |
| 3 | Im2col custom kernel | Deferred (high risk, all gates first) | ⏭️ |
| 4 | Async H2D/D2H | Deferred (already async, 2-3ms p50) | ⏭️ |

---

## NOT DONE / Next Session

### P0: Graph Capture Correctness (10 boundary conditions)
1. Dynamic shape (different chunk lengths)
2. Session reset mid-capture
3. Abort during capture
4. Model reload after session
5. Multiple concurrent sessions
6. Long-running stability (1hr+)
7. KV cache HIT/MISS/OFF modes
8. Multi-prefix isolation
9. Clean-machine reproduction
10. Capture failure fallback

### P1: Production Gates (Phase 3 candidate)
1. Demo full validation
2. First/warmup/steady/tail chunk statistics
3. Official Benchmark harness audit
4. 30-min + 1-hr stability
5. KV cache integration regression
6. T2W lifecycle (L2-L6)
7. Clean-machine reproduction
8. Submission package

### P2: Im2col (POST-GATE ONLY)
- Requires: all gates pass + wall-time benefit ≥ 3% + audio correctness verifiable
- Approach: `aclnnFusedCausalConv1d` or custom AscendC kernel

---

## Document Inventory

| Document | Path | Status |
|----------|------|--------|
| Phase 3 reconciliation | `PHASE3_PERFORMANCE_RECONCILIATION.md` | COMPLETE |
| Graph capture audit | `ACL_GRAPH_CAPTURE_CORRECTNESS_AUDIT.md` | INITIAL |
| Phase 3 evidence manifest | `PHASE3_EVIDENCE_MANIFEST.md` | COMPLETE |
| P19: Graph execution reuse | `P19_GRAPH_EXECUTION_REUSE.md` | COMPLETE |
| Phase 2 gate results | `PHASE2_GATE_RESULTS.md` | COMPLETE |
| P15-C: msprof | `docs/experiments/operator-optimization/P15C_CANN_FLOW_MSPROF.md` | COMPLETE |
| Evidence manifest (Phase 1) | `EVIDENCE_MANIFEST.md` | COMPLETE |
| 4 audit docs | `FLOW_*_AUDIT.md`, `PERFORMANCE_*`, `CANN_BACKEND_*` | COMPLETE |

---

## Git Status

- Modified: `profiles/STATUS.md`, `profiles/HANDOFF.md`, `profiles/rope_fp16_ab/pairs.csv`, `tools/omni/omni.cpp`, `tools/omni/omni.h`
- Untracked: earlier-phase docs (`docs/experiments/operator-optimization/*`), rope_fp16 data, cann_fusion_v0 profile data
- NPU idle
