# CANN BACKEND ENV SEMANTICS

**Date**: 2026-07-29
**Status**: AUDITED

---

## 1. `OMNI_VOC_DEVICE=gpu` Semantics

### 1.1 Source Code Mapping

In `token2wav-impl.cpp`, the `gpu` string maps through:

```cpp
// token2wav-impl.cpp:2273-2290
ggml_backend_t fm_loader_init_backend_gpu_idx(int gpu_idx, ...) {
    ggml_backend_t backend = nullptr;
#ifdef GGML_USE_CUDA
    backend = ggml_backend_cuda_init(gpu_idx);    // Try CUDA first
#endif
#ifdef GGML_USE_CANN
    if (!backend) {
        backend = ggml_backend_cann_init(gpu_idx); // Then CANN
    }
#endif
    if (!backend) {
        backend = ggml_backend_init_by_type(GGML_BACKEND_DEVICE_TYPE_GPU, nullptr); // Generic
    }
    // ... fallbacks to iGPU, then CPU
}
```

### 1.2 Build-Time Resolution

- Build: `-DGGML_CANN=ON` enables `GGML_USE_CANN`
- CUDA is NOT compiled in this binary
- Therefore: `gpu` → CANN, `cpu` → CPU

### 1.3 Runtime Confirmation

```
flowGGUFModelLoader: init_backend device=gpu, gpu_idx=0, backend=CANN0
voc_hg2_model: init_backend device=gpu, gpu_idx=0, backend=CANN0
```

### 1.4 Correct Statement for Documentation

> `OMNI_VOC_DEVICE=gpu` in this build (GGML_CANN=ON, no CUDA) maps to
> `ggml_backend_cann_init(0)`, creating an Ascend NPU backend.
> The string `gpu` is a ggml accelerator abstraction, not NVIDIA-specific.

### 1.5 Alternative Explicit Naming

The code also supports `cann` as a device string prefix (from omni.cpp P3 fixes):
```cpp
device.find("gpu") == 0 || device.find("cann") == 0
```
So `OMNI_VOC_DEVICE=cann` would also work and is more explicit.

---

## 2. `OMNI_T2W_DEVICE=cann-flow-only` Semantics

### 2.1 Code Path

In `omni.cpp:4970-4981`:

```cpp
#ifdef GGML_USE_CANN
const char * t2w_dev_env = getenv("OMNI_T2W_DEVICE");
std::string device_token2mel = "cpu";    // DEFAULT: CPU
if (t2w_dev_env && std::string(t2w_dev_env) == "cann-flow-only") {
    device_token2mel = "gpu";             // Override to CANN
    ctx_omni->token2wav_defer_worker_init = true;  // KEY FLAG
    print_with_timestamp("Token2Wav: CANN flow-only mode — deferring init to worker thread\n");
} else {
    print_with_timestamp("Token2Wav: CANN流跨线程需算子适配，flow_matching暂用CPU\n");
}
```

### 2.2 What `defer_worker_init` Does

Without it: main thread creates CANN backend → passes to T2W worker thread →
worker gets `ctx=NULL` / `device=-1` (CANN requires thread-local device ownership).

With it: worker thread calls `flowGGUFModelLoader::load_from_gguf()` with `device="gpu"`,
creating a dedicated CANN backend on the worker thread. This avoids the cross-thread
context invalidation.

### 2.3 Default Behavior (NO env var set)

- `OMNI_T2W_DEVICE` unset → `device_token2mel = "cpu"`
- Flow model runs entirely on CPU
- Message: "flow_matching暂用CPU"
- This was the state in ALL experiments before P15

### 2.4 Why "cann-flow-only" Name

- `cann-`: Indicates CANN-specific path
- `flow-only`: Only affects Flow model (not vocoder)
- Vocoder is controlled separately by `OMNI_VOC_DEVICE`

---

## 3. Complete Configuration Matrix

| OMNI_T2W_DEVICE | OMNI_VOC_DEVICE | Flow Backend | Vocoder Backend | RTF |
|-----------------|-----------------|--------------|-----------------|-----|
| (unset) | (unset) | CPU | CPU | ~4.21 |
| (unset) | gpu | CPU | CANN | ~3.92 |
| cann-flow-only | (unset) | CANN | CPU | ~1.86 |
| cann-flow-only | gpu | CANN | CANN | **~0.27** |

---

## 4. Future Improvements

1. **Renaming**: `OMNI_VOC_DEVICE=cann` is already supported and more explicit.
   `OMNI_T2W_DEVICE=cann-flow-only` should become `OMNI_T2W_DEVICE=cann` once
   cross-thread issue is fully resolved (worker-thread init becomes the default).

2. **Default change**: Once worker-thread deferred init is validated as stable,
   `cann-flow-only` behavior should become the DEFAULT for CANN builds.
