# V0: CANN ADD+RMSNorm Fusion A/B — DEFINITIVE VERDICT

**Date:** 2026-07-28 08:41 UTC
**Binary:** `6913c972` (baseline), `d2f5a3b1` (diagnostic for P5+ FUSION_ON)
**Method:** 10 paired A/B (OFF vs ON), ngl=8 (production config), MEDIUM tc=4

---

## 1. E2E Wall-Time Result

| Metric | BASELINE | FUSION_ON | Δ |
|--------|----------|-----------|---|
| Mean wall_ms | 90,195 | 108,899 | +18,704ms |
| Mean wav_count | 16.0 | 20.9 | +4.9 |
| Mean ms/wav | 6,880 | 7,434 | +8.1% |
| Pair 10 (wavs=6 both) | 48,977 | 49,008 | **+31ms (+0.06%)** |

**Correlation(Δwav, Δwall): r = 0.999**

The wall-time delta across 10 pairs is PERFECTLY explained by wav count variation (LLM output non-determinism). The only pair with matched wav count (pair 10) shows +31ms — well within noise.

## 2. Why No Effect

### 2.1 Talker LLM Does NOT Fuse

The CANN fusion pattern `{GGML_OP_ADD, GGML_OP_RMS_NORM}` requires:
```
ggml_node_has_n_uses(add_node, 1) == true
```

Talker LLM residual connections create **2 uses** of the ADD output:
```
hidden = ggml_add(ctx, residual, attn_out)      ← ADD node
// ↓ 2 consumers
normed = rms_norm(ctx, hidden, ...)              ← use #1: RMS_NORM
hidden = ggml_add(ctx, residual, mlp_out)        ← use #2: residual skip (via residual=hidden pointer)
```

**The upstream `ggml_can_fuse()` rejects all Talker LLM ADD→RMS_NORM pairs before they reach the CANN backend.**

### 2.2 What DOES Fuse

Only `[4096,1,1,1]` tensors from a flow/projector model component fuse. Diagnostic output from `fusion1_pair5.stderr`:

```
[FUSION_TRACE] call#1-20 add_node='l_out-35' rms_norm='norm' shape=[4096,1,1,1]
```

This is a cross-modal component (LLM→T2W projector, 4096-dim). Even here, most layers fail with `uses=2`:
```
[FUSION_DIAG] ADD[0]=4096 fail: uses=2 add='l_out-28' rms='norm-29'
```

Only `l_out-35` succeeds — likely the final layer or a special non-residual connection.

### 2.3 CANN Kernel Time is <1% of Wall Time

From P4 profiling: CANN kernel time = 0.164s out of ~87s wall time (0.19%). Even a 50% kernel speedup saves <0.1% E2E. No wall-time A/B can detect this.

## 3. Verdict

```text
V0_CANN_FUSION_ACTIVATING           = YES (10+ calls/run, flow model only)
V0_CANN_FUSION_TALKER_LLM           = NEVER (ggml_node_has_n_uses fails)
V0_CANN_FUSION_E2E_EFFECT           = NO_SIGNAL (Δwall explained by Δwav, r=0.999)
V0_CANN_FUSION_WALL_TIME_VALIDITY   = INVALID (2.3x-41x LLM variance > 0.1% signal)
V0_CANN_FUSION_VIABLE_AS_OPT        = NO (needs graph-level fix for Talker LLM)

FINAL_VERDICT: INSUFFICIENT — E2E wall-time A/B cannot detect sub-1% effects.
The fusion works but only on non-Talker model components.
Talker LLM requires graph transformation to reduce ADD output use count from 2→1.
```

## 4. Path Forward

### 4.1 Enable Talker LLM Fusion (V0+)
- Insert a `GGML_OP_COPY` (identity) between the ADD output and the residual skip
- Reduces ADD output use count from 2→1, enabling upstream fusion check
- Cost: one COPY per layer (1152 bytes), negligible device time
- Risk: graph transformation must preserve correctness

### 4.2 V1: AscendC Dual-Output Fusion
- Custom kernel outputs BOTH residual_sum AND normalized result
- Avoids the use-count problem entirely
- Maximum memory bandwidth savings
- Complexity: requires AscendC kernel + Tiling implementation

### 4.3 Candidate E: Runtime Overhead Reduction
- `aclrtSetDevice` caching (~6,559 calls per run)
- `aclrtSynchronizeStream` reduction
- Independent of operator fusion, stacked benefits
- Low risk, ~1% E2E expected

## 5. Immediate Next Action

1. Expand diagnostic to trace 1152-dim tensors (confirm Talker LLM fusion failure root cause)
2. Evaluate V0+ (graph COPY insertion) vs V1 (AscendC dual-output) vs Candidate E
3. Proceed with highest-ROI candidate

---

**Data:** `/workspace/llama.cpp-omni-operator/profiles/cann_fusion_v0/pairs.csv`
**Diagnostic:** `fusion1_pair5.stderr` (FUSION_TRACE + FUSION_DIAG lines)
