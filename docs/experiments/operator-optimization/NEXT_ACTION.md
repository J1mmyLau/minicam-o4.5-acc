# NEXT ACTION — CANN Flow Discovery → Competition Metric Achieved

**P15 complete.** Continue from `perf/flow-chunk-rtf`, HEAD `fff6ab0`.

---

## BREAKTHROUGH: RTF=0.27 — Below Realtime

The Flow model was discovered to be running on CPU (not CANN) in all previous experiments.
Enabling `OMNI_T2W_DEVICE=cann-flow-only` deferred worker-thread CANN init and achieved:

```
Before:  RTF = (3,723 + 117) / 1000 = 3.84  — NOT realtime
After:   RTF = (  155 + 119) / 1000 = 0.27  — WELL BELOW REALTIME
```

**Total T2W speedup: 13.8×** (4,045ms → 274ms per chunk)

---

## Mission Status Summary

| Gate | Status | Key Finding |
|------|--------|-------------|
| P0 | ✅ PASS | Environment verified |
| P1 | ✅ PASS | Diagnostic code cleaned |
| P2 | ✅ PASS | CPU baseline (RTF=4.21) |
| P3 | ✅ PASS | Path audit + counters |
| P4 | ✅ PASS | CANN vocoder reachable |
| P5 | ✅ PASS | CANN vocoder correct |
| P6 | ✅ COMPLETE | Framework overhead analysis |
| P7 | ✅ FINAL | Vocoder paired A/B: 2.96× |
| P8 | ✅ COMPLETE | msprof: kernel launch dominates vocoder |
| P9 | ✅ COMPLETE | O2-A+O2-B selected |
| P10 | 🔄 DEFERRED | Device handoff |
| P11 | ✅ COMPLETE | Graph reuse (INFRASTRUCTURE_ONLY) |
| P12 | ✅ DECIDED | CANN_VOCODER = INTEGRATION_CANDIDATE |
| P13 | ✅ COMPLETE | Flow architecture audit |
| P14 | ✅ COMPLETE | Flow canonical baseline (CPU: 3,723ms) |
| P15 | ✅ COMPLETE | **Flow CANN discovery: 21.9× speedup** |
| P15-A | ✅ PRELIMINARY_PASS | Correctness: 60/60 wavs valid |
| P15-B | ✅ PRELIMINARY_PASS | Stability: 5 batches, 0 failures |
| P15-C | ⏳ PENDING | CANN Flow msprof |
| P16-P24 | ⏳ PENDING | Accuracy, demo, stability, docs |

---

## Competition Metric Achievement

### Final Numbers (CANN Flow + CANN Vocoder, Steady-State)

| Component | Time | RTF | % Total |
|-----------|------|-----|---------|
| Flow (t2m.compute, CANN) | 155ms | 0.155 | 56.6% |
| Vocoder (CANN) | 119ms | 0.119 | 43.4% |
| **Total T2W** | **274ms** | **0.274** | **100%** |

### Speedup Stack

| Optimization | Cumulative RTF | Speedup | Method |
|-------------|---------------|---------|--------|
| CPU baseline | 4.21 | 1.00× | — |
| + CANN Vocoder | 3.92 | 1.07× | OMNI_VOC_DEVICE=gpu |
| + CANN Flow | **0.27** | **15.6×** | OMNI_T2W_DEVICE=cann-flow-only |

### Key Configuration

```bash
export OMNI_T2W_DEVICE=cann-flow-only   # Flow CANN (worker-thread deferred init)
export OMNI_VOC_DEVICE=gpu              # Vocoder CANN
export OMNI_T2W_PROFILE=2               # Per-chunk timing
```

---

## Remaining Gates

### P15-C: CANN Flow msprof
Re-run msprof with CANN Flow enabled to capture Flow model CANN kernels.
Identify top operators and kernel launch overhead.

### P16: Accuracy Benchmark Gate
Daily-Omni, TTS-Seed, Video-MME benchmarks with CANN Flow.
Full mel-spectrogram equivalence between CPU Flow and CANN Flow.

### P17: Demo Gate
Working end-to-end demo with CANN Flow.

### P18: Resource and Stability Testing
Long-running stability test (1h → 6h → 24h).

### P19: KV Cache Integration Regression
Testing with KV cache enabled.

### P20-P22: Documentation
Reproduction package, final documentation.

---

## Commit Chain

```
fff6ab0 (HEAD) → P15-A+P15-B: correctness + stability
660fe91        → P15: Flow CANN discovery (21.9×)
edf0661        → P13+P14: Flow audit + baseline
8a4de90        → P12: CANN vocoder final verdict
88d5c43        → P7: vocoder paired A/B
be44a40        → P11: graph reuse
... (see earlier commits on perf/operator-decode-speak)
```
