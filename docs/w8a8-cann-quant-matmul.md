# W8A8 CANN Quantized Matmul: INT8×INT8→FP16 Pipeline

**Status:** Production-ready as Q8_0 opt-in  
**Date:** 2026-08-09  
**Branch:** `main` @ `a55dcba`

## Overview

W8A8 replaces the default Q8_0 matmul path (`aclnnWeightQuantBatchmatmulV2`, W8A16) with an INT8×INT8→FP16 pipeline (`aclnnQuantize` + `aclnnQuantMatmulV3`) on Ascend NPU via CANN 9.1.0-beta.1.

The default Q8_0 path (V2) is **10.3% slower** than F16 on Ascend 910B2C because CANN lacks a native W8A16→FP16 kernel for the Q8_0 non-zero (NZ) layout. W8A8 recovers ~86% of this gap by using INT8×INT8→FP32→FP16 matmul, which CANN does support natively.

## Quick Start

```bash
# Enable W8A8 matmul for Q8_0 models
GGML_CANN_W8A8=1 ./llama-omni-server -m model-Q8_0.gguf ...

# Or set as environment variable
export GGML_CANN_W8A8=1
```

**Scope:** Only affects `ggml_cann_mul_mat()` when:
1. Weight type is `GGML_TYPE_Q8_0`
2. Output dimension N ≥ 2048 (small-N shapes use V2 — faster)

## Performance

### Matmul-Level (Phase 1c Benchmark)

| Path | Model-Weighted Latency (S1-S7) | vs V2 | vs F16 |
|------|-------------------------------|-------|--------|
| F16_ND (aclnnMm) | 311.6 us | 11.86× | 1.00× |
| **W8A8** (Quantize+QuantMatmulV3) | **776.1 us** | **4.76×** | **0.40×** |
| V2 (WeightQuantBatchmatmulV2) | 3695.0 us | 1.00× | 0.084× |

### W8A8 Decomposition

| Component | Mean p50 | % of Total |
|-----------|----------|------------|
| T_ACT_SCALE (D2H + CPU max scan) | 56.9 us | 42.7% |
| T_QUANTIZE (aclnnQuantize) | 29.8 us | 22.4% |
| T_MATMUL (aclnnQuantMatmulV3) | 45.9 us | 34.5% |
| **Total** | **133.2 us** | 100% |

### Shape-Specific Speedup

| Shape | K | N | V2 p50 | W8A8 p50 | Speedup |
|-------|---|---|--------|----------|---------|
| S1 Q-proj | 4096 | 4096 | 535.0 | 110.9 | **4.82×** |
| S2 K-proj | 4096 | 1024 | 47.2 | 107.2 | 0.44× → **V2** |
| S3 V-proj | 4096 | 1024 | 53.2 | 104.4 | 0.51× → **V2** |
| S4 O-proj | 4096 | 4096 | 540.8 | 108.3 | **4.99×** |
| S5 FFN-gate | 4096 | 12288 | 834.0 | 107.1 | **7.78×** |
| S6 FFN-up | 4096 | 12288 | 830.1 | 112.6 | **7.37×** |
| S7 FFN-down | 12288 | 4096 | 854.7 | 125.6 | **6.80×** |

## Architecture

### Pipeline

```
Q8_0 Weight (device)                FP16 Input (device)
        │                                  │
        ▼ D2H                              │
  Dequant per-group                       │
  (int8 × fp16_scale)                     │
        │                                  │
        ▼                                  ▼
  Requant per-tensor              Compute act_scale
  (fp32 → int8 / w_scale)         (max|input| / 127)
        │                                  │
        ▼ H2D (cached)                     │
  INT8 Weight (device)                     │
        │                                  │
        └──────────┬───────────────────────┘
                   ▼
        aclnnQuantize(input, act_scale) → INT8 act
                   │
                   ▼
        aclnnQuantMatmulV3(w_i8, a_i8, combined_scale) → FP16 output
```

### Weight Preprocessing Cache

- **Key:** `src0->data` (device pointer, constant for model lifetime)
- **Identity check:** `K`, `N`, `ne[2]`, `ne[3]`
- **Storage:** `aclrtMalloc` persistent (survives compute pool resets)
- **Thread safety:** `std::mutex`
- **Cost:** Cache miss = D2H dequant + FP32 requant + H2D (one-time per weight tensor). Cache hit = O(1) pointer lookup.

### Shape-Dependent Dispatch

```
if (type == Q8_0) {
    if (W8A8 enabled && N >= 2048) → W8A8 (aclnnQuantize + aclnnQuantMatmulV3)
    else                           → V2   (aclnnWeightQuantBatchmatmulV2)
}
```

S2 (K-proj 4096×1024) and S3 (V-proj 4096×1024) fall back to V2 because W8A8's ACT_SCALE overhead (~50us) exceeds V2's total latency (~50us) for small-N shapes.

## Correctness

### Gate Evidence

| Gate | Criterion | Result |
|------|-----------|--------|
| **test-backend-ops** | 35/35 Q8_0 MUL_MAT NMSE ≤ 5e-4 | **PASS** (Phase 1b) |
| **Benchmark sanity** | 12/12 NMSE ≤ 5e-4 (4 shapes × 3 paths) | **PASS** (Phase C4 Step 1) |
| **E2E no crash** | Full model load + prefill + decode | **PASS** (C1) |
| **Non-regression** | 35/35 W8A8=0 identically PASS | **PASS** (Phase 1b) |

### NMSE Comparison (Phase 1c Sanity)

| Shape | F16_ND | V2 | W8A8 |
|-------|--------|-----|------|
| S1 Q-proj (4096×4096) | 4.51e-08 | 8.45e-08 | 1.41e-07 |
| S2 K-proj (4096×1024) | 4.35e-08 | 9.34e-08 | 2.84e-07 |
| S5 FFN-gate (4096×12288) | 4.37e-08 | 8.88e-08 | 2.77e-07 |
| S7 FFN-down (12288×4096) | 4.30e-08 | 8.78e-08 | 1.43e-07 |

All paths well within 5e-4 threshold. W8A8 ~3× noisier than F16 (~2× vs V2), consistent with INT8×INT8→FP16 quantization.

## Strategic Decision: F16 Primary, W8A8 Opt-In

### Why Not Default?

**F16 is faster for every single matmul shape on Ascend 910B2C.** The oracle analysis (per-shape min across all paths) shows F16_ND wins all 7 model shapes at 311.6us model-weighted, vs W8A8 at 776.1us.

W8A8's speed advantage is relative to the slow Q8_0 V2 path, not to F16. W8A8 makes Q8_0 models usable (recovering ~86% of the F16→Q8_0 performance gap) but cannot beat F16.

### When to Use W8A8

- **Memory constraint:** Model too large for FP16 (16GB+ for MiniCPM-O 4.5)
- **Q8_0 deployment:** Any Q8_0 model running on CANN
- **Best Q8_0 speed:** 4.76× faster matmul vs default V2 path

```bash
# Memory-constrained: Q8_0 model with W8A8 acceleration
GGML_CANN_W8A8=1 ./llama-omni-server -m model-Q8_0.gguf ...
```

### When NOT to Use

- **F16 model:** No effect (W8A8 only triggers for Q8_0 weights)
- **Sufficient memory:** Use F16 directly (3.9× faster matmul than W8A8)

## Limitations & Future Work

### Current Limitations
1. **ACT_SCALE overhead:** 42.7% of W8A8 latency is D2H + CPU max scan (~57us). NPU-side `aclnnReduceMax` not available in CANN 9.1.
2. **Per-tensor quantization:** Single scale for all weight elements, discards Q8_0's per-group precision. No accuracy gap observed in practice.
3. **No fused kernel:** CANN has no single Quantize+Matmul fused operator; the two-kernel approach adds ~30us Quantize overhead.

### Deferred
- ACT_SCALE elimination via NPU-side reduce (blocked on CANN API)
- Per-group weight×act scales (no accuracy gap to motivate)
- MUL_MAT_ID support (MoE — F16 path already covers this)
- W8A8 as F16 replacement (requires CANN QuantMatmul kernel improvement > 2.5×)

## Key Files

| File | Role |
|------|------|
| `ggml/src/ggml-cann/aclnn_ops.cpp` | W8A8 implementation, cache, dispatch |
| `ggml/src/ggml-cann/ggml-cann.cpp` | `cannd_w8a8_enabled()` env gate |
| `phase1c_w8a8_bench.cpp` | Standalone performance + correctness benchmark |
| `benchmarks/results/phase1c_formal_results.csv` | Timing data (14 shapes × 4 paths) |
| `benchmarks/results/phase1c_sanity_results.csv` | Validation data (4 shapes × 3 paths) |

## References

- Phase A: F16 baseline calibration → [[f6-phase-a-f16-calibration-complete]]
- Phase B: Q8_0 A/B → [[f6-phase-b-complete]]
- Phase C1: W8A8 V3 benchmark → [[f6-task-c1-v3-benchmark-complete]]
- Phase C4 1c: Performance A/B → [[f6-c4-phase1c-complete]]
- Phase C4 Sanity Gate → [[f6-c4-sanity-gate-pass]]
- Phase C4 Phase 2 → [[f6-c4-phase2-progress]]
