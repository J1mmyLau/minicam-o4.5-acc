# Top-1 Operator Candidate Proposal

**Date:** 2026-07-28 07:00 UTC
**Based on:** `profiles/decode-speak/PROFILING_REPORT.md` (msprof CANN trace, 65,865 tasks)

---

## 1. Profiling Verdict: Add+RMSNorm REJECTED

The user's initial candidate (`Residual Add + RMSNorm`) has been evaluated against profiling evidence:

| Metric | Add | RmsNorm | Combined |
|--------|-----|---------|----------|
| Call count | 380 | 107 | 487 |
| Kernel time | 2,093 μs | 1,582 μs | 3,675 μs |
| Pct of CANN kernel | 1.3% | 1.0% | **2.2%** |
| Pct of total wall | 0.001% | 0.001% | **0.002%** |

**Decision: REJECTED by profiling evidence.**

The `aclnnAddRmsNorm` fused operator already exists in the codebase (gated by `GGML_CANN_OPERATOR_FUSION`). Even if it provided 100% speedup (eliminating both ops entirely), the end-to-end saving would be 0.0037s — undetectable in the ~200s decode-to-speak timeline.

---

## 2. Top-1 Candidate: RoPE Cast Elimination

### 2.1 Why RoPE

Within the 0.164s CANN kernel execution time:

| RoPE sub-operation | Count | Kern Time (μs) | Pct |
|-------------------|-------|----------------|-----|
| RotaryPositionEmbedding | 7,956 | 44,327 | 27.0% |
| Mul (RoPE internal) | ~15,912 | ~42,000 | ~25.5% |
| Tile (RoPE internal) | ~15,956 | 22,228 | 13.5% |
| Cos (RoPE internal) | 7,956 | 14,136 | 8.6% |
| Sin (RoPE internal) | 7,956 | 13,767 | 8.4% |
| **Cast (RoPE F16↔F32)** | **~5,300** | **~7,600** | **~4.6%** |
| **RoPE Total** | — | **~144,000** | **~87.6%** |

### 2.2 The Problem

In `ggml_cann_rope()` (`aclnn_ops.cpp:3088-3221`), when the model uses F16 activations:

```
F16 input → aclnn_cast(F32) → aclnnRotaryPositionEmbedding(F32) → aclnn_cast(F16) → F16 output
```

This F16→F32→F16 round-trip has two costs:
1. **Kernel time**: Each Cast takes ~1.4 μs — with 7,956 RoPE calls, that's ~22ms of kernel time (but msprof shows only ~7.6ms from Cast actually on the RoPE path)
2. **Memory**: Temporary F32 buffers allocated per RoPE call: `ggml_nelements(src0) * sizeof(float)` — for a 1×16×1×72 tensor, that's 1,152 × 4 = 4.6 KB per call (small but adds up)
3. **Wait time**: Additional task scheduling overhead per Cast

### 2.3 The Fix

`aclnnRotaryPositionEmbedding` accepts `aclTensor*` with configurable data type. The CANN documentation indicates this operator supports F16 input natively. The fix is:

1. **Try F16 directly**: Pass F16 tensors to `aclnnRotaryPositionEmbedding` without casting
2. **Fall back to F32**: If the operator rejects F16 (error), fall back to existing F32 path
3. **Gate**: `GGML_CANN_ROPE_FP16=1` to enable; default OFF preserves existing behavior

**Expected impact**:
- Kernel time: eliminate ~4.6% of 0.164s = 0.0075s savings
- Wait time: reduce ~5,300 Cast tasks from the scheduler queue → save ~1-2s
- End-to-end: ~1-2s improvement (~0.5-1% of decode-to-speak wall time)

### 2.4 Why Only ~1% Impact

CANN kernel time is only 0.08% of total wall time. The REAL bottleneck is:
- CANN task wait time: 72.3s (36%) — host-device scheduling overhead
- CPU TTS processing: ~128s (64%)

Any single-kernel optimization on CANN can at most save a few percent of the 0.164s kernel budget. The high-impact work (>10% end-to-end) requires:
1. Reducing CANN graph capture fragmentation (reduces 72s wait time)
2. Accelerating TTS CPU pipeline (reduces 128s CPU time)

These are out of scope for the current single-operator mission.

---

## 3. Implementation Plan

### 3.1 Code Change

File: `ggml/src/ggml-cann/aclnn_ops.cpp`
Function: `ggml_cann_rope()` (line 2861)

Changes:
1. Add env var check: `GGML_CANN_ROPE_FP16` (parse_bool, default false)
2. When enabled and src0 is F16: Create F16 tensors for cos/sin reshape, pass F16 to `aclnnRotaryPositionEmbedding`
3. Fall back to F32 path on error (catch, log, retry)

### 3.2 Non-functional requirements

- `GGML_CANN_ROPE_FP16` defaults to 0 (OFF) — preserves existing behavior
- When disabled, code path is identical to current (zero risk)
- When enabled and F16 fails, fall back to F32 (graceful degradation)
- Existing F32 path preserved intact

### 3.3 Verification

1. Build with change, verify compilation
2. Run smoke test: `--test` mode with 1 test case, compare output (should be identical)
3. Run msprof: verify Cast count decreased, RoPE kernel time reduced
4. E2E A/B: 3 runs each, measure wall clock difference

---

## 4. Rejected Alternatives

| Alternative | Reason Rejected |
|-------------|----------------|
| Add+RMSNorm fusion | 2.2% of 0.164s = 0.0037s. Already implemented. |
| MatMul optimization | 1.3% of kernel time. Already well-optimized (FractalNZ). |
| Custom AscendC RoPE kernel | `aclnnRotaryPositionEmbedding` is already hardware-optimized. Custom kernel unlikely to beat it. |
| QKV projection fusion | Requires GGML graph restructuring. Not a single-operator change. |

---

**Proposed by profiling evidence. Ready for implementation.**
