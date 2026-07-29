# CANN Flow + Vocoder Optimization — HANDOFF

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/flow-chunk-rtf`
**HEAD:** `0973299` (P18: 1hr stability PASS — Phase 2 production gates complete)
**Updated:** 2026-07-29 09:45 UTC

---

## Commit Chain

```
0973299 (HEAD -> perf/flow-chunk-rtf) docs(P18): 1hr stability PASS — Phase 2 production gates complete
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

### Tag

`cann-flow-vocoder-rtf027-20260729` (HEAD: 189fc96)

---

## Current State

```
CANN_FLOW       = INTEGRATION_CANDIDATE  (24.1×, 3,726→155ms)
CANN_VOCODER    = INTEGRATION_CANDIDATE  (2.92×, 348→119ms)
COMBINED_INTERNAL_STEADY_RTF ≈ 0.274
COMPETITION_METRIC: per-chunk RTF = 0.274 (mean, n=65 steady, 5 batches)
PRODUCTION_READY  = NO
OFFICIAL_RTF      = NOT_AVAILABLE
GUARANTEED_15×    = NO
```

---

## Completed

### Phase 1: BREAKTHROUGH_CHECKPOINT
- ✅ 4 audits (number reconciliation, reachability, env semantics, profile percentage)
- ✅ Evidence manifest + SHA256SUMS
- ✅ Git tag: `cann-flow-vocoder-rtf027-20260729`

### Phase 2: Production Gates (ALL 7 PASS)
| Gate | Result | Key Data |
|------|--------|----------|
| Demo smoke | ✅ | 16 WAVs, RTF=0.28, 0 CANN errors |
| Bucket characterization | ✅ | Steady RTF=0.261 (call≥4), first=0.567 |
| KV cache regression | ✅ | HIT/MISS/OFF all compatible, 0 CANN errors |
| 30-min stability | ✅ | 59/59 PASS, 302 WAVs, RTF mean=0.313 |
| T2W lifecycle L2-L6 | ✅ | Rapid 5/5, 59 transitions, 0 failures |
| 1-hr stability | ✅ | 118/118 PASS, 594 WAVs, RTF mean=0.324 |
| Multi-prefix | ⏭️ | Deferred to KV cache production branch |

---

## NOT DONE / Phase 3: Further Optimization

| Rank | Task | Est. Impact | Approach |
|------|------|-------------|----------|
| 1 | Graph execution reuse | 20-60ms | Reduce 188k kernel launches, reuse CANN graph |
| 2 | Operator fusion | 10-20ms | Element-wise fusion (Add+Mul+Cast), norm+scale |
| 3 | Im2col custom kernel | 5-8ms | Fused conv1d or AscendC kernel |
| 4 | Async H2D/D2H | 1-2ms | Async transfer, pinned memory |

---

## Document Inventory (new since checkpoint)

| Document | Path |
|----------|------|
| P16: Demo smoke + bucket + KV cache | `P16_DEMO_SMOKE_BUCKET_KVCACHE.md` |
| P17: 30-min stability | `P17_30MIN_STABILITY_REPORT.md` |
| P17: T2W lifecycle plan | `P17_T2W_LIFECYCLE_TEST_PLAN.md` |
| P18: 1-hr stability | `P18_1HR_STABILITY_REPORT.md` |
| Phase 2 gate results | `PHASE2_GATE_RESULTS.md` |
| Evidence manifest | `EVIDENCE_MANIFEST.md` |
| 4 audit docs | `FLOW_*_AUDIT.md`, `PERFORMANCE_*`, `CANN_BACKEND_*` |

---

## Git Status

- Modified: `profiles/STATUS.md`, `profiles/HANDOFF.md`, `profiles/rope_fp16_ab/pairs.csv`, `tools/omni/omni.cpp`, `tools/omni/omni.h`
- Untracked: earlier-phase docs, rope_fp16 data, cann_fusion_v0 profile
- NPU idle
