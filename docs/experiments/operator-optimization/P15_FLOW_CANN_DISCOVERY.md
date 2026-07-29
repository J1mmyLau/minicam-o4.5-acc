# P15: Flow Model CANN Discovery — 21.9× Speedup

**Date**: 2026-07-29
**Phase**: P15 — Flow Profiling / CANN Discovery
**Status**: COMPLETE (Discovery)

---

## 1. Critical Discovery

The Flow model (token2mel) was running on **CPU**, not CANN, in all previous experiments.
Despite the binary being compiled with `GGML_USE_CANN`, the omni-cli initialization explicitly
defaults `device_token2mel = "cpu"` under CANN due to a cross-thread CANN stream issue.

However, a special mode `OMNI_T2W_DEVICE=cann-flow-only` defers Flow session init to the
worker thread, creating a dedicated CANN backend that avoids the cross-thread conflict.

**Enabling this mode yields a 21.9× Flow model speedup.**

---

## 2. Root Cause Analysis

### 2.1 The Cross-Thread CANN Stream Problem

From `omni.cpp:4970-4981`:

```cpp
#ifdef GGML_USE_CANN
const char * t2w_dev_env = getenv("OMNI_T2W_DEVICE");
std::string device_token2mel = "cpu";
if (t2w_dev_env && std::string(t2w_dev_env) == "cann-flow-only") {
    // Worker-thread CANN backend: defer session init to t2w_thread_func_cpp.
    // The worker will create its own CANN backend, avoiding the cross-thread
    // ctx=NULL / device=-1 failure (ROOT_CAUSE_CONFIRMED_THREAD_OWNERSHIP).
    device_token2mel = "gpu";  // Will be used inside worker
    ctx_omni->token2wav_defer_worker_init = true;
    print_with_timestamp("Token2Wav: CANN flow-only mode — deferring init to worker thread\n");
} else {
    print_with_timestamp("Token2Wav: CANN流跨线程需算子适配，flow_matching暂用CPU\n");
}
```

**Cause**: CANN runtime requires exclusive thread ownership of device contexts. When the
main thread initializes the CANN backend and then passes it to the T2W worker thread,
the worker gets `ctx=NULL` / `device=-1` errors. The `cann-flow-only` mode solves this
by deferring ALL CANN init to the worker thread.

### 2.2 Why This Was Missed

- The binary prints "flow_matching暂用CPU" (flow_matching temporarily using CPU) — a warning that was overlooked
- The vocoder had `OMNI_VOC_DEVICE=gpu` for explicit CANN routing, but Flow had no equivalent env var exposed
- The Flow model still completed inference (just on CPU), so no error signaled the issue

---

## 3. Results

### 3.1 Single Test Case (60 chunks, CANN Flow + CANN Vocoder)

| Stage | p50 (ms) | Mean (ms) | p95 (ms) | CV |
|-------|----------|-----------|----------|-----|
| t2m.compute | **166.3** | **165.6** | 244.2 | 0.227 |
| voc.compute | 119.8 | 121.5 | 124.2 | 0.031 |
| **Total** | **289.6** | **294.0** | 376.0 | — |

### 3.2 Steady-State (calls ≥ 4, n=56)

| Metric | t2m.compute | voc.compute | Total |
|--------|-------------|-------------|-------|
| Mean | 170ms | 123ms | 293ms |
| p50 | 169ms | 123ms | 290ms |
| p95 | 251ms | 135ms | 386ms |
| CV | 0.227 | 0.051 | 0.125 |
| **RTF** | **0.170** | **0.123** | **0.293** |

### 3.3 Speedup vs CPU Flow Baseline

| Component | CPU Flow | CANN Flow | Speedup |
|-----------|----------|-----------|---------|
| **t2m.compute** | 3,723ms | 170ms | **21.9×** |
| voc.compute | 323ms | 123ms | 2.6× |
| **Total T2W** | 4,045ms | 293ms | **13.8×** |
| **Total RTF** | 4.05 | 0.29 | — |

### 3.4 Competition Metric Impact

```
PER-CHUNK RTF (competition metric):

Before (CPU Flow + CANN Vocoder):
  RTF = (3,723 + 117) / 1000 = 3.84  ← NOT realtime

After (CANN Flow + CANN Vocoder):
  RTF = (170 + 123) / 1000 = 0.29   ← WELL BELOW REALTIME!
```

**The system now achieves RTF < 1.0 — faster than realtime — on Ascend 910C.**

---

## 4. New Bottleneck Picture

### 4.1 Before (CPU Flow)

```
T2W per chunk: 4,045ms
├── Flow (t2m.compute, CPU): 3,723ms (92.0%) ← DOMINANT
└── Vocoder (CPU):             323ms (8.0%)
```

### 4.2 After (CANN Flow + CANN Vocoder)

```
T2W per chunk: 293ms
├── Flow (t2m.compute, CANN): 170ms (58.0%)
└── Vocoder (CANN):            123ms (42.0%)
```

### 4.3 New Optimization Surface

| Target | Time | % Total | Headroom |
|--------|------|---------|----------|
| Flow t2m.compute (CANN) | 170ms | 58% | CV=0.227 suggests scheduling jitter |
| Vocoder (CANN) | 123ms | 42% | 75ms kernel launch (P8 finding) |
| **Total** | **293ms** | **100%** | **RTF=0.29** |

The bottleneck is now **balanced** between Flow and Vocoder. Both are on CANN.
Further optimization should target both components.

---

## 5. Observations and Concerns

### 5.1 High Flow Variability (CV=0.227)

- CPU Flow CV was 0.047 — CANN Flow CV is 4.8× higher
- p95/p50 ratio: 1.51× (vs 1.13× on CPU) — significant tail latency
- Possible causes:
  - CANN graph JIT compilation on some chunks
  - Memory allocator jitter (galloc)
  - Cross-thread synchronization artifacts
  - Kernel scheduling variability

### 5.2 First Chunk

- First chunk: 378ms total (178ms Flow + 199ms Vocoder)
- Includes CANN graph JIT + first-time memory allocation
- Steady-state reached by ~call 4

### 5.3 t2m.upload Increased

| Stage | CPU Flow | CANN Flow | Delta |
|-------|----------|-----------|-------|
| t2m.upload | 2.0ms | 3.5ms | +1.5ms |
| t2m.feed_noise | 0.2ms | 0.5ms | +0.3ms |
| t2m.download | 0.01ms | 0.1ms | +0.09ms |

CANN upload/download overhead is slightly higher but still negligible (~4ms vs 170ms compute).

---

## 6. CANN Backend Verification

```
flowGGUFModelLoader: init_backend device=gpu, gpu_idx=0, backend=CANN0
voc_hg2_model: init_backend device=gpu, gpu_idx=0, backend=CANN0
```

Both Flow and Vocoder use CANN0 backend. The vocoder backend is separate from Flow's
(worker-thread init creates a dedicated CANN context for Flow).

### NPU Operators Captured (LLM/Vision only in CPU Flow msprof)

Since the first msprof run captured CPU Flow, the NPU operators were from LLM decode:
- RmsNorm: 43ms (18.7%) — AI_VECTOR_CORE
- Mul: 31ms (13.1%) — AI_VECTOR_CORE
- FusedInferAttentionScore: 29ms (12.4%) — MIX_AIC
- RotaryPositionEmbedding: 26ms (11.2%) — MIX_AIV

These are NOT Flow model ops. Re-profiling with CANN Flow is needed to identify Flow's
CANN kernel breakdown.

---

## 7. Required Next Steps

### P15-A: Correctness Verification (CRITICAL)

The CANN Flow path must be verified for audio output correctness:
- Compare CANN Flow output wav with CPU Flow output wav
- Check for audio artifacts, silence, or distortion
- Verify mel spectrogram similarity (MCD, SNR)

### P15-B: Stability Multi-Batch

Run 5+ batches with CANN Flow to verify:
- Zero CANN failures
- Consistent RTF across batches
- No memory leaks or HBM accumulation

### P15-C: CANN Flow msprof

Re-run msprof with `OMNI_T2W_DEVICE=cann-flow-only` to capture Flow model CANN kernels.
This will identify:
- Top CANN operators in Flow model
- Kernel launch overhead
- Fusion opportunities

### P15-D: High CV Investigation

Investigate root cause of CV=0.227:
- Is it JIT compilation on some chunks?
- Is it memory allocator variability?
- Is it scheduling artifacts?

---

## 8. Configuration Protocol

```bash
# Enable CANN for both Flow and Vocoder
export OMNI_T2W_DEVICE=cann-flow-only   # Flow model on CANN (worker-thread deferred init)
export OMNI_VOC_DEVICE=gpu              # Vocoder on CANN
export OMNI_T2W_PROFILE=2               # Per-chunk timing

# Run inference
./build/bin/llama-omni-cli -m <model.gguf> --omni --test <prefix> <count>
```

**This configuration achieves RTF=0.29 (13.8× vs CPU Flow baseline).**
