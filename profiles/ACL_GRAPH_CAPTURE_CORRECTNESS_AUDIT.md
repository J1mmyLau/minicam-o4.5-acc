# ACL Graph Capture Correctness Audit

**Date:** 2026-07-29
**Status:** INITIAL_AUDIT — correctness verified for tested scenarios, 10 boundary conditions pending

---

## 1. Configuration

| Parameter | Value |
|-----------|-------|
| CMake option | `USE_ACL_GRAPH=ON` |
| Env var | `GGML_CANN_ACL_GRAPH=on` |
| Capture mode | `ACL_MODEL_RI_CAPTURE_MODE_RELAXED` |
| Min nodes threshold | `GGML_CANN_GRAPH_MIN_NODES=100` |
| LRU cache capacity | `GGML_CANN_GRAPH_CACHE_CAPACITY=12` |
| Stream sync | `aclrtSynchronizeStream` before `aclmdlRICaptureBegin` |
| CANN version | 9.1.0-beta.1 |
| Device | Ascend 910C (dav-2201) |

---

## 2. Graph Identity Cache Key

The `graph_lru_cache` key is derived from `ggml_cann_graph::create_from_cgraph(cgraph)`. Based on code audit:

| Component | Included in key? | Notes |
|-----------|-----------------|-------|
| n_nodes | ✅ Yes | Graph node count |
| Node op types | ✅ Yes | Per-node operation type |
| Tensor shapes | ✅ Yes | ne[] dimensions |
| Tensor dtype | ✅ Yes | Via tensor metadata |
| Tensor layout | Probable | Via nb[] strides |
| Device ID | ✅ Yes | Per-backend-context cache |
| Backend context | ✅ Yes | Separate cache per context |
| Stream/capture context | ❌ No | Single stream per context |
| Execution mode | ❌ No | Eager/capture mode not part of key |
| Workspace/galloc identity | ❌ No | Buffer addresses not in key |
| Model identity | ❌ No | No explicit model ID in key |
| Dynamic input addresses | ❌ No | H2D buffer addresses change per chunk |

**Risk:** If the same cgraph structure is used across different models or sessions, the cache may incorrectly return a graph captured with different weight buffers. This is mitigated by per-context cache isolation.

**Risk (RELAXED mode):** Operations that pass through during capture (H2D) may produce different results if buffer addresses change between capture and replay. This is mitigated by the Flow model's use of persistent tensor buffers.

---

## 3. Verified Scenarios

| Scenario | Result | Evidence |
|----------|--------|----------|
| Single test case (0000) | ✅ PASS | AUDIO_SUCCESS, 4 WAVs, RTF=0.28 |
| Multi test case (0000-0003) | ✅ PASS | AUDIO_SUCCESS, 21-29 WAVs, RTF=0.24 |
| Per-chunk graph reuse | ✅ PASS | 1 capture → 19+ cache HITs for n_nodes=11740 |
| LLM prefill reuse | ✅ PASS | 1 capture → 18+ HITs for n_nodes=2373 |
| LLM decode skip | ✅ PASS | n_nodes=3,5,15 graphs skip capture (below min_nodes) |
| Model loading + capture coexistence | ✅ PASS | RELAXED mode allows H2D during capture |
| No CANN errors | ✅ PASS | 0 rtMemcpyAsync errors, 0 ACL errors across all tests |
| Audio validity | ✅ PASS | 0 silence, 0 clipping, all WAVs valid (40KB+) |
| Vocoder compatibility | ✅ PASS | voc.compute unchanged (119→118ms, within noise) |

---

## 4. Pending Boundary Condition Tests

| # | Condition | Risk | Priority |
|---|-----------|------|----------|
| 1 | Different chunk shapes (dynamic seq_len) | Cache miss → recapture | HIGH |
| 2 | Session reset mid-capture | Capture state leak | HIGH |
| 3 | Abort during capture | Stream corruption | HIGH |
| 4 | Model reload after session | Stale graph with old buffer addresses | HIGH |
| 5 | Multiple concurrent sessions | Cross-session cache pollution | MEDIUM |
| 6 | Long-running stability (1hr+) | Cache eviction, memory growth | HIGH |
| 7 | KV cache HIT/MISS/OFF modes | Graph identity changes with cache state | MEDIUM |
| 8 | Multi-prefix isolation | Different prefix → different graph | MEDIUM |
| 9 | Clean-machine reproduction | Environment-specific capture behavior | HIGH |
| 10 | Capture failure fallback | Silent performance degradation | HIGH |

---

## 5. Known Limitations

1. **RELAXED mode semantics:** Operations that pass through during capture (H2D) are not recorded in the graph. If buffer addresses change between capture and replay, results may be incorrect. Currently mitigated by Flow model's persistent tensor buffers.

2. **No explicit model identity in cache key:** Graph identity is determined solely by cgraph structure. If two different models produce structurally identical graphs, they would share the same cache entry. Not a risk in current single-model setup.

3. **First-chunk penalty:** The first Flow chunk incurs capture overhead (~10-20ms additional). Acceptable for production.

4. **No capture failure detection:** If `aclmdlRICaptureEnd` or `aclmdlRIExecuteAsync` fail, there is no fallback to eager execution. The error propagates as a CANN error.

---

## 6. Fallback and Safety

| Mechanism | Status |
|-----------|--------|
| Env var disable (`GGML_CANN_ACL_GRAPH=off`) | ✅ Works, completely disables capture |
| Min nodes filter (`GGML_CANN_GRAPH_MIN_NODES`) | ✅ Works, skips small graphs |
| Per-context cache isolation | ✅ Prevents cross-model pollution |
| LRU eviction (capacity 12) | ✅ Prevents unbounded memory growth |
| Capture failure → error | ⚠️ No silent fallback; error propagates |
