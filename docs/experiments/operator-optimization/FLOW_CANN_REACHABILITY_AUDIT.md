# FLOW CANN REACHABILITY AUDIT

**Date**: 2026-07-29
**Status**: AUDITED — Path confirmed, fallback=0

---

## 1. The "Flow=CANN" Discrepancy

### 1.1 What Previous Documents Claimed

Earlier phases (P5, P7, P13-P14) described the Flow model as "using CANN backend":

> P13 Architecture Audit: "Flow model uses the SAME ggml CANN backend as the vocoder"
> P14 Canonical Baseline: "Flow backend: CANN (auto-selected when GGML_USE_CANN compiled)"

### 1.2 What Actually Happened

The binary WAS compiled with `GGML_USE_CANN`, and the ggml-cann backend WAS available.
But `omni-cli` (via `omni.cpp`) explicitly overrides `device_token2mel = "cpu"`:

```cpp
// omni.cpp:4971
std::string device_token2mel = "cpu";   // DEFAULT under CANN build!
```

This happens because CANN runtime requires thread-local device ownership.
The main thread creates a CANN context, but the T2W worker thread can't use it.

### 1.3 Why `OMNI_T2W_DEVICE=cann-flow-only` Fixes It

The `cann-flow-only` mode:
1. Sets `device_token2mel = "gpu"` (→ CANN)
2. Sets `token2wav_defer_worker_init = true`
3. The worker thread calls `flowGGUFModelLoader::load_from_gguf(device="gpu")` on ITS OWN thread
4. Worker thread gets its own CANN backend instance → no cross-thread issue

### 1.4 Confirmation

Before P15 (no env var):
```
Token2Wav: CANN流跨线程需算子适配，flow_matching暂用CPU
Token2Wav: CANN流跨线程需算子适配，vocoder暂用CPU
```

After P15 (`OMNI_T2W_DEVICE=cann-flow-only OMNI_VOC_DEVICE=gpu`):
```
flowGGUFModelLoader: init_backend device=gpu, gpu_idx=0, backend=CANN0
voc_hg2_model: init_backend device=gpu, gpu_idx=0, backend=CANN0
```

**Timing confirms CANN path:**
- CPU Flow: 3,725.8ms mean (n=36 steady)
- CANN Flow: 154.9ms mean (n=65 steady)
- 24× difference confirms genuine backend switch

---

## 2. Path Hit Audit

### 2.1 Path Routing Verification

The existing path hit counters (`OMNI_VOC_PATH_STATS=1`) track vocoder routing only.
Flow model routing does NOT have dedicated path counters in the current code.

### 2.2 Indirect Path Verification

| Evidence | CPU Flow | CANN Flow |
|----------|----------|-----------|
| Init message | "flow_matching暂用CPU" | "init_backend device=gpu...backend=CANN0" |
| t2m.compute mean | 3,725.8ms | 154.9ms |
| t2m.compute p50 | 3,644.9ms | 155.3ms |
| t2m.upload mean | 2.0ms | 3.5ms |
| t2m.download mean | 0.01ms | 0.11ms |
| t2m.feed_noise mean | 0.2ms | 0.5ms |

The upload/download overhead increase (2.0→3.5ms for upload) is consistent with
H2D transfers through CANN runtime, confirming the CANN path is active.

### 2.3 Fallback Verification

- No "CANN error" messages in any P15/P15-A/P15-B log
- No compute failures (all t2m.compute values are valid)
- No download failures
- Audio output generated correctly (60/60 wavs valid)
- **fallback_count = 0** (based on absence of error messages + valid timing)

---

## 3. Why This Was Missed

1. **"gpu" frontend abstraction**: The code uses `device="gpu"` which in a CANN-only
   build maps to CANN. Reading `device_token2mel = "gpu"` in the default code path
   looked like CANN was enabled.

2. **But omni.cpp overrides**: The CLI layer (`omni.cpp:4971`) sets `device_token2mel = "cpu"`
   regardless of the lower-level capability. The lower-level code CAN use CANN,
   but the CLI overrides it to CPU.

3. **Warning was present but overlooked**: Every run printed "flow_matching暂用CPU"
   but this was treated as informational, not as a routing issue.

4. **No path hit counters for Flow**: Unlike the vocoder (which has `g_vocoder_cann_dispatch_count`
   etc.), the Flow model has no path routing counters. The CANN/CPU routing is opaque.

---

## 4. Current Path State

| Component | Env Var | Path | Verified |
|-----------|---------|------|----------|
| Flow model | OMNI_T2W_DEVICE=cann-flow-only | CANN (worker-thread) | ✅ timing + init log |
| Vocoder | OMNI_VOC_DEVICE=gpu | CANN | ✅ path counters + timing |
| Fallback (Flow) | — | 0 | ✅ no errors |
| Fallback (Vocoder) | — | 0 | ✅ path counters |

---

## 5. Recommended Code Improvements

1. **Add Flow path hit counters** (analogous to vocoder):
   ```cpp
   static int g_flow_cpu_dispatch_count = 0;
   static int g_flow_cann_dispatch_count = 0;
   static int g_flow_cann_success_count = 0;
   static int g_flow_cann_failure_count = 0;
   static int g_flow_cpu_fallback_count = 0;
   ```

2. **Print Flow backend at init** (already partially done — `init_backend` message appears
   when CANN path is used. Add a similar message for CPU path.)

3. **Make `cann-flow-only` the default** once cross-thread worker init is validated stable.
   The current default (CPU) is a pessimization that cost 24× performance.

4. **Rename `cann-flow-only` to `cann`** for consistency with `OMNI_VOC_DEVICE=cann`.
