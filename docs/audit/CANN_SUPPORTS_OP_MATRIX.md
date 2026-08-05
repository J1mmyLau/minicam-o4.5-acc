# CANN Backend `supports_op` 完整矩阵

> **源码**: `ggml/src/ggml-cann/ggml-cann.cpp:2528-2828` (`ggml_backend_cann_supports_op`)
> **冻结 commit**: `bdd4550`
> **注意**: `supports_op` 只检查 op 类型/数据类型，不检查 tensor shape 或 batch size。`offload_op` 是独立的 batch-size gate。

---

## 列说明

| 列 | 含义 | 取值 |
|----|------|------|
| `STATIC_SUPPORTED` | CANN backend 源码中是否声明支持此 op | `YES` / `NO` / `CONDITIONAL` |
| `CONDITIONS` | `CONDITIONAL` 时的具体条件 | 源码条件 |
| `TARGET_GRAPH_USES_OP` | 此 op 是否出现在 MiniCPM-o 的 compute graph 中 | `LIKELY` / `UNLIKELY` / `UNKNOWN` |
| `RUNTIME_REACHED` | 冻结模型中此 op 是否实际命中 CANN backend | `NOT_MEASURED` |
| `OBSERVED_BACKEND` | 若已测量，实际执行 backend | `NOT_MEASURED` |
| `FALLBACK_COUNT` | 若触发 CPU fallback，次数 | `NOT_MEASURED` |
| `PER_CHUNK_RELEVANCE` | 此 op 是否在 decode chunk 关键路径 | `YES` / `NO` / `UNKNOWN` |

---

## 无条件支持 (STATIC_SUPPORTED=YES)

这些 op 在 CANN backend 始终返回 `true`，无任何前置条件：

| Op | TARGET_GRAPH | RUNTIME_REACHED | PER_CHUNK |
|----|-------------|-----------------|-----------|
| `GGML_OP_NONE` | UNLIKELY | NOT_MEASURED | NO |
| `GGML_OP_RESHAPE` | LIKELY (view op) | NOT_MEASURED | YES |
| `GGML_OP_VIEW` | LIKELY (view op) | NOT_MEASURED | YES |
| `GGML_OP_PERMUTE` | LIKELY (view op) | NOT_MEASURED | YES |
| `GGML_OP_TRANSPOSE` | LIKELY (view op) | NOT_MEASURED | YES |
| `GGML_OP_DUP` | LIKELY | NOT_MEASURED | UNKNOWN |
| `GGML_OP_SET` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_CPY` | LIKELY | NOT_MEASURED | YES |
| `GGML_OP_CONT` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_ADD` | LIKELY (residual) | NOT_MEASURED | YES |
| `GGML_OP_ADD1` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_SUB` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_MUL` | LIKELY (gating) | NOT_MEASURED | YES |
| `GGML_OP_DIV` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_RMS_NORM` | LIKELY (every layer) | NOT_MEASURED | YES |
| `GGML_OP_SQR` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_SQRT` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_CLAMP` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_DIAG_MASK_INF` | LIKELY (causal mask) | NOT_MEASURED | YES |
| `GGML_OP_SUM_ROWS` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_ARGSORT` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_ACC` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_GROUP_NORM` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_ARANGE` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_TIMESTEP_EMBEDDING` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_LEAKY_RELU` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_ARGMAX` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_COS` | LIKELY (RoPE) | NOT_MEASURED | YES |
| `GGML_OP_SIN` | LIKELY (RoPE) | NOT_MEASURED | YES |
| `GGML_OP_LOG` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_MEAN` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_PAD_REFLECT_1D` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_COUNT_EQUAL` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_GATED_LINEAR_ATTN` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_CONV_TRANSPOSE_1D` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_SSM_CONV` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_IM2COL` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_CONCAT` | LIKELY (KV cache) | NOT_MEASURED | YES |
| `GGML_OP_REPEAT` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_UPSCALE` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_POOL_2D` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_SUM` | LIKELY | NOT_MEASURED | UNKNOWN |
| `GGML_OP_L2_NORM` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_CROSS_ENTROPY_LOSS` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_SET_ROWS` | UNKNOWN | NOT_MEASURED | UNKNOWN |
| `GGML_OP_NORM` | LIKELY | NOT_MEASURED | UNKNOWN |

---

## 条件支持 (STATIC_SUPPORTED=CONDITIONAL)

### `GGML_OP_UNARY`

| 条件 | STATIC_SUPPORTED | TARGET_GRAPH | RUNTIME_REACHED |
|------|-----------------|-------------|-----------------|
| GELU / SILU / GELU_QUICK / TANH / RELU / SIGMOID / HARDSIGMOID / HARDSWISH / NEG / STEP / SIGN | YES | LIKELY (SILU in every FFN) | NOT_MEASURED |
| ABS / EXP / SOFT_SIGN / SOFT_PLUS / ELU / GELU_ERF / LOG_SIGMOID / SILU_BACK / 其他 | NO → CPU | UNKNOWN | NOT_MEASURED |

### `GGML_OP_GLU`

| 条件 | STATIC_SUPPORTED | RUNTIME_REACHED |
|------|-----------------|-----------------|
| F16 / F32 / BF16 / Q8_0 / Q4_0 | YES | NOT_MEASURED |
| 其他 dtype | NO → CPU | NOT_MEASURED |

### `GGML_OP_MUL_MAT`

| 条件 | STATIC_SUPPORTED | RUNTIME_REACHED |
|------|-----------------|-----------------|
| F16 / F32 / BF16 | YES | NOT_MEASURED |
| Q8_0 / Q4_0 且 `ggml_is_contiguous(src[0])` | YES | NOT_MEASURED |
| Q8_0 / Q4_0 但非连续 | NO → CPU | NOT_MEASURED |
| Q2_K / Q3_K / Q5_0 / Q5_1 / Q6_K / Q8_K / IQ 系列等 | NO → CPU | NOT_MEASURED |

### `GGML_OP_MUL_MAT_ID`

同 MUL_MAT + 额外 `src[0]->ne[2] == src[0]->ne[3]`（expert count consistency）。

### `GGML_OP_GET_ROWS`

| 条件 | STATIC_SUPPORTED |
|------|-----------------|
| F16 / F32 / BF16 / Q8_0 | YES |
| 其他 dtype | NO → CPU |

**注意**: `offload_op` 显式排除 `GGML_OP_GET_ROWS`（`&& op->op != GGML_OP_GET_ROWS`）。

### `GGML_OP_ROPE`

| 条件 | STATIC_SUPPORTED | 冻结模型命中? |
|------|-----------------|-------------|
| `ne[0] <= 896` | YES | `NOT_MEASURED`（MiniCPM-o head_dim 未确认） |
| `ne[0] > 896` | NO → CPU | `NOT_MEASURED` |
| ASCEND_310P 特定限制 | NO → CPU | N/A (910C) |

**关键风险**: 如果 MiniCPM-o 4.5 的 head_dim > 896，ROPE 会回退 CPU → 产生 split + sync + copy。这是当前静态审计中 **唯一可能影响主 LLM decode 的条件性 fallback**。建议确认 head_dim。

### `GGML_OP_PAD`

| 条件 | STATIC_SUPPORTED |
|------|-----------------|
| `op_params[8] == 0`（zero-padding） | YES |
| `op_params[8] != 0`（circular padding） | NO → CPU |

### `GGML_OP_SCALE`

| 条件 | STATIC_SUPPORTED |
|------|-----------------|
| `bias == 0.0f` | YES |
| `bias != 0.0f` | NO → CPU |

### `GGML_OP_SOFT_MAX`

| 条件 | STATIC_SUPPORTED |
|------|-----------------|
| `src[2] == NULL`（无 attention sinks） | YES |
| `src[2] != NULL`（attention sinks） | NO → CPU |

### `GGML_OP_FLASH_ATTN_EXT`

最复杂的条件检查：

| 条件 | STATIC_SUPPORTED | 冻结模型命中? |
|------|-----------------|-------------|
| ASCEND_310P | NO | N/A (910C) |
| Q/K 均为 F16（源码第一个检查） | YES | `NOT_MEASURED` |
| Q/K 非 F16（F32/BF16 被第一个检查短路） | NO → CPU | `NOT_MEASURED` |
| 输出 type 为 F16/F32/BF16 | YES | `NOT_MEASURED` |
| `src[4] == NULL`（无 attention sinks） | YES | `NOT_MEASURED` |
| `src[4] != NULL`（attention sinks） | NO → CPU | `NOT_MEASURED` |
| `src[1]->ne[0] == src[2]->ne[0]`（K/V head size 相等） | YES | `NOT_MEASURED` |
| `logitSoftcap == 0.0f` | YES | `NOT_MEASURED` |
| `logitSoftcap != 0.0f` | NO → CPU | `NOT_MEASURED` |

**源码注意** (line 2789): 存在双重 dtype 检查——第一个检查 `src[1]->type != F16 || src[2]->type != F16` 要求 K 和 Q 都是 F16，第二个检查允许 F32/BF16。第一个短路生效 → **FLASH_ATTN_EXT 实际上只支持 F16 Q/K/V**。F32/BF16 的 FA 会回退 CPU。

### `GGML_OP_OUT_PROD`

| 条件 | STATIC_SUPPORTED |
|------|-----------------|
| ASCEND_310P | NO |
| `src[0]->type` 为 F16 或 F32 | YES |
| 其他 dtype | NO → CPU |

### `GGML_OP_CUMSUM` / `GGML_OP_TRI` / `GGML_OP_FILL` / `GGML_OP_DIAG` / `GGML_OP_SOLVE_TRI`

全部要求 `src[0]->type == GGML_TYPE_F32`。

---

## `offload_op` 独立门控

```cpp
// ggml-cann.cpp:3001-3004
static bool ggml_backend_cann_offload_op(ggml_backend_dev_t dev, const ggml_tensor * op) {
    return op->ne[1] >= dev_ctx->op_offload_min_batch_size  // 默认 32
        && op->op != GGML_OP_GET_ROWS;  // GET_ROWS 永不 offload
}
```

**两层独立判断**:

| `supports_op` | `offload_op` | 效果 |
|---------------|-------------|------|
| true | true | op 可在 CANN 执行；权重在 CPU 时 scheduler 可提升到 CANN |
| true | false | op 可在 CANN 执行；但权重在 CPU 时留在 CPU（不触发 offload） |
| false | — | op 必须走 CPU，无论权重在哪 |

**Decode bs=1 影响**: `ne[1]=1 < 32` → `offload_op=false`。但这不影响 `-ngl 999`：所有权重已在 CANN，scheduler pass 1.wgt 直接将 op 分配到 CANN，不经过 pass 1.off。

---

## 不支持（→ CPU fallback）

所有未列出的 op 返回 `false`。常见的不支持类型：
- MUL_MAT 的非标准量化类型（Q2_K, Q3_K, Q5_0, Q5_1, Q6_K, Q8_K, IQ 系列）
- GET_ROWS 的 Q4_0
- 不支持的 UNARY 变体（ABS, EXP, SOFT_SIGN 等）
