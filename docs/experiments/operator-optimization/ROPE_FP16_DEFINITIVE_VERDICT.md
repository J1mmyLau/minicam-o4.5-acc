# P7-C: RoPE FP16 A/B Configuration Audit — DEFINITIVE VERDICT

**Date:** 2026-07-28 08:15 UTC
**Binary:** `f8b14c8e` (rebuild after debug removal)
**Method:** Source-level instrumentation of `ggml_cann_rope()` with static counters

---

## 1. Configuration Validity: INVALID

### P6/P4 Profiling Configuration

Both the P4 msprof profiling AND the P6 RoPE FP16 msprof verification used:

```
-ngl 0
```

**Evidence from `profiles/decode-speak/PROF_000001_.../host/sample.json`:**
```json
"app_parameters":"-m ... -ngl 0 --omni --test ..."
```

**Evidence from `profiles/decode-speak/rope_fp16/PROF_000001_.../host/sample.json`:**
```json
"app_parameters":"-m ... -ngl 0 --omni --test ..."
```

### P7-B A/B Test Configuration

The RoPE FP16 A/B script (`run_rope_fp16_ab.sh`) also used:

```
-ngl 0
```

### Production Configuration

The production candidate uses:

```
Talker n_gpu_layers = 8 (per LLAMA_CPP_OMNI_OPTIMIZATION_CLOSEOUT.md)
```

**Verdict:** `ROPE_AB_CONFIGURATION_INVALID` — Both profiling and A/B used `-ngl 0` instead of production `-ngl 8`. The CANN RoPE path was NOT exercised for the Talker LLM layers.

---

## 2. CANN RoPE Path Verification (Source-Level Instrumentation)

### Method

Added static counters to `ggml_cann_rope()` in `aclnn_ops.cpp:2861`:

```cpp
static int rope_call_count = 0;
static int rope_fp16_count = 0;
rope_call_count++;
// ...
if (rope_use_fp16) rope_fp16_count++;
fprintf(stderr, "[CANN_ROPE_DEBUG] call#%d fp16_hits=%d use_fp16=%d src_type=%s dims=%lld\n", ...);
```

### Results

| Configuration | CANN RoPE Called? | call count (24s) | src_type | fp16_hits |
|---------------|-------------------|---------------------|----------|-----------|
| ngl=0, FP16=0 | NO | 0 | N/A | 0 |
| ngl=8, FP16=0 | **YES** | 1500+ | **f32** | 0 |
| ngl=8, FP16=1 | **YES** | 500+ (partial) | **f32** | 0 |

### Critical Finding

```text
src0->type is ALWAYS GGML_TYPE_F32

The GGML_CANN_ROPE_FP16 optimization gate:
  rope_use_fp16 = (rope_fp16_enabled && src0->type == GGML_TYPE_F16)
  
Since src0->type == GGML_TYPE_F32 always, rope_use_fp16 is ALWAYS false.

GGML_CANN_ROPE_FP16=1 has ZERO EFFECT on MiniCPM-o decode-to-speak path.
```

### Why src0 is F32

The GGML compute graph for MiniCPM-o ALWAYS passes F32 tensors to RoPE operations. This is a graph-level decision made during model graph construction, likely because:
1. RoPE is numerically sensitive (cos/sin precision)
2. The GGML graph may upcast F16 → F32 for RoPE internally
3. The CANN backend receives the F32 tensor directly

**The GGML_CANN_ROPE_FP16 optimization can only work if the model graph passes F16 tensors to RoPE. This is NOT the case for MiniCPM-o.**

---

## 3. Impact on Profiling Data

| Dataset | ngl value | Talker LLM layers | CANN RoPE calls | Data validity |
|---------|-----------|-------------------|--------------------|---------------|
| P4 baseline msprof | 0 | ALL on CPU | From T2W+vision only | **MIS-SCOPED** |
| P6 RoPE FP16 msprof | 0 | ALL on CPU | From T2W+vision only | **MIS-SCOPED** |
| P7-B RoPE A/B (pairs.csv) | 0 | ALL on CPU | NONE for Talker | **INVALID** |

The CANN kernel execution in the P4 profiling trace (0.164s kernel time, 7,956 RoPE calls) originates from:
- **Vision encoder** (always CANN)
- **Token2Wav model** (Flow=CANN, has transformer layers with RoPE)

These are VALID CANN kernels but NOT from the Talker LLM (the primary optimization target with 27 layers).

### Impact on KERNEL_CANDIDATE_RANKING.md

The candidate ranking's operator-level data (RoPE kernel time, ADD/RMSNorm counts) may need re-auditing against `-ngl 8` profiling. However:

| Finding | Still Valid? | Reason |
|---------|-------------|--------|
| Wait time dominance (72s) | YES | Runtime API calls are host-side, independent of ngl |
| `aclrtSetDevice` 6,559 calls | YES | Host-side overhead, cross-model |
| CANN kernel time (0.164s) | NEEDS RE-VERIFY | With ngl=8, Talker LLM layers add CANN kernel execution |
| RoPE as % of kernel time | NEEDS RE-VERIFY | With ngl=8, more RoPE calls from Talker layers |
| ADD+RMS_NORM pattern | YES | Graph structure confirmed at source level |

---

## 4. P6 / P7-C Verdict

```text
P6_IMPLEMENTATION            = PASS         (code complete, builds, smoke OK)
P6_BUILD_AND_SMOKE           = PASS
P6_ROPE_KERNEL_LOCAL_SPEEDUP = WEAK_POSITIVE (+4.1%, but from T2W RoPE, not Talker)
P6_EXPLICIT_CAST_HYPOTHESIS  = DISPROVEN    (explicit casts fused by CANN runtime)
P7_AB_CONFIGURATION          = INVALID      (-ngl 0 instead of production -ngl 8)
P7_ROPE_FP16_PATH_HIT        = NEVER        (src0->type always F32, rope_use_fp16 always false)
P7_ROPE_FP16_EFFECT_ON_TALKER= ZERO         (FP16 gate cannot activate with F32 inputs)

FINAL_VERDICT: REJECTED_WITH_EVIDENCE

Evidence chain:
  1. ngl=0 → Talker LLM layers on CPU → CANN RoPE NEVER called (for Talker)
  2. ngl=8 → CANN RoPE IS called, but src0->type is always F32
  3. GGML_CANN_ROPE_FP16 gate: rope_use_fp16 = (enabled && src0->type == F16)
  4. src0->type NEVER F16 → rope_use_fp16 ALWAYS false → optimization NEVER activates
  5. This is a FUNDAMENTAL dtype incompatibility, not a bug

DEFAULT_ON = NO  (unconditionally, regardless of A/B data)
```

---

## 5. Next Steps (Post P7-C)

1. **Remove RoPE FP16 from active candidates** — The GGML graph cannot provide F16 RoPE inputs
2. **Re-profile with `-ngl 8`** to get correct Talker LLM CANN operator data
3. **Proceed to verified Top-1 candidates:**
   - V0: Enable `GGML_CANN_OPERATOR_FUSION` (CANN ADD+RMSNorm) — already implemented
   - Candidate E: Runtime Overhead Reduction (`aclrtSetDevice` caching, sync reduction)
4. **OP-002 AscendC fusion** only if V0 fusion doesn't match or is insufficient

---

**Commit this as evidence of negative result (valid negative — NOT a failure)**
