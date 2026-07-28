# P8: Technology Stack Decision — Operator Optimization

**Date:** 2026-07-28 07:38 UTC
**Based on:** P7 candidate ranking, P4 profiling data, P6 RoPE F16 experiment

---

## 1. Decision Summary

```text
PRIMARY STACK (Priority 1):     GGML-CANN dispatch optimization (no custom kernel)
SECONDARY STACK (Priority 2):   CANN ACLNN existing fusion enablement
TERTIARY STACK (Priority 3):    AscendC custom kernel (only if Priority 1+2 insufficient)
REJECTED:                        TileLang, Triton Ascend, CATLASS (for current candidates)
```

---

## 2. Candidates Mapped to Tech Stacks

| Rank | Candidate | Required Stack | Rationale |
|------|-----------|---------------|-----------|
| **1** | **E: Runtime Overhead** | GGML-CANN C++ dispatch | `aclrtSetDevice` caching, stream sync reduction, memcpy batching. Pure host-side changes. |
| **2** | **A: ADD+RMSNorm Fusion** | CANN ACLNN | `aclnnAddRmsNorm` already exists. Requires graph pattern matching + `GGML_CANN_OPERATOR_FUSION` enablement. |
| 3 | C: Custom RoPE | AscendC | Replace `aclnnRotaryPositionEmbedding` decomposition with single kernel. F16 natively. |
| — | F: Skinny MatMul | REJECTED | MatMul already optimized, 67-82% Cube utilization |
| — | D: KV ScatterUpdate | REJECTED | Architectural barrier (423ms GatherV2 wait), not operator fix |
| — | B: Custom Add+RMSNorm | REJECTED | CANN fusion already exists (Candidate A) |

---

## 3. Priority 1: GGML-CANN Dispatch (Candidate E)

### What to fix

| Issue | Current | Fix | Estimated Saving |
|-------|---------|-----|------------------|
| `aclrtSetDevice` | 6,559 calls (798ms) | Cache with static flag, call once | ~790ms |
| `aclrtSynchronizeStream` | 46,914 calls (269ms) | Audit redundant syncs in decode loop, remove if not needed | ~100-200ms |
| `aclrtMemcpy` (sync) | 25,226 calls (971ms) | Identify async-safe copies, convert to async | ~300-500ms |
| `aclrtMemcpy` in graph capture | 25,226 total | Check if graph capture already handles async | TBD |
| **Total target** | **~2.0s** | **Pure dispatch optimization** | **~1.0-1.5s (0.5-0.75% E2E)** |

### Implementation approach

```cpp
// In ggml-cann graph execution / device manager:
static int  cann_current_device = -1;  // Cached SetDevice
static bool cann_device_set     = false;

// Replace per-op aclrtSetDevice(0) with:
if (!cann_device_set) {
    ACL_CHECK(aclrtSetDevice(0));
    cann_device_set = true;
}

// Audit SynchronizeStream in decode loop:
// - Remove syncs between independent operators
// - Keep syncs only at graph boundaries
// - Use events for producer-consumer patterns instead of full stream sync
```

**Gate:** `GGML_CANN_REDUCE_RUNTIME_OVERHEAD` env var, default OFF
**Fallback:** All `aclrtSetDevice` and `aclrtSynchronizeStream` calls preserved as-is

---

## 4. Priority 2: CANN ACLNN Fusion (Candidate A)

### What to fix

The `aclnnAddRmsNorm` fused operator already exists in the codebase:
- Implemented in `ggml/src/ggml-cann/aclnn_ops.cpp`
- Gated by `GGML_CANN_OPERATOR_FUSION` (OFF by default)

### Steps

1. **Audit graph pattern**: Check if MiniCPM-o decode graph has contiguous ADD→RMS_NORM nodes
2. **Enable fusion gate**: `GGML_CANN_OPERATOR_FUSION=1`
3. **Verify fusion activation**: Count `aclnnAddRmsNorm` calls vs Add+RmsNorm calls
4. **Run paired A/B**: Wall clock, kernel count, wait time

### Risk

- Pattern may not match if GGML graph has them as non-adjacent nodes
- Performance benefit depends on actual fusion rate
- Zero correctness risk (CANN-provided fused op, already tested)

**Gate:** Existing `GGML_CANN_OPERATOR_FUSION` (already implemented, just disabled)
**Fallback:** Individual Add + RmsNorm ops (current default)

---

## 5. Priority 3: AscendC Custom RoPE (Candidate C)

### When to pursue

ONLY if:
1. Priority 1 + Priority 2 don't deliver sufficient decode-to-speak improvement
2. P6 RoPE FP16 A/B shows measurable decode-to-speak benefit
3. The 56s RoPE wait time can be partially reduced (estimated 20-40%)

### Why AscendC (not TileLang, Triton, CATLASS)

| Stack | Verdict | Reason |
|-------|---------|--------|
| **AscendC** | **RECOMMENDED** | Direct hardware control, tiling for position encoding, F16 native, CANN 9.1 tested |
| TileLang | NOT READY | Skill registered but NOT_RUNNABLE in current CANN 9.1 env. Defer verification. |
| Triton Ascend | NOT READY | Skill present but NOT_REGISTERED (`npx skills list` doesn't show it). Environment compatibility unknown. |
| CATLASS | REJECTED | MatMul is NOT the bottleneck (Candidate F rejected). No CATLASS use case. |

### AscendC RoPE kernel design sketch

```cpp
// Replace: aclnnRotaryPositionEmbedding(x, cos, sin, mode, y)
// With:    custom_rope_fp16_ascendc(x_f16, cos_f32, sin_f32, y_f16)
//
// Single kernel that:
// 1. Applies cos/sin rotation to first rope_dims dimensions (F32 compute)
// 2. Copies remaining tail dimensions unchanged
// 3. Outputs F16 directly
// 4. Eliminates 5 ACLNN sub-tasks (Cos, Sin, Cast, Mul, RotaryPositionEmbedding)
//
// Expected: 1 launch instead of 5, ~30-50% wait time reduction
```

### Gate
`GGML_CANN_ROPE_ASCENDC` env var, default OFF
Fallback: `aclnnRotaryPositionEmbedding` (existing path, or `GGML_CANN_ROPE_FP16` if enabled)

---

## 6. Stack Rejection Matrix

| Stack | Status | Why Rejected (for current candidates) |
|-------|--------|--------------------------------------|
| **TileLang** | Present but NOT_RUNNABLE | TileLang skills discovered but environment compatibility with CANN 9.1 unconfirmed. Not needed for Priority 1 (pure C++) or Priority 2 (existing CANN ops). |
| **Triton Ascend** | NOT_REGISTERED | Not in `npx skills list`. No environment setup. Premature for current candidates. |
| **CATLASS** | Not applicable | MatMul is not a bottleneck (Candidate F rejected). |
| **Custom TileLang/Triton kernel** | Premature | Priority 1+2 don't need custom kernels. RoPE custom kernel (Priority 3) is best served by AscendC. |

---

## 7. Implementation Order

```text
PHASE 1 (this session):
  P7-C: Complete RoPE FP16 A/B after baseline finishes
  → If rejected: document REJECTED_WITH_EVIDENCE
  → If experimental: mark EXPERIMENTAL_OPT_IN, keep OFF

PHASE 2:
  P9-E: Implement Candidate E (Runtime Overhead Reduction)
  Stack: GGML-CANN C++ dispatch
  Gate: GGML_CANN_REDUCE_RUNTIME_OVERHEAD
  
PHASE 3 (parallel with Phase 2 if NPU available):
  P9-A: Audit and enable Candidate A (CANN ADD+RMSNorm Fusion)
  Stack: CANN ACLNN existing op
  Gate: GGML_CANN_OPERATOR_FUSION (already implemented)

PHASE 4 (deferred):
  Only if Phase 2+3 insufficient AND RoPE A/B shows decode-to-speak bottleneck
  → P9-C: AscendC Custom RoPE Kernel
```

---

## 8. Skill Registry Audit

From `npx skills list` (run at P2):

| Skill | Discoverable | Status for This Mission |
|-------|-------------|------------------------|
| model-infer-profiling | YES | Used (P4) |
| model-infer-perf-breakdown | YES | Used (P4-P5) |
| model-infer-sota-approach | YES | Plugin, 6 agents |
| ops-profiling | NO | Used msprof directly |
| ascendc-env-check | YES | Used (P2) |
| npu-arch | YES | Used (P2) |
| tilelang-* | FILES_PRESENT_NOT_REGISTERED | Deferred per policy |
| triton-* | NOT_REGISTERED | Not available |

---

**Decision filed. Proceed to P9 after P7-C A/B completion.**
