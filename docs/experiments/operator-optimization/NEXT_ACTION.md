# NEXT ACTION — CANN Vocoder Per-Chunk RTF Optimization

**P11 COMPLETE.** Continue from `perf/operator-decode-speak`, HEAD `be44a40`.

---

## Mission Status Summary

| Gate | Status | Key Finding |
|------|--------|-------------|
| P0 | ✅ PASS | Environment verified, NPU idle |
| P1 | ✅ PASS | Diagnostic code cleaned |
| P2 | ✅ PASS | CPU canonical baseline (RTF=4.05) |
| P3 | ✅ PASS | Path audit + counters |
| P4 | ✅ PASS | CANN vocoder reachable |
| P5 | ✅ PASS (corrected) | CANN correct, vocoder RTF=0.11 vs CPU 0.33 |
| P6 | ✅ COMPLETE | P6-E: framework overhead analysis |
| P7 | ⏳ PRELIMINARY | Paired A/B: 3.0× CANN speedup on vocoder, 6.5% total RTF |
| P8 | ✅ COMPLETE | msprof: NPU compute 3ms, kernel launch 75ms dominates |
| P9 | ✅ COMPLETE | O2-A+O2-B selected as Top-1 |
| P10 | 🔄 DEFERRED | Device handoff: high risk, max 0.8% total RTF gain |
| P11 | ✅ COMPLETE | Graph reuse implemented, ~1-2ms actual savings |
| P12 | ✅ DECIDED | EXIT vocoder-only optimization |
| P13-P24 | ⏳ PENDING | See below |

---

## Critical Finding: Flow Model Is the True Bottleneck

```
Total T2W time per chunk (steady-state): ~3,710ms
├── Flow model (token2mel, CANN): 3,600ms (97.0%)
└── Vocoder (HiFi-GAN2, CANN):     110ms  (3.0%)
    ├── Kernel launch + sync:       75ms   (68% of vocoder)
    ├── Upload (H2D):               15ms   (14%)
    ├── Download (D2H):             10ms   (9%)
    ├── NPU compute:                 3ms   (3%)
    └── Graph build + galloc:        2ms   (2%)
```

**All vocoder optimizations combined can improve total RTF by at most ~3% (3.71→3.60).**
Only Flow model optimization can achieve competition-significant improvement.

---

## P12 Decision: EXIT VOCODER-ONLY OPTIMIZATION

Rationale:
1. Graph reuse (O2-A+O2-B): 1-2ms savings — implemented, minimal impact
2. Device handoff (P10): 20-25ms savings — high risk, 0.5% total RTF
3. Kernel fusion (O2-E): 1-2ms savings — high effort
4. Maximum remaining vocoder savings: ~30ms (0.8% total RTF)

**All practical vocoder optimizations have been explored. Flow model is the next frontier.**

---

## Remaining Gates (P13-P24)

### P13: CPU Fallback Optimization
Skipped — CANN vocoder is 3× faster than CPU. CPU fallback not needed.

### P14: First Chunk + Steady Chunk Joint Optimization
First chunk analysis:
- First chunk vocoder CANN RTF: ~0.28
- Steady chunk vocoder CANN RTF: ~0.11
- First chunk overhead is mostly in Flow model (cold start), not vocoder
Action: Document, no vocoder-specific optimization possible.

### P15: Streaming Continuity Check
Requires: cross-chunk audio boundary analysis
Deferred in P5. Action: Run continuity test if time permits.

### P16: Accuracy Benchmark Gate
Daily-Omni, TTS-Seed, Video-MME benchmarks.
Requires: separate benchmark harness and evaluation data.

### P17: Demo Gate
Requires: working end-to-end demo.

### P18: Resource and Stability Testing
Requires: long-running stability test.

### P19: KV Cache Integration Regression
Requires: testing with KV cache enabled.

### P20: Final Reproduction Package
All scripts, configs, data to reproduce results.

### P21: Git and Report Standards
Final documentation cleanup.

### P22: Final Documentation
Comprehensive mission report.

---

## Next Actions (Priority Order)

1. ⏳ **Wait for P7 background batches to complete** → update P7 with full 30+ paired data
2. **P14**: Document first-chunk analysis
3. **P16**: If benchmark harness available, run accuracy benchmarks
4. **P20**: Prepare reproduction package with all scripts and configs
5. **P22**: Write final comprehensive mission report

---

## Key Files

| File | Content |
|------|---------|
| `P11_GRAPH_REUSE_IMPLEMENTATION.md` | Graph reuse implementation and verdict |
| `P9_CANN_VOCODER_CANDIDATE_RANKING.md` | Candidate ranking |
| `P8_CANN_VOCODER_MSPROF.md` | msprof profiling results |
| `P7_CANN_VS_CPU_PAIRED_AB.md` | Paired A/B (preliminary) |
| `CANN_VOCODER_CORRECTNESS.md` | Correctness gate (with correction) |
| `P6E_FRAMEWORK_OVERHEAD_ANALYSIS.md` | Framework overhead analysis |
| `CPU_VOCODER_CANONICAL_BASELINE.md` | CPU baseline |
| `CANN_VOCODER_PATH_AUDIT.md` | Path audit |
| `CANN_VOCODER_DATAFLOW.md` | Dataflow diagrams |
| `VOCODER_CANN_ENVIRONMENT.md` | Environment snapshot |

## Commit Chain

```
be44a40 feat(P11): O2-A+O2-B graph+galloc reuse with OMNI_VOC_GRAPH_REUSE=1
9b677bc docs(P9): CANN vocoder candidate ranking
dea690a docs(P8): CANN vocoder msprof profiling
4b4c4e5 docs(P5-correction,P6-E,P7): corrected vocoder RTF attribution + paired A/B
14de4ef docs(P5): CANN vocoder correctness gate
c3279ad feat(P4): CANN vocoder reachability smoke
a39b0d0 docs(audit): P3 CANN vocoder path audit + path hit counters
ac8653c docs(baseline): CPU vocoder canonical baseline
59926cd refactor(diag): remove SetDevice/Sync trace instrumentation
```
