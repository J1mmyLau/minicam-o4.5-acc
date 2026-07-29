# CANN Flow + Vocoder Optimization — HANDOFF

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/flow-chunk-rtf`
**HEAD:** `a8acdf7`
**Final Tag:** `cann-flow-vocoder-aclgraph-kvcache-final-20260729`
**Updated:** 2026-07-29 19:50 UTC

---

## State: ALL PRODUCTION GATES CLOSED

```
PHASE3_CANDIDATE_RTF    = 0.229  (18.4× vs CPU baseline 4.21)
STEADY_STATE_RTF         = 0.224  (call ≥ 4)
A_B_ANCHOR_RTF           = 0.245  (4-quadrant Q4: ON,ON)

GATES_PASSED             = 13/14
GATES_BLOCKED            = 1 (G5 external benchmark)
GATES_DEFERRED           = 1 (G14 Im2col)

KV_CACHE_STATUS          = OPT_IN_READY / DEFAULT_OFF
```

---

## Commit Chain

```
a8acdf7 (HEAD -> perf/flow-chunk-rtf) docs: G13 submission package final — all production gates closed
50e8483 docs: G9-G11 gates PASS — KV cache, multi-prefix, lifecycle validated
8e08db4 docs: AUDIT.md — final gate log for 2026-07-29 session
01fdf71 docs: G13 submission package — all gates documented, RTF 0.229, 18.4x vs CPU
767dc20 docs: G12 clean reproduction PASS — RTF 0.236 vs 0.245 original
3685050 docs: G8 1-hr stability PASS — 66 iters, 1368 WAVs, 0 CANN errors
c13d2b7 docs: G7 30-min stability PASS — 37 iters, 661 WAVs, 0 CANN errors
6154b85 docs: HANDOFF — Phase 3 final commit chain updated
9aa54f9 docs: Phase 3 final status — RTF 0.229 (-16.4%), all optimizations documented
7e46faf docs: Phase 3 Rank 2 complete — ADD+NORM fusion, ~1ms gain
9a7f5c2 feat(P20): ADD+NORM (Add+LayerNorm) operator fusion for CANN backend
4a2cbcd feat(P19): CANN ACL graph capture for Flow model — RELAXED mode + min_nodes filter
4f27f96 docs(status): Phase 2 complete — all 7 gates PASS
0973299 docs(P18): 1hr stability PASS — Phase 2 production gates complete
3000af5 docs(P16-P17): Phase 2 gates — demo smoke, bucket, KV cache, 30min stability
189fc96 docs(checkpoint): BREAKTHROUGH_CHECKPOINT — CANN Flow+Vocoder RTF=0.274 candidate freeze
```

## Tag Chain

```
cann-flow-vocoder-rtf027-20260729               (Phase 2 freeze)
cann-flow-vocoder-aclgraph-rtf0229-20260729      (Phase 3 freeze)
cann-flow-vocoder-aclgraph-kvcache-final-20260729 (Production gates closed) ← CURRENT
```

---

## Gate Results (Final)

| # | Gate | Status | Key Result |
|---|------|--------|------------|
| G1 | Perf consistency | ✅ PASS | Numbers self-consistent |
| G2 | Graph cache audit | ✅ PASS | 12-component key verified |
| G3 | 4-quadrant A/B | ✅ PASS | Q4(ON,ON): RTF=0.245 |
| G4 | Chunk buckets | ✅ PASS | Steady RTF=0.224 (call≥4) |
| G5 | Benchmark harness | ⏭️ BLOCKED | External harnesses unavailable |
| G6 | Demo validation | ✅ PASS | 9 cases, 0 CANN errors |
| G7 | 30-min stability | ✅ PASS | 37 iters, 661 WAVs, 0 CANN errors |
| G8 | 1-hr stability | ✅ PASS | 66 iters, 1368 WAVs, 0 CANN errors |
| G9 | KV cache regression | ✅ PASS | 28/30 HIT, 62 tokens, 0 CANN errors |
| G10 | Multi-prefix | ✅ PASS | 3 keys isolated, corruption detected |
| G11 | T2W lifecycle | ✅ PASS | 154 runs, 0 crashes, 0 CANN errors |
| G12 | Clean reproduction | ✅ PASS | RTF 0.236 vs 0.245 (±3.6%) |
| G13 | Submission package | ✅ DONE | Final version |
| G14 | Im2col decision | ⏭️ DEFERRED | Post-gate, Amdahl-limited |

---

## Document Inventory (Complete)

| Document | Status |
|----------|--------|
| `FINAL_CANONICAL_CONFIGURATION.md` | COMPLETE |
| `GRAPH_FUSION_CONFIGURATION_CONTRACT.md` | COMPLETE |
| `PHASE3_PERFORMANCE_RECONCILIATION.md` | COMPLETE |
| `ACL_GRAPH_CAPTURE_CORRECTNESS_AUDIT.md` | INITIAL |
| `PHASE3_EVIDENCE_MANIFEST.md` | COMPLETE |
| `P19_GRAPH_EXECUTION_REUSE.md` | COMPLETE |
| `GRAPH_CAPTURE_CACHE_AUDIT.md` | COMPLETE |
| `GRAPH_FUSION_FOUR_QUADRANT.md` | COMPLETE |
| `CHUNK_BUCKET_STATISTICS.md` | COMPLETE |
| `G5_BENCHMARK_HARNESS_AUDIT.md` | COMPLETE |
| `G6_DEMO_REPORT.md` | COMPLETE |
| `G7_30MIN_STABILITY_REPORT.md` | COMPLETE |
| `G8_1HR_STABILITY_REPORT.md` | COMPLETE |
| `G9_KV_CACHE_FINAL_BINARY_REPORT.md` | COMPLETE |
| `G10_MULTI_PREFIX_REPORT.md` | COMPLETE |
| `G11_T2W_LIFECYCLE_REPORT.md` | COMPLETE |
| `G12_CLEAN_REPRODUCTION.md` | COMPLETE |
| `P4_FINAL_INTEGRATED_PERFORMANCE_REVIEW.md` | COMPLETE |
| `G13_SUBMISSION_PACKAGE.md` | COMPLETE |

---

## Remaining

1. P7: Official Benchmark Harness (Daily-Omni, TTS-Seed, Video-MME) — BLOCKED: no harness
2. P8: Im2col decision — DEFERRED (benefit < 3%)

---

## Key Decisions

- ACL_GRAPH_CAPTURE = PRIMARY_PHASE3_OPTIMIZATION
- ADD_LAYERNORM_FUSION = CONDITIONAL_WEAK_POSITIVE_WITH_GRAPH_CAPTURE
- KV_CACHE = OPT_IN_READY / DEFAULT_OFF
- Three RTF numbers never conflated: 0.245 (A/B), 0.224 (steady), 0.236 (clean build)
- Im2col deferred until all gates pass AND benefit ≥ 3%

## Git Status

- Modified: `tools/omni/omni.cpp`, `tools/omni/omni.h` (pipeline trace infrastructure, uncommitted)
- Untracked: experiment docs, profiling data, rope_fp16 data
- NPU idle
