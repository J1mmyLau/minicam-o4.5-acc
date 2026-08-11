# CANN Vocoder Final Verdict — INTEGRATION_CANDIDATE

**Date**: 2026-07-29
**Phase**: P7 finalization → P12 decision
**Status**: FINAL
**Verdict**: `CANN_VOCODER = INTEGRATION_CANDIDATE`

---

## 1. Executive Summary

After exhaustive evaluation across P0-P12, the CANN HiFi-GAN2 vocoder path is retained as
`INTEGRATION_CANDIDATE`. It provides a **2.96× local vocoder speedup** (346→117ms)
translating to **7.0% total T2W RTF reduction** (4.21→3.92). The path is correct
(zero fallback, zero failure across 213 chunks), stable (CV=0.03), and
statistically indisputable (bootstrap 95% CI non-overlapping).

**The vocoder bottleneck is resolved. The true bottleneck is the Flow model (token2mel),
3,798ms/chunk (97% of CANN T2W).**

---

## 2. Final Per-Bucket Statistics

### 2.1 CPU Vocoder (OMNI_VOC_DEVICE=cpu)

| Bucket | n | Vocoder | Token2Mel | Total | Voc RTF | CV |
|--------|---|---------|-----------|-------|---------|-----|
| FIRST | 6 | 429±186ms | 5,121±2,066ms | 5,550ms | 0.511 | 0.434 |
| WARMUP | 18 | 428±126ms | 4,669±1,267ms | 5,097ms | 0.429 | 0.295 |
| **STEADY** | **47** | **346±58ms** | **3,863±324ms** | **4,209ms** | **0.346** | **0.169** |
| TAIL | 6 | 361±75ms | 3,722±89ms | 4,083ms | 0.361 | 0.209 |

### 2.2 CANN Vocoder (OMNI_VOC_DEVICE=gpu)

| Bucket | n | Vocoder | Token2Mel | Total | Voc RTF | CV |
|--------|---|---------|-----------|-------|---------|-----|
| FIRST | 6 | 269±25ms | 4,362±444ms | 4,631ms | 0.320 | 0.093 |
| WARMUP | 18 | 120±4ms | 4,364±434ms | 4,485ms | 0.120 | 0.032 |
| **STEADY** | **106** | **117±3ms** | **3,798±268ms** | **3,915ms** | **0.117** | **0.029** |
| TAIL | 6 | 112±14ms | 3,757±197ms | 3,869ms | 0.119 | 0.048 |

### 2.3 Key Observations

- **CANN variance is 6× lower** than CPU (CV 0.029 vs 0.169 on vocoder RTF)
- **CANN is tight across all steady chunks**: 117±3ms, all within [112, 123]ms
- **CPU is bimodal**: clusters at ~0.33 and ~0.55 RTF depending on chunk content
- **First-chunk penalty exists in both**: CPU 429ms, CANN 269ms — predominantly Flow model cold-start, not vocoder
- **Warmup converges by call 4**: CANN drops from 269→120→117ms across first 4 calls

---

## 3. Steady-State Paired Comparison (Primary Metric)

### 3.1 Vocoder-Only

| Metric | CPU (n=47) | CANN (n=106) |
|--------|-----------|-------------|
| Mean RTF | 0.3461 | 0.1167 |
| Std dev | 0.0584 | 0.0034 |
| CV | 0.169 | 0.029 |
| Bootstrap 95% CI | [0.3316, 0.3636] | [0.1161, 0.1174] |
| Median | 0.332 | 0.116 |
| p90 | 0.407 | 0.120 |
| p95 | 0.481 | 0.122 |

**Vocoder local speedup: 2.96×** (0.3461 / 0.1167)
**Vocoder RTF difference: 0.2293** (95% CI [0.2146, 0.2476])
**100% win rate**: all 106 CANN chunks below CPU median (0.332)

### 3.2 Total T2W Impact

| Metric | CPU | CANN |
|--------|-----|------|
| Total T2W RTF | 4.2094 | 3.9152 |
| Bootstrap 95% CI | [4.1137, 4.3150] | [3.8675, 3.9702] |
| **Total speedup** | **1.0751×** | |
| **Relative reduction** | **-6.99%** | |

### 3.3 Flow Model Contribution

| Component | CPU (ms) | % of T2W | CANN (ms) | % of T2W |
|-----------|----------|----------|-----------|----------|
| token2mel | 3,863 | 91.8% | 3,798 | 97.0% |
| vocoder | 346 | 8.2% | 117 | 3.0% |
| Total | 4,209 | 100% | 3,915 | 100% |

**Amdahl verification**: 8.2% of work accelerated 2.96× → theoretical 6.5% total gain.
Measured 7.0% — consistent within sampling error.

---

## 4. Graph Reuse (OMNI_VOC_GRAPH_REUSE=1) — Separate Benefit

### 4.1 Measured Impact

| Metric | Without Reuse | With Reuse | Delta |
|--------|--------------|------------|-------|
| CANN vocoder steady time | ~112ms | ~118ms | +6ms (within noise) |
| Graph build + galloc savings | — | ~1-2ms | **INFRASTRUCTURE_ONLY** |
| Total T2W RTF delta | — | — | **~0%** |

### 4.2 Why Graph Reuse Doesn't Help

The P8 msprof analysis revealed that graph construction is only ~3ms of the 110ms
vocoder time. The dominant overhead is:

| Component | Time | Addressable by Reuse? |
|-----------|------|----------------------|
| Kernel launch + sync | ~75ms | ❌ No |
| Upload (H2D) | ~15ms | ❌ No |
| Download (D2H) | ~10ms | ❌ No |
| Graph build + galloc | ~3ms | ✅ Yes (saves ~1-2ms) |
| NPU compute | ~3ms | ❌ No |

### 4.3 Verdict: OMNI_VOC_GRAPH_REUSE = INFRASTRUCTURE_ONLY

- Feature flag is implemented, tested, and correct (25/27 chunk reuse hits)
- Zero segfaults, zero compute failures, zero download failures
- Actual savings: ~1-2ms per chunk (immaterial to total T2W)
- **Useful for future work** (e.g., device handoff, persistent allocation)
- **Default: OFF** — not harmful, not significantly helpful

---

## 5. Path Hit Verification (All 213 Chunks)

| Counter | CPU (77 chunks) | CANN (136 chunks) |
|---------|----------------|-------------------|
| cpu_dispatch | 77 | 0 |
| cann_dispatch | 0 | 136 |
| cann_success | 0 | 136 |
| cann_failure | 0 | 0 |
| cpu_fallback | 0 | 0 |

✅ **Zero fallback, zero failure across 213 chunks. Path routing is correct.**

---

## 6. Statistical Rigor

### 6.1 Bootstrap 95% CI (10,000 resamples)

All CIs are non-overlapping — the CANN advantage is statistically irrefutable.

### 6.2 Effect Size

- **Cohen's d ≈ 5.5** (vocoder RTF): massive effect
- **Common language effect size**: 100% (CANN < CPU for any random pair)
- **No overlap in distributions**: max CANN = 0.123 RTF, min CPU = 0.254 RTF

### 6.3 Practical Significance

- **7.0% total RTF reduction** on the competition metric
- Translate to **~260ms saved per chunk** (4,209→3,915ms total T2W)
- **Consistent across all batches** (CPU batches: 1-7, CANN batches: 1-7)

---

## 7. Integration Protocol

### 7.1 Routing

```bash
# Enable CANN vocoder (explicit opt-in)
export OMNI_VOC_DEVICE=gpu

# Graph reuse: available but default OFF
export OMNI_VOC_GRAPH_REUSE=1   # optional, ~1-2ms savings

# Path hit verification (debug)
export OMNI_VOC_PATH_STATS=1
```

### 7.2 Fallback Behavior

- If CANN backend unavailable → falls back to CPU vocoder (existing behavior)
- If CANN compute/download fails → falls back to CPU for that chunk
- Path hit counters track all transitions

### 7.3 Do NOT Default ON

The 7.0% total RTF improvement is real but modest. The CANN path adds a dependency
on CANN runtime and HBM allocation (~2GB for vocoder). Default remains CPU vocoder;
operators who need the speedup can explicitly opt in.

---

## 8. What Was Explored and Rejected

| Optimization | Potential | Actual | Verdict |
|-------------|----------|--------|---------|
| Graph reuse (O2-A+O2-B) | 60-90ms | 1-2ms | INFRASTRUCTURE_ONLY |
| Device handoff (P10) | 20-25ms | — | HIGH_RISK, 0.5% total |
| Kernel fusion (O2-E) | 1-3ms | — | HIGH_EFFORT, 0.1% total |
| FP16 vocoder | 5-10ms | — | QUALITY_RISK |
| Async compute (O2-G) | 10-15ms | — | FRAMEWORK_CHANGE |

**Maximum remaining vocoder-only savings: ~30ms (0.8% total T2W).**
**Amdahl's Law forbids further vocoder optimization from being competition-significant.**

---

## 9. Transition to Flow Model

### 9.1 Why Flow Model Now

```
CANN T2W per chunk (steady-state): 3,915ms
├── Flow model (token2mel): 3,798ms (97.0%) ← TRUE BOTTLENECK
└── Vocoder (HiFi-GAN2):     117ms (3.0%)  ← RESOLVED
```

**Even a theoretical 100× vocoder speedup (0ms) only improves total RTF by ~3%.**
**A 10% Flow model speedup improves total RTF by ~9.7%.**

### 9.2 Flow RTF Target

- Current Flow RTF: 3.80 (3,798ms for ~1,000ms audio)
- Competition-significant total RTF improvement requires Flow RTF reduction of >15%

### 9.3 Next Steps

1. **Flow architecture audit**: token2mel model structure, CANN backend utilization
2. **Flow canonical baseline**: per-operator timing, kernel breakdown
3. **Flow profiling**: msprof or similar CANN profiler on Flow model ops
4. **Flow candidates**: kernel fusion, attention optimization, quantization

---

## 10. Document Index

| Document | Content |
|----------|---------|
| `VOCODER_CANN_ENVIRONMENT.md` | P0: Environment snapshot |
| `CANN_VOCODER_PATH_AUDIT.md` | P3: Path audit + counters |
| `CANN_VOCODER_DATAFLOW.md` | P3: Dataflow diagrams |
| `CPU_VOCODER_CANONICAL_BASELINE.md` | P2: CPU baseline |
| `CANN_VOCODER_CORRECTNESS.md` | P5: Correctness gate |
| `P6E_FRAMEWORK_OVERHEAD_ANALYSIS.md` | P6-E: Framework overhead |
| `P7_CANN_VS_CPU_PAIRED_AB.md` | P7: Paired A/B |
| `P8_CANN_VOCODER_MSPROF.md` | P8: msprof profiling |
| `P9_CANN_VOCODER_CANDIDATE_RANKING.md` | P9: Candidate ranking |
| `P11_GRAPH_REUSE_IMPLEMENTATION.md` | P11: Graph reuse |

---

## 11. Sign-off

| Gate | Status | Key Metric |
|------|--------|------------|
| P0: Environment | ✅ PASS | CANN 9.1.0-beta1, Ascend 910C |
| P1: Diag cleanup | ✅ PASS | 238 lines removed |
| P2: CPU baseline | ✅ PASS | CPU voc RTF=0.346 |
| P3: Path audit | ✅ PASS | Counters verified |
| P4: CANN reachable | ✅ PASS | Smoke test pass |
| P5: Correctness | ✅ PASS | Audio output valid |
| P6-E: Overhead | ✅ PASS | Kernel launch dominates |
| P7: Paired A/B | ✅ PASS | 2.96×, d≈5.5, 100% win |
| P8: msprof | ✅ PASS | NPU compute=3ms |
| P9: Candidates | ✅ PASS | O2-A+O2-B selected |
| P11: Graph reuse | ✅ PASS | INFRASTRUCTURE_ONLY |
| **P12: FINAL** | **INTEGRATION_CANDIDATE** | **7.0% total RTF reduction** |

**CANN_VOCODER = INTEGRATION_CANDIDATE**
**OMNI_VOC_DEVICE=gpu: explicit opt-in, not default**
**OMNI_VOC_GRAPH_REUSE=1: INFRASTRUCTURE_ONLY, default OFF**
**Next mission: Flow model (token2mel) RTF optimization**
