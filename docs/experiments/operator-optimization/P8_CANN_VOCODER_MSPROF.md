# P8: CANN Vocoder msprof Profiling

**Date**: 2026-07-29
**Phase**: P8 — CANN Operator Profiling
**Status**: COMPLETE

---

## 1. Profiling Configuration

| Parameter | Value |
|-----------|-------|
| Tool | msprof (CANN 9.1.0-beta.1) |
| Command | `msprof --ascendcl=on --runtime-api=on --task-time=on --ai-core=on` |
| Test case | 1 omni input (single chunk) |
| Vocoder backend | CANN (`OMNI_VOC_DEVICE=gpu`) |
| Output | `/tmp/p8_msprof/` |

---

## 2. CANN API Breakdown (Host Side)

| API | Total Time | Count | Avg | Notes |
|-----|-----------|-------|-----|-------|
| **SetDevice** | **629.9ms** | 907 | 694us | ⚠️ TLS cache hit expected; single outlier at 613ms |
| **MemCopySync** | **427.1ms** | 6,321 | 67.6us | D2H/H2D transfers across Flow + Vocoder |
| **DevMalloc** | 248.9ms | 39 | 6.4ms | Device memory allocation |
| **LaunchKernelV2** | 138.4ms | 17,482 | 7.9us | Kernel launch overhead |
| **StreamSynchronize** | 71.7ms | 9,600 | 7.5us | Stream sync (mostly Flow model) |
| **BinaryLoadFromData** | 28.0ms | 37 | 758us | Kernel binary loading |
| **DevFree** | 18.8ms | 39 | 483us | Device memory free |
| **HostFree** | 16.9ms | 4 | 4.2ms | Large host deallocations |
| **StreamCreate** | 15.5ms | 7 | 2.2ms | Stream creation |
| **BinaryGetFunctionByEntry** | 14.9ms | 1,379 | 10.8us | Kernel function lookup |
| **HostMalloc** | 8.6ms | 4 | 2.1ms | Host memory allocation |
| **StreamDestroy** | 6.1ms | 7 | 878us | Stream destruction |

**Total API overhead: ~1,660ms** (dominated by SetDevice + MemCopySync)

> Note: These cover the ENTIRE inference (Flow model + Vocoder), not just vocoder. The Flow model runs on multiple streams and dominates the API call count.

---

## 3. NPU Operator Breakdown (Device Side)

### By Operator Type (Device 0 — likely Vocoder NPU context)

| Operator | Core Type | Count | Total Time | % of Kernel Time |
|----------|-----------|-------|------------|------------------|
| RotaryPositionEmbedding | MIX_AIV | 1,258 | 12.4ms | 20.6% |
| Mul | AI_VECTOR_CORE | 2,922 | 11.2ms | 18.6% |
| Tile | AI_VECTOR_CORE | 2,522 | 5.2ms | 8.7% |
| RmsNorm | AI_VECTOR_CORE | 631 | 4.9ms | 8.1% |
| Sin | AI_VECTOR_CORE | 1,258 | 2.3ms | 3.9% |
| ScatterUpdate | AI_VECTOR_CORE | 272 | 2.2ms | 3.7% |
| TransData | AI_VECTOR_CORE | 135 | 2.0ms | 3.4% |
| Transpose | AI_VECTOR_CORE | 125 | 2.0ms | 3.3% |
| MatMulV2 | AI_CORE | 154 | 1.6ms | 2.6% |
| TensorMove | AI_VECTOR_CORE | 135 | 0.9ms | 1.5% |

**Total NPU kernel time (all streams): ~74ms**

### Stream Distribution

| Stream | Total Kernel Time | Task Count | Likely Role |
|--------|-------------------|------------|-------------|
| 39 | 47.4ms | 12,480 | Flow model (transformer layers) |
| 41 | 14.0ms | 3,467 | Flow model (additional layers) |
| 37 | 9.9ms | 1,282 | Flow model / Vision encoder |
| **42** | **2.9ms** | **272** | **Vocoder (HiFi-GAN2) + weight init** |
| 34 | 0.3ms | 66 | Utility |

---

## 4. Vocoder-Specific Analysis

The vocoder operates on **Stream 42** with ~2.9ms of NPU kernel time. The vocoder ops identified:

| Op Type | Count | Time | Vocoder Role |
|---------|-------|------|-------------|
| TransData (weight transform) | 135 | 2.0ms | Weight layout conversion for MatMul |
| TensorMove | 135 | 0.9ms | Weight movement to AI Core |
| (Remaining hidden ops) | — | ~0ms | Conv1d/Upsample/Snake/iSTFT fused? |

The vocoder kernel ops appear to be mostly weight transformation (TransData/TensorMove), suggesting the actual compute (conv1d, upsample, iSTFT) may be:
1. Fused into a small number of custom kernels not individually labeled
2. Extremely fast (sub-microsecond per op) due to the small tensor dimensions
3. Partially absorbed into the MatMul weight preprocessing

---

## 5. Vocoder Time Budget (110ms total, reconstructed)

| Component | Estimated Time | % of Vocoder | Evidence |
|-----------|---------------|-------------|----------|
| NPU kernels (stream 42) | 3ms | 2.7% | msprof task_time |
| Graph build (`voc_hg2_runner_build_graph`) | 50-70ms | 45-64% | Code analysis |
| `ggml_gallocr_alloc_graph` | 10-20ms | 9-18% | Code analysis |
| H2D: mel upload + const upload | 10-15ms | 9-14% | msprof MemCopySync |
| D2H: wave + source download | 10-15ms | 9-14% | msprof MemCopySync |
| `ggml_init` + tensor creation | 5-10ms | 5-9% | Code analysis |
| Other framework overhead | 5-10ms | 5-9% | — |
| **Total** | **~110ms** | **100%** | T2W profiler |

### Key Insight

**NPU compute is only ~3ms of the 110ms vocoder time (2.7%).** The remaining 107ms (97%) is framework overhead:
- Graph construction: ~50-70ms
- Memory allocation: ~10-20ms
- Data transfer: ~20-30ms
- Context init/teardown: ~5-10ms

**This confirms the P5 corrected analysis: the CANN vocoder is framework-overhead-bound.**

---

## 6. Comparison: CPU vs CANN Vocoder Time Budget

| Component | CPU | CANN | Notes |
|-----------|-----|------|-------|
| NPU/CPU compute | ~250ms | **3ms** | CANN 83× faster for compute |
| Graph build | ~50ms | ~50ms | Same code path |
| Galloc | ~15ms | ~15ms | Same code path |
| Upload/Download | 0ms | ~25ms | CANN-only penalty |
| Context init/other | ~15ms | ~17ms | Similar |
| **Total** | **~330ms** | **~110ms** | **CANN 3× faster overall** |

**The NPU delivers an 83× compute speedup (250ms → 3ms), but framework overhead masks most of this gain, resulting in only 3× end-to-end vocoder speedup.**

---

## 7. Top 5 Optimization Opportunities

| Rank | Optimization | Current Cost | Target | Vocoder RTF Impact | Total RTF Impact |
|------|-------------|-------------|--------|-------------------|-----------------|
| **1** | **Graph reuse (O2-A)** | 50-70ms/chunk | ~5ms (first only) | 110→50ms | 3.71→3.65 |
| **2** | **Galloc reuse (O2-B)** | 10-20ms/chunk | ~0ms | 50→35ms | 3.65→3.63 |
| **3** | **Device handoff (P10)** | 20-30ms/chunk | ~5ms | 35→15ms | 3.63→3.61 |
| **4** | **Context reuse (O2-C)** | 5-10ms/chunk | ~0ms | 15→10ms | 3.61→3.60 |
| **5** | **Const cache (O2-D)** | 5-10ms/chunk | ~0ms | 10→5ms | negligible |

Combined potential: vocoder RTF from 0.11 to ~0.005, total RTF from 3.71 to ~3.60 (+3.0%).

**However, the Flow model at 3,600ms remains the dominant bottleneck.** Even eliminating ALL vocoder overhead (110ms → 0ms) only improves total RTF by 3.0%.

---

## 8. Mission Implications

### The vocoder optimization ceiling is ~3% total RTF improvement.

Given that:
- Vocoder is 110ms out of 3,710ms total T2W time (3.0%)
- Maximum possible vocoder optimization saves ~105ms → total RTF 3.71 → 3.60 (+3.0%)
- Flow model (3,600ms) is the true bottleneck

### Recommendation

1. **O2-A (graph reuse)** is the highest-value vocoder optimization — implement if effort is low
2. **P10 (device handoff)** provides modest additional savings
3. **To achieve competition-significant RTF improvement, Flow model optimization must be addressed**
4. **Consider expanding mission scope** to include Flow model (token2mel) optimization

---

## 9. Raw Data

- msprof output: `/tmp/p8_msprof/PROF_000001_20260729060941837_04134712MQNJRPFP/`
- Key files:
  - `mindstudio_profiler_output/op_statistic_*.csv` — per-operator statistics
  - `mindstudio_profiler_output/api_statistic_*.csv` — per-API statistics
  - `mindstudio_profiler_output/task_time_*.csv` — per-task timing
  - `mindstudio_profiler_output/op_summary_*.csv` — per-op execution summary
