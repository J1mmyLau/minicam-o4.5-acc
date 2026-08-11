# OP002: Graph Pattern Audit — Residual Add + RMSNorm in MiniCPM-o

**Date:** 2026-07-28 08:00 UTC
**Source:** `tools/omni/voxcpm2/voxcpm2_transformer.cpp`

---

## 1. Graph Pattern Confirmed

### 1.1 Layer Forward Pattern

```cpp
// tools/omni/voxcpm2/voxcpm2_transformer.cpp:688-703
hidden = input;
for (int i = 0; i < cfg.n_layer; ++i) {   // n_layer = 27
    // === ATTENTION BLOCK ===
    residual = hidden;                        // C++ pointer copy, NOT a GGML node
    normed   = rms_norm(ctx, hidden, ...);    // GGML_OP_RMS_NORM
    attn_out = attention_forward(... normed);
    hidden   = ggml_add(ctx, residual, attn_out);  // GGML_OP_ADD (residual)

    // === FFN BLOCK ===
    residual = hidden;                        // C++ pointer copy
    normed   = rms_norm(ctx, hidden, ...);    // GGML_OP_RMS_NORM ← src[0] = ADD output!
    mlp_out  = mlp_forward(... normed);
    hidden   = ggml_add(ctx, residual, mlp_out);   // GGML_OP_ADD (residual)
}
```

### 1.2 Fusion-Relevant Pattern

```text
Attention Block:         FFN Block:
                         ↓
  RMS_NORM               ← GGML graph node N (NOT fusible — no preceding ADD)
  [attention ops]        ← Q, K, V, RoPE, attn, WO
  ADD                    ← GGML graph node N+M (residual connection)
                         
  RMS_NORM               ← GGML graph node N+M+1
                           src[0] = ADD.output = hidden
                           OP: GGML_OP_RMS_NORM
                           prev node: GGML_OP_ADD
                           Pattern: ADD → RMS_NORM ✓
  [FFN ops]              ← gate, up, SiLU, down
  ADD                    ← GGML graph node (residual connection, feeds next layer)
                         ↓
  RMS_NORM               ← next layer attention norm
                           src[0] = ADD.output = hidden
                           Pattern: ADD → RMS_NORM ✓
```

### 1.3 Pattern Count Per Decode Step

| Source | Count | Note |
|--------|-------|------|
| Attention ADD → FFN RMS_NORM | 27 | One per layer |
| FFN ADD → next layer Attention RMS_NORM | 26 | Between layers 0-1, 1-2, ..., 25-26 |
| Final FFN ADD → final RMS_NORM | 1 | Line 703: `return rms_norm(ctx, hidden, weights.norm, eps)` |
| **Total potential** | **54** | Per decode token |

---

## 2. ggml_can_fuse Compatibility Check

### 2.1 Upstream GGML Check (`ggml-impl.h:699`)

```cpp
ggml_can_fuse(cgraph, i, {GGML_OP_ADD, GGML_OP_RMS_NORM})
```

| Condition | Check | Result |
|-----------|-------|--------|
| `i + 2 <= n_nodes` | Adjacent indices within bounds | ✅ |
| `node[i]->op == GGML_OP_ADD` | Correct op types | ✅ |
| `node[i+1]->op == GGML_OP_RMS_NORM` | Correct op types | ✅ |
| Both have COMPUTE flag | Both are computation ops | ✅ |
| `ggml_node_has_n_uses(node[i], 1)` | ADD output has exactly 1 consumer | **✅ (likely)** |
| `node[i+1]->src[0] == node[i]` | RMS_NORM consumes ADD output | ✅ (`rms_norm(ctx, hidden, eps)` where `hidden=ggml_add(...)`) |
| `ggml_are_same_shape(node[i], node[i+1])` | Same tensor shape | ✅ (both [n_embd, n_tokens]) |

### 2.2 CANN Custom Check (`ggml-cann.cpp:2237`)

```cpp
// ADD operands must have identical shape (no broadcast)
add_node->src[0]->ne[0] == add_node->src[1]->ne[0]
&& add_node->src[0]->ne[1] == add_node->src[1]->ne[1]
&& add_node->src[0]->ne[2] == add_node->src[1]->ne[2]
&& add_node->src[0]->ne[3] == add_node->src[1]->ne[3]
```

For decode:
- `src[0]` = residual = hidden_before_attention = [1152, 1, 1, 1]
- `src[1]` = attn_out = [1152, 1, 1, 1]

| Dim | src[0] | src[1] | Match? |
|-----|--------|--------|--------|
| ne[0] | 1152 | 1152 | ✅ |
| ne[1] | 1 (decode) | 1 (decode) | ✅ |
| ne[2] | 1 | 1 | ✅ |
| ne[3] | 1 | 1 | ✅ |

**Verdict: Pattern SHOULD match for decode.**

### 2.3 Potential Blockers

1. **ggml_node_has_n_uses(node[i], 1)**: If `hidden` tensor from `ggml_add` is consumed by any OTHER GGML node (not just the next `rms_norm`), this fails. The code shows `residual = hidden` (C++ pointer) and `rms_norm(ctx, hidden, ...)`, which are the only uses. But GGML graph optimization passes (dead code elimination, common subexpression) could potentially invalidate this.

2. **DAG optimization reordering**: The upstream GGML DAG optimization could reorder nodes, breaking adjacency.

3. **No-op nodes between**: Any `GGML_OP_RESHAPE`, `GGML_OP_VIEW`, `GGML_OP_PERMUTE` or empty nodes between ADD and RMS_NORM would break adjacency. Code inspection shows none present.

---

## 3. Decode Shape Summary

| Parameter | Value | Status |
|-----------|-------|--------|
| H (n_embd) | 1152 | Fixed per layer |
| B (batch) | 1 | Decode is single-sequence |
| S (sequence step) | 1 | One token at a time |
| dtype | F32 or F16 | depends on backend |
| layers | 27 | All same pattern |
| ADD+RMS_NORM per step | up to 54 | ~27-54 based on actual graph |

---

## 4. Next Step: Runtime Verification

The pattern match needs runtime verification because:
1. GGML DAG optimization may reorder nodes
2. The `ggml_node_has_n_uses` condition is runtime-dependent
3. Non-adjacent nodes due to graph optimization passes

**Plan**: After A/B completes, run a single decode step with `GGML_CANN_OPERATOR_FUSION=1` and add a counter to verify:
- How many ADD→RMS_NORM patterns are detected
- How many `aclnnAddRmsNorm` calls are made vs individual Add + RmsNorm
- Graph is unchanged (no incorrect fusion)

---

## 5. Alternative: V1 AscendC Custom Kernel

If V0 CANN fusion fails to match:

### Fusion Semantics (Type A confirmed)
```
residual_out = x + residual     ← AscendC::Add
y = RMSNorm(residual_out, gamma) ← AscendC::RmsNorm<half, false>
```

### Decode-Optimized Tiling
- H=1152 fits in UB (192 KB) as a single tile
- isBasicBlock=false (B×S=1 fails 8-multiple)
- No DataCopyPad needed (2304 bytes = 32B aligned)
- No Double Buffer needed (single tile)

### Feature Gate
```
GGML_CANN_FUSED_ADD_RMSNORM=0  // default OFF, enum: baseline|cann_fusion|ascendc_custom
```

---

**Next: V0 runtime verification → A/B if fusion activates**
