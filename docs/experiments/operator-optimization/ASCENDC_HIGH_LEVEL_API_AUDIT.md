# OP002: AscendC High-Level API Compatibility Audit

**Date:** 2026-07-28 08:00 UTC
**CANN Version:** 9.1.0-beta.1
**NPU Architecture:** dav-2201 (Ascend 910C)
**Target:** MiniCPM-o 4.5 Q4_K_M, n_embd=1152, n_head=16, n_layer=27

---

## 1. API Discovery Summary

### 1.1 AscendC::RmsNorm

| Item | Status |
|------|--------|
| **Header** | `/usr/local/Ascend/cann-9.1.0-beta.1/aarch64-linux/asc/include/adv_api/normalization/rmsnorm.h` |
| **Signature** | `AscendC::RmsNorm<T, isBasicBlock>(dstLocal, srcLocal, gammaLocal, sharedTmpBuffer, epsilon, tiling)` |
| **Supported dtypes** | `half`, `float` |
| **Supported architectures** | 2201, 2002, 3510, 3003, 3113 |
| **910C support** | YES (arch 2201) |
| **Status** | **AVAILABLE** |

### 1.2 RmsNorm Tiling Functions

| Item | Status |
|------|--------|
| **Header** | `/usr/local/Ascend/cann-9.1.0-beta.1/aarch64-linux/asc/include/adv_api/normalization/rmsnorm_tiling.h` |
| `GetRmsNormMaxMinTmpSize()` | AVAILABLE — computes tmp buffer requirements |
| `GetRmsNormTilingInfo()` | AVAILABLE — computes tiling params from shape |
| `RmsNormTiling` struct | AVAILABLE — defined in `adv_api/kernel_tiling.h:565` |
| **Status** | **AVAILABLE** |

### 1.3 AscendC::Axpy

| Item | Status |
|------|--------|
| **Header** | `/usr/local/Ascend/cann-9.1.0-beta.1/aarch64-linux/asc/include/adv_api/math/axpy.h` |
| **Signature** | `AscendC::Axpy<T, U, isReuseSource>(dstTensor, srcTensor, scalarValue, sharedTmpBuffer, calCount)` |
| **Semantics** | `dst = src * scalar + dst` |
| **Arch 2201 path** | Uses `axpy_common_impl.h` (not the 3510-optimized path) |
| **Documentation note** | Axpy is implemented via Muls + Add for better precision; not guaranteed to compile to single FMA |
| **Status** | **AVAILABLE (common path for 2201)** |

### 1.4 AscendC::Add (Vector)

| Item | Status |
|------|--------|
| **Header** | `basic_api/impl/kernel_operator_vec_binary_intf_impl.h` |
| **Signature** | `AscendC::Add<T>(dst, src0, src1, mask, repeat, params)` |
| **Status** | **AVAILABLE (basic API)** |

### 1.5 DataCopyPad

| Item | Status |
|------|--------|
| **Header** | `basic_api/impl/kernel_operator_data_copy_intf_impl.h` |
| **Status** | **AVAILABLE** |
| **Note** | Only needed if row_bytes != 32B aligned |

### 1.6 TPipe / TQue / InitBuffer

| Item | Status |
|------|--------|
| **Headers** | `basic_api/impl/kernel_tpipe_impl.h`, `kernel_tpipe_base.h`, `kernel_tquesync_impl.h` |
| **InitBuffer** | AVAILABLE — `TPipe::InitBuffer` with buffer count |
| **Double Buffer** | AVAILABLE via buffer count=2 |
| **Status** | **AVAILABLE** |

---

## 2. RmsNorm BasicBlock Compatibility

### 2.1 Shape Constraints (from implementation)

From `rmsnorm_common_impl.h` (arch 2201):
```cpp
constexpr uint32_t BASIC_BLK_HLENGTH  = 64;   // H must be multiple of 64
constexpr uint32_t BASIC_BLK_BSLENGTH = 8;    // B*S must be multiple of 8
```

The `isBasicBlock` template parameter enables:
1. **ReduceSum**: Splits H into n×64 blocks, uses vector Add to reduce to 1 block, then RepeatReduceSum (vs. generic pairwise reduce)
2. **FirstAxisBrcMul**: Uses BasicBlockBrc when `bsLength > 8 && bsLength > hLength/64`
3. **LastAxisBrcMul**: Uses 64-element block tiling with Repeat Mul

### 2.2 MiniCPM-o Decode Shape Assessment

| Parameter | Value | BasicBlock Required | Result |
|-----------|-------|---------------------|--------|
| n_embd (H) | 1152 | H ≤ 2040 | **PASS** (1152 ≤ 2040) |
| H % 64 | 1152/64 = 18 | H % 64 == 0 | **PASS** (1152 % 64 = 0) |
| B × S (decode) | 1 | (B×S) % 8 == 0 | **FAIL** (1 % 8 = 1) |
| sizeof(half) × H | 1152 × 2 = 2304 | 32B alignment | **PASS** (2304 % 32 = 0) |

### 2.3 Verdict

**BasicBlock fast path NOT available for decode (B=1, S=1).**

The RmsNorm high-level API still works with `isBasicBlock=false` (default), but:
- Uses `RmsNormGenericReduceSum` (pairwise reduce instead of block reduce)
- Uses `RmsNormGeneralFirstAxisBrcMul` (scalar broadcast instead of vector broadcast)
- Performance gap vs BasicBlock: TBD by microbenchmark

### 2.4 Batch Scenarios Where BasicBlock WOULD Work

| Scenario | B | S | B×S | BasicBlock? |
|----------|---|---|-----|-------------|
| Decode (single token) | 1 | 1 | 1 | NO |
| Prefill (10 tokens) | 1 | 10 | 10 | NO (10%8=2) |
| Prefill (8 tokens) | 1 | 8 | 8 | **YES** |
| Batch decode (8 seqs) | 8 | 1 | 8 | **YES** |
| Batch decode (16 seqs) | 16 | 1 | 16 | **YES** |

---

## 3. Row Alignment Check

```
row_bytes = H × sizeof(half) = 1152 × 2 = 2304 bytes
2304 % 32 = 0 → naturally 32B aligned
```

**DataCopyPad is NOT needed** for the base hidden dimension. The row is naturally aligned.

---

## 4. Double Buffer Assessment for Decode

| Condition | Value | Verdict |
|-----------|-------|---------|
| H needs multi-tile? | 1152 / UB capacity — depends on tiling | Possibly, but 1152 half elements = 2304 bytes fits in 192KB UB easily |
| Multiple tiles for overlap? | With 1152 fitting in one tile, no second tile | **NO** |
| Data transfer overlaps compute? | Single tile → transfer then compute → no overlap | **NO** |

**Double Buffer is NOT beneficial for decode (single-tile fits entirely in UB).**

Only consider Double Buffer if:
- Future tiling strategy splits H across multiple tiles for better parallelism
- Larger batch sizes create more rows that can be pipelined

---

## 5. Existing CANN Fusion (aclnnAddRmsNorm)

### 5.1 Implementation Status

| Item | Status |
|------|--------|
| **ACLNN operator** | `aclnnAddRmsNorm` — CANN-provided fused op |
| **GGML-CANN wrapper** | `ggml_cann_op_add_rms_norm_fused()` in `aclnn_ops.cpp:4327` |
| **Pattern matching** | `ggml_cann_can_fuse(cgraph, i, {GGML_OP_ADD, GGML_OP_RMS_NORM})` in `ggml-cann.cpp:2278` |
| **Feature gate** | `GGML_CANN_OPERATOR_FUSION` env var (parse_bool) |
| **Default** | OFF (empty string → parse_bool → false) |
| **Broadcast support** | NOT supported — both ADD operands must have identical shape on all 4 dims |

### 5.2 Pattern Match Conditions

```cpp
// ggml_cann_can_fuse checks:
// 1. ggml_can_fuse(cgraph, node_idx, ops) — upstream GGML graph adjacency
// 2. ADD operands must have same ne[0..3] (no broadcast)
```

### 5.3 Remaining Questions

1. **Does MiniCPM-o graph have contiguous ADD→RMS_NORM?** — Needs runtime verification
2. **Are both operands same shape?** — Needs runtime dump
3. **What percentage of ADD+RMS_NORM calls does the pattern match?** — Needs msprof trace with fusion counting

---

## 6. API Recommendations for OP-002

### V0: Enable Existing CANN Fusion (LOWEST RISK)

```bash
GGML_CANN_OPERATOR_FUSION=1 ./build/bin/llama-omni-cli ...
```

- Zero code changes needed
- Already implemented and compiled
- Needs graph pattern verification first

### V1: AscendC Custom Kernel (if V0 insufficient)

If the CANN fusion doesn't activate or shows insufficient benefit:

```cpp
// Data flow:
CopyIn(x_f16, residual_f16, gamma_f16)
  → Add(residualLocal, xLocal, residualLocal)  // residual_out = x + residual
  → RmsNorm<half, false>(normLocal, residualLocal, gammaLocal, tmpBuf, eps, tiling)
     // isBasicBlock=false for decode (B×S=1 fails 8-multiple constraint)
CopyOut(normLocal)

// Key decisions:
// - Use AscendC::Add (not Axpy) for residual add — simpler, no scalar multiply needed
// - RmsNorm with isBasicBlock=false — decode shape doesn't qualify
// - No DataCopyPad — rows are naturally 32B aligned (2304 bytes)
// - No Double Buffer — single tile fits in UB (192KB)
// - Use TPipe — acceptable for V1, simplest programming model
```

### V2-V5: Only if V1 shows positive microbenchmark

- V2: Shape-specialized tiling for B=1,S=1,H=1152
- V3: DataCopyPad only if tail blocks appear
- V4: Double Buffer only if multi-tile tiling is adopted
- V5: Static Tensor + basic API only if TPipe overhead proves significant

---

## 7. Toolchain Readiness

| Tool | Status |
|------|--------|
| AscendC compiler (cannsim) | AVAILABLE |
| msprof | AVAILABLE |
| npu-smi | AVAILABLE (25.5.1) |
| CANN 9.1 beta.1 | INSTALLED, VERIFIED |
| NPU arch | dav-2201 (Ascend 910C) |
| NPU devices | 2× Ascend910, both OK |
| Custom op package | NOT installed (only needed for running custom ops; compilation still works) |

---

## 8. Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| BasicBlock unavailable → lower perf | HIGH (decode shape) | MEDIUM | Accept isBasicBlock=false; still get fusion benefit |
| CANN fusion already sufficient | MEDIUM | LOW | V0 first — if fusion works, skip AscendC entirely |
| GGML graph doesn't have ADD+RMSNorm pattern | MEDIUM | HIGH | Stop OP-002; redirect to verified Top-1 (Candidate E: Runtime) |
| TPipe overhead > benefit for tiny tensors | LOW | MEDIUM | V5 fallback: static Tensor + basic API |
| AscendC compile fails on 910C | LOW | HIGH | Fallback to CANN fusion only |

---

**Next: OP-002 Graph Pattern Audit → V0 CANN Fusion Verification**
