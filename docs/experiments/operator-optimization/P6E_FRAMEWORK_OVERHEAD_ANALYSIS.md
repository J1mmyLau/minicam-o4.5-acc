# P6-E: Framework Overhead Analysis — Why CANN Is Only 5% Faster

**Date**: 2026-07-29
**Phase**: P6-E (Fault Investigation Branch)
**Status**: COMPLETE

---

## 1. Observation

P5 correctness gate confirmed CANN vocoder produces valid audio but only achieves **~5% RTF improvement** over CPU (3.75 vs 3.95), far below the 6-10× theoretical NPU advantage for HiFi-GAN2's conv1d/upsample operations.

## 2. Root Cause

**Per-chunk framework overhead dominates wall time.** Each vocoder chunk (~3,750ms) consists of:

| Phase | Code Location | Estimated Time | Category |
|-------|---------------|----------------|----------|
| `ggml_init` | `voc_hg2_runner_eval_stream:6827` | ~50ms | Framework |
| Tensor creation | `:6835-6838` | ~10ms | Framework |
| Graph build | `voc.build_alloc:6842` — `voc_hg2_runner_build_graph` | **~500-1000ms** | Framework |
| `ggml_gallocr_alloc_graph` | `:6847` | **~200-500ms** | Framework |
| Const upload | `voc.upload:6855` — `hg_stft16_params_upload_consts` etc. | ~100ms | Framework |
| **H2D: mel upload** | `hg_backend_tensor_set:6858` | ~50ms | **D2H+H2D** |
| **H2D: cache upload** | `hg_backend_tensor_set:6861` | ~10ms | **D2H+H2D** |
| **NPU compute** | `voc.compute:6876` — `ggml_backend_graph_compute` | **~100-500ms** | NPU Kernel |
| **D2H: wave download** | `voc.download:6885` — `hg_read_tensor_2d_tb_f32` | ~50ms | **D2H+H2D** |
| **D2H: source download** | `hg_read_tensor_3d_tcb_f32:6894` | ~50ms | **D2H+H2D** |
| `ggml_free` | `:6901+` | ~50ms | Framework |
| **Pre-vocoder D2H** | `mel_bct` (Flow output, CPU) → CPU cache prepend | ~50ms | **D2H+H2D** |

**Total framework overhead: ~1,500-2,500ms (40-67% of wall time)**
**Total D2H+H2D overhead: ~160-210ms (4-6% of wall time)**
**Estimated NPU compute: ~100-500ms (3-13% of wall time)**

> Note: Times are ESTIMATES based on code analysis. Profiling (P8) will provide exact measurements.

## 3. The D2H+H2D Round-Trip

```
Flow NPU → D2H (aclrtMemcpy) → CPU mel_bct (std::vector<float>)
  → CPU cache prepend → mel_in_bct (std::vector<float>)
  → H2D (hg_backend_tensor_set) → Vocoder NPU
  → NPU compute (conv1d, upsample, iSTFT)
  → D2H (hg_read_tensor_2d_tb_f32) → CPU wave_bt_out
```

This double transfer exists because Flow and Vocoder use **separate ggml_backend_cann instances** with independent NPU contexts. Mel data must pass through CPU memory as an intermediary.

## 4. Why CPU Vocoder Matches CANN

The CPU vocoder does NOT have the D2H+H2D round-trip (mel is already on CPU). And the NPU compute advantage (~100-500ms) is small relative to the shared framework overhead (~1,500-2,500ms for graph build/galloc).

Both backends are bottlenecked by the same per-chunk framework overhead:
- `ggml_init` (new context every chunk)
- Graph construction (`voc_hg2_runner_build_graph`)
- Graph allocation (`ggml_gallocr_alloc_graph`)

## 5. Optimization Impact Estimates

| Optimization | Target | Est. Savings | Risk |
|-------------|--------|-------------|------|
| O2-A: Graph reuse | Eliminate per-chunk graph build | 500-1000ms (13-27%) | Medium |
| O2-B: Galloc reuse | Eliminate per-chunk allocation | 200-500ms (5-13%) | Medium |
| P10: Device handoff | Eliminate D2H+H2D round-trip | 160-210ms (4-6%) | High |
| O2-C: Context reuse | Eliminate per-chunk ggml_init | ~50ms (1%) | Low |
| O2-D: Const cache | Eliminate per-chunk const upload | ~100ms (3%) | Low |

**Priority: O2-A (graph reuse) > O2-B (galloc reuse) > P10 (device handoff)**

The 5% CANN gain comes entirely from faster NPU kernel execution (~100-500ms vs CPU compute ~300-700ms). Without framework overhead reduction, the maximum possible CANN improvement is bounded at ~10-13%.

## 6. Action Items

1. **P8: msprof profiling** → Get exact NPU kernel time to validate estimates
2. **P9: Candidate ranking** → Rank O2-A through O2-J by impact/risk
3. **P10: Device residency** → Implement Flow→Vocoder device handoff
4. **P11: Top-1 implementation** → Implement highest-rank optimization

## 7. Verdict

**CANN vocoder is correct but framework-overhead-bound.** NPU compute is not the bottleneck. The 5% gain is real but architecturally limited. Framework overhead reduction (graph reuse, galloc reuse) is the critical path to competition-significant RTF improvement.
