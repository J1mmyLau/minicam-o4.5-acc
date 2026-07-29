# G2: ACL Graph Capture Cache-Key / Lifetime Audit

**Date:** 2026-07-29
**Status:** PASS — code audit complete, cache semantics verified

---

## Cache Key Components (from `ggml_graph_node_properties::has_matching_properties`)

| # | Component | Field | Risk |
|---|-----------|-------|------|
| 1 | n_nodes | `ggml_graph_properties.size()` | Size mismatch → definite MISS |
| 2 | Buffer address (per node) | `node->data` | Model reload → realloc → MISS (CORRECT) |
| 3 | Buffer address exception | `GGML_OP_VIEW` skips addr check | VIEW aliases memory; addr changes expected |
| 4 | Op type | `node->op` | Different op → MISS |
| 5 | Tensor dtype | `node->type` | Different dtype → MISS |
| 6 | Shape (per node) | `node->ne[0..3]` | Dynamic chunk len → MISS → recapture |
| 7 | Strides (per node) | `node->nb[0..3]` | Layout change → MISS |
| 8 | Src buffer address | `src->data` | Weight reload → MISS (CORRECT, same exception for VIEW) |
| 9 | Src dtype | `src->type` | Different src type → MISS |
| 10 | Src shape | `src->ne[0..3]` | Different input shape → MISS |
| 11 | Src strides | `src->nb[0..3]` | Different layout → MISS |
| 12 | Op params | `node->op_params` (memcmp) | Different epsilon, dim, etc. → MISS |

## Cache Lifetime

| Property | Implementation | Verdict |
|----------|---------------|---------|
| Scope | Per `ggml_backend_cann_context` | ✅ Isolated per context |
| Capacity | `GGML_CANN_GRAPH_CACHE_CAPACITY` (default 12) | ✅ Configurable, bounded |
| Eviction | LRU: back evicted on overflow | ✅ Standard LRU |
| Promotion | `find_and_move_to_front` on hit | ✅ MRU on access |
| Teardown | `~ggml_cann_graph_lru_cache()` calls `clear()` | ✅ No leak |
| Graph destroy | `~ggml_cann_graph()` calls `aclmdlRIDestroy` | ✅ CANN resource freed |

## Capture/Replay Flow

```
graph_compute(cgraph):
  1. Check GGML_CANN_PREFILL_USE_GRAPH → if prefill AND seq_len>1, skip graph
  2. Check acl_graph_mode (GGML_CANN_ACL_GRAPH env) → if off, skip graph
  3. Check n_nodes < GGML_CANN_GRAPH_MIN_NODES (100) → if too small, skip graph
  4. find_and_move_to_front(cgraph) → HIT or MISS
  5a. HIT: graph_capture_required=false → evaluate op-by-op (SKIPPED: graph replay replaces it)
  5b. MISS: create_from_cgraph + push → graph_capture_required=true
  6. If capture_required: SynchronizeStream + CaptureBegin(RELAXED) → op-by-op → CaptureEnd
  7. ExecuteAsync(matched_graph) → graph replay
```

## Verified Semantics

| Scenario | Expected | Mechanism |
|----------|----------|-----------|
| Flow model (n=11740) → capture + reuse | ✅ Verified | 1 capture, 19+ HITs |
| LLM prefill (n=2373) → capture + reuse | ✅ Verified | 1 capture, 18+ HITs |
| LLM decode (n=3-15) → skip | ✅ Verified | MIN_NODES=100 filter |
| Dynamic shape → recapture | ✅ Expected | shape in cache key |
| Model reload → recapture | ✅ Expected | buffer addr in cache key |
| Cross-context isolation | ✅ Expected | per-context cache object |

## Known Limitations (from code audit)

1. **No capture failure fallback** (line ~2360): if `aclmdlRICaptureEnd` or `ExecuteAsync` fails, error propagates as `ACL_CHECK` assertion. No fallback to eager execution.
2. **Buffer address in key** means two contexts loading the same model each capture independently. Not a bug, but captures are not shared across contexts.
3. **RELAXED mode** allows H2D during capture but does not record it in graph. Mitigated by Flow model's persistent tensor buffers.

## Verdict

**G2: PASS.** Cache key semantics are correct, LRU lifetime is bounded, per-context isolation is sound. The VIEW exception for buffer addresses is necessary and correct. The min_nodes filter correctly prevents wasted capture on unreusable LLM decode graphs.
