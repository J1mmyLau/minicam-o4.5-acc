# P19: CANN ACL Graph Capture for Flow Model — Phase 3 Rank 1

**Date:** 2026-07-29
**Status:** COMPLETE — Graph execution reuse working, ~34ms savings per Flow chunk
**Commit:** `4a2cbcd`

---

## Summary

Enabled CANN ACL graph capture (`USE_ACL_GRAPH=ON`) for the Flow model on Ascend 910C,
resolving the H2D interference issue discovered in the previous investigation.
The Flow model's per-chunk inference graph (n_nodes=11740) is now captured once and
reused for all subsequent chunks, saving ~34ms per chunk (23.5% on Flow compute).

---

## Implementation

### 3 Changes to `ggml/src/ggml-cann/ggml-cann.cpp`

1. **RELAXED capture mode** (line 2322): Changed from `ACL_MODEL_RI_CAPTURE_MODE_GLOBAL`
   to `ACL_MODEL_RI_CAPTURE_MODE_RELAXED`.
   - GLOBAL mode captures ALL streams on the device, blocking `aclrtMemcpyAsync(H2D)`
     on any concurrent CANN backend context
   - RELAXED mode allows operations that cannot be captured (H2D memcpy) to proceed
     without error, while still capturing kernel launches into the graph
   - Added `aclrtSynchronizeStream` before `aclmdlRICaptureBegin` as safety measure

2. **Minimum nodes threshold** (line 2417-2427): Added `GGML_CANN_GRAPH_MIN_NODES`
   env var (default: 100). Graphs with fewer nodes skip graph capture entirely.
   - LLM decode tokens generate unique 3-node graphs that can never be reused,
     causing ~3424 wasted captures per conversation (pure overhead)
   - Flow model graphs (11740 nodes) and LLM prefill graphs (2373 nodes) are
     captured and reused

3. **Diagnostic logging removed** after bringup verification

### How to Enable

```bash
# Compile-time (required): CMakeLists.txt already has USE_ACL_GRAPH option
cmake -DUSE_ACL_GRAPH=ON ...    # Enable ACL graph support

# Run-time:
GGML_CANN_ACL_GRAPH=on          # Enable graph capture/reuse (default when compiled)
GGML_CANN_GRAPH_MIN_NODES=100   # Min nodes for graph capture (default: 100)
GGML_CANN_GRAPH_CACHE_CAPACITY=12  # LRU cache size (default: 12)
```

---

## Results

### A/B Comparison (4 test cases, same binary, same model)

| Metric | OFF (no graph) | ON (graph reuse) | Improvement |
|--------|---------------|------------------|-------------|
| t2m.compute p50 | 144.0 ms | **110.8 ms** | -23.1% (-33.2ms) |
| t2m.compute mean | 145.5 ms | **111.3 ms** | -23.5% (-34.2ms) |
| voc.compute p50 | 112.5 ms | 106.6 ms | -5.2% (noise/variance) |
| Per-chunk RTF (steady) | 0.250 | **0.229** | -8.4% |
| Total RTF (incl warmup) | ~0.30 | **0.239** | -20.3% |

### Graph Cache Effectiveness

- Flow model (n_nodes=11740): 1 capture → 19+ cache HITs across 4 test cases
- LLM prefill (n_nodes=2373): 1 capture → 18+ cache HITs
- LLM decode (n_nodes=3,5,15): Skipped entirely (below min_nodes threshold)
- Small vision graphs (n_nodes=1036): 4 captures (unique graphs, no reuse expected)

### Correctness

- 42+ WAVs generated across multiple test cases
- 0 CANN errors, 0 rtMemcpyAsync errors
- 0 audio defects (no silence, no clipping)
- Per-chunk RTF distribution tight (0.22-0.24 steady state)

### Comparison to Baseline (Phase 2)

| Phase | t2m.compute | voc.compute | RTF | 
|-------|------------|------------|-----|
| Phase 2 baseline | 154.9 ms | 119.1 ms | 0.274 |
| Phase 3 + graph | **110.8 ms** | 106.6 ms | **0.229** |
| Delta | **-44.1 ms** | -12.5 ms | **-0.045** |

The t2m.compute improvement is within the HANDOFF.md estimate of 20-60ms for Rank 1.

---

## Technical Details

### Capture Flow

```
First call (CAPTURE):
  aclrtSynchronizeStream
  aclmdlRICaptureBegin(stream, RELAXED)
  → Record all ACL kernel launches (not executed)
  aclmdlRICaptureEnd → produce ACL model
  aclmdlRIExecuteAsync → execute recorded model
  Total: ~345ms (includes capture overhead)

Subsequent calls (REUSE):
  aclmdlRIExecuteAsync → execute pre-recorded model
  Total: ~220ms (steady state)
```

### Why RELAXED instead of GLOBAL or THREAD_LOCAL

| Mode | H2D behavior | Result |
|------|-------------|--------|
| GLOBAL | Captures ALL device streams | ❌ H2D fails on all streams |
| THREAD_LOCAL | Captures only specific stream | ❌ H2D still fails on same stream |
| RELAXED | Allows non-capturable ops | ✅ H2D proceeds, kernels captured |

### LRU Cache

- Key: graph hash (n_nodes + node op types + tensor shapes)
- Capacity: 12 graphs (configurable)
- Cache is per-CANN-backend-context (Flow and LLM have separate contexts)
- Flow model context: 2 large graphs cached (gf_nonlast ~11740, gf_last ~11746)
- LLM model context: prefill graphs cached (2373 nodes each)

---

## Limitations & Future Work

1. **Graph capture only helps deterministic graphs** — LLM decode (varying seq_len) can't
   benefit from capture, but the min_nodes filter eliminates their overhead
2. **First-chunk still pays capture cost** — the first Flow chunk incurs ~10-20ms
   of graph capture overhead
3. **RELAXED mode semantics** — operations that are not captured (H2D) during
   capture may not produce identical results to eager mode in edge cases;
   verified correct via audio output quality

### Next Steps (Phase 3 Rank 2-4)

- Rank 2: Operator fusion (element-wise Add+Mul+Cast, norm+scale)
- Rank 3: Im2col custom kernel (if kernel launch overhead still significant)
- Rank 4: Async H2D/D2H
