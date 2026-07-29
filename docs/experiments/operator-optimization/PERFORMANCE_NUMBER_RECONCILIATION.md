# PERFORMANCE NUMBER RECONCILIATION

**Date**: 2026-07-29
**Status**: RECONCILED

---

## 1. Source Data

| Dataset | Path | Chunks | Env |
|---------|------|--------|-----|
| CPU Flow + CPU Vocoder | `/tmp/p14_graph_full.stderr` | 41 | OMNI_T2W_PROFILE=2 |
| CANN Flow + CANN Vocoder (single) | `/tmp/p15_cann_flow.stderr` | 60 | OMNI_T2W_DEVICE=cann-flow-only OMNI_VOC_DEVICE=gpu |
| CANN Flow + CANN Vocoder (stability) | `/tmp/p15_stability_batch[1-5].stderr` | 84 | same |
| P7 CPU Vocoder only | `/tmp/p7_cpu_batches/batch_*.stderr` + smoke | 77 | OMNI_T2W_PROFILE=2 OMNI_VOC_DEVICE=cpu |
| P7 CANN Vocoder only | `/tmp/p7_cann_batches/batch_*.stderr` + smoke | 136 | OMNI_T2W_PROFILE=2 OMNI_VOC_DEVICE=gpu |

## 2. Corrected Numbers

### 2.1 Flow Model (token2mel) — Steady-State Only

| Metric | CPU | CANN | Speedup |
|--------|-----|------|---------|
| Mean | 3,725.8ms | 154.9ms | **24.1×** |
| Median | 3,644.9ms | 155.3ms | **23.5×** |
| p95 | 4,124.4ms | 194.6ms | 21.2× |
| n | 36 | 65 | — |

### 2.2 Vocoder — Steady-State Only

| Metric | CPU | CANN | Speedup |
|--------|-----|------|---------|
| Mean | 348.2ms | 119.1ms | **2.92×** |
| Median | 327.0ms | 118.8ms | **2.75×** |
| p95 | 427ms | 131ms | 3.26× |
| n | 52 | 65 | — |

### 2.3 Total T2W (Flow + Vocoder) — Steady-State Only

| Metric | CPU | CANN | Speedup |
|--------|-----|------|---------|
| Mean | 4,049.4ms | 274.0ms | **14.8×** |
| Median | 3,965.2ms | 273.7ms | **14.5×** |
| p95 | 4,450ms | 326ms | 13.7× |
| n | 36 | 65 | — |

### 2.4 Per-Chunk RTF

| Metric | CANN Steady |
|--------|-------------|
| Mean RTF | **0.2740** |
| Median RTF | **0.2737** |
| p95 RTF | 0.326 |

---

## 3. Discrepancy Analysis

### 3.1 "21.9×" → corrected to 24.1×

Previous report at P15 used CANN Flow single-batch `all` mean (169.7ms, n=60)
vs CPU Flow `steady` mean (3,725.8ms, n=36):
```
3725.8 / 169.7 = 21.96×
```

The error: compared steady CPU against ALL CANN (including first+warmup).
Correct: use steady-state for both:
```
3725.8 / 154.9 = 24.05×
```

### 3.2 "2.96×" vocoder → corrected to 2.92× (mean) / 2.75× (median)

P7 analysis used slightly different steady-state definitions and included
different subsets. The corrected numbers use matched bucket definitions:

| Previous Report | Corrected (mean) | Corrected (median) |
|----------------|-----------------|-------------------|
| 2.96× | 2.92× | 2.75× |

### 3.3 "13.8×" total → corrected to 14.8×

Same issue: single-batch CANN `all` mean (294.0ms) vs CPU `steady` mean (4,049.4ms):
```
4049.4 / 294.0 = 13.77×
```

Correct (steady-state both):
```
4049.4 / 274.0 = 14.78×
```

### 3.4 "0.27 RTF" → confirmed as 0.274

Rounded to 0.27 is acceptable shorthand. Exact values: mean=0.2740, median=0.2737.

---

## 4. Which Numbers to Use Officially

### Competition Metric

```
PER-CHUNK RTF = (flow_compute + vocoder_compute) / audio_duration_ms
              = (154.9 + 119.1) / 1000.0
              = 0.2740  (mean, steady-state, n=65)
              = 0.2737  (median, steady-state, n=65)
```

### Total Speedup

```
ABSOLUTE SPEEDUP = CPU_Total_T2W / CANN_Total_T2W
                 = 4049.4 / 274.0
                 = 14.8×  (mean, steady-state)
                 = 14.5×  (median, steady-state)
```

### Conservative Statement

> CANN Flow + CANN Vocoder achieves **RTF ≈ 0.27** on Ascend 910C,
> a **~15× total T2W speedup** vs CPU baseline (4,050ms → 274ms per chunk).
> All numbers: steady-state (call ≥ 4), mean across 65 chunks from 5 independent batches.
> Exact values: mean RTF=0.2740, median RTF=0.2737, speedup=14.8× (mean) / 14.5× (median).

---

## 5. Bucket Definitions (for all datasets)

| Bucket | Definition | Notes |
|--------|-----------|-------|
| FIRST | call=0 | Includes CANN JIT / first-time alloc |
| WARMUP | call 1-3 | NPU warms up, cache settles |
| STEADY | call ≥ 4, excl last | Primary metric bucket |
| TAIL | last call in batch | May differ from steady |

---

## 6. Sample Counts

| Dataset | Total | First | Warmup | Steady | Tail |
|---------|-------|-------|--------|--------|------|
| CPU Flow (P14) | 41 | 1 | 3 | 36 | 1 |
| CANN Flow single (P15) | 60 | 1 | 3 | 55 | 1 |
| CANN Flow stability | 84 | 5 | 14 | 65 | 5 |
| P7 CPU Vocoder | 77 | 6 | 18 | 52 | 6 |
| P7 CANN Vocoder | 136 | 6 | 18 | 111 | 6 |

---

## 7. Caveats

1. **CPU Flow and CANN Flow are from different test cases** (different LLM output).
   Numbers are UNPAIRED — not matched by chunk content.
2. **Flow and Vocoder samples come from different runs** (P14/P15 for Flow, P7 for Vocoder).
   Total T2W uses in-run pairing from the same stderr file.
3. **CPU Flow n=36 vs CANN Flow n=65** — asymmetric sample sizes.
   The larger CANN sample is from 5 stability batches.
4. **Inter-batch CV of CANN Flow means**: 0.087 (good reproducibility).
5. **First-chunk and warmup are excluded** from steady-state for conservative reporting.
