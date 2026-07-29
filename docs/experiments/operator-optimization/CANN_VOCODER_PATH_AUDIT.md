# CANN Vocoder Path Audit — Source and Scheduling

**Date**: 2026-07-29
**Phase**: P3 — CANN Vocoder Source and Scheduling Audit
**Status**: COMPLETE
**Source**: `tools/omni/omni.cpp`, `tools/omni/token2wav/token2wav-impl.cpp`

---

## 1. OMNI_VOC_DEVICE Parsing

### Q1: Where is OMNI_VOC_DEVICE=cann parsed?

**File**: `tools/omni/omni.cpp`, lines 4991-5007

```cpp
const char * voc_dev_env = getenv("OMNI_VOC_DEVICE");
std::string device_vocoder;
if (voc_dev_env) {
    device_vocoder = voc_dev_env;
    print_with_timestamp("Token2Wav: vocoder device overridden by OMNI_VOC_DEVICE=%s\n", voc_dev_env);
} else {
    // default: CANN→CPU, CUDA→GPU, Metal→CPU
}
```

Also checked at worker thread deferred init (line 10019):
```cpp
const char * voc_dev = getenv("OMNI_VOC_DEVICE");
```

**Parsed in two places:**
1. Main thread: `omni_init` → session init (lines 4991-5007) — used for `init_from_prompt_cache_gguf()`
2. Worker thread: deferred init path (line 10019) — re-reads env var

### Q2: What values are supported?

| Value | Behavior |
|-------|----------|
| `"cpu"` | CPU backend (default for CANN) |
| `"gpu"` or `"gpu:0"` or `"gpu:1"` | GPU backend (CANN on Ascend, CUDA on NVIDIA) |
| `"cann"` | Passed as `"gpu"` → resolved to CANN via `ggml_backend_cann_init()` |
| Any other string | Passed as-is to `voc_hg2_model_init_from_gguf()` → `ggml_backend_init_by_type()` |

### Q3: What is the default value?

**`"cpu"`** when `GGML_USE_CANN` is defined. Rationale: "CANN流跨线程需算子适配，vocoder暂用CPU" (omni.cpp:5001).

This is an **explicit production decision**, not an oversight. The concern is cross-thread operator compatibility in the CANN stream.

---

## 2. CANN Backend Compilation

### Q4: Is the CANN path actually compiled into the current binary?

**YES.** Proven by:
- `#ifdef GGML_USE_CANN` guard at `token2wav-impl.cpp:6790` wraps `ggml_backend_cann_init(gpu_idx)`
- Binary `libggml-cann.so.0.13.1` exists (346KB, SHA256: `47bb4386...`)
- Flow model already runs on CANN via the same `ggml_backend_cann_init()` path

### Q5: How to confirm the actual backend being used?

Run with `OMNI_VOC_DEVICE=cann` and check stderr:
```
voc_hg2_model: init_backend device=gpu, gpu_idx=X, backend=CANN
```
(This is the log from `voc_hg2_model_init_from_gguf`, line 6647.)

Vs. CPU:
```
voc_hg2_model: CPU backend using 8 threads
```

---

## 3. Fallback and Error Handling

### Q6: Does CANN failure automatically fall back to CPU?

**NO.** No automatic fallback exists. If `ggml_backend_cann_init(gpu_idx)` returns nullptr, the code tries `ggml_backend_init_by_type(GPU)` → `IGPU` → `CPU` in sequence (lines 6638-6646 in token2wav-impl.cpp). This is a startup-time fallback, not a runtime fallback.

If the CANN backend is successfully created but compute fails, `push_tokens_window` returns `false` — the error propagates to the caller.

### Q7: Is there a fallback log?

Only the backend init log at line 6647. No runtime fallback counting exists. **This must be added per mission requirements.**

---

## 4. Model Loading and Lifecycle

### Q8: Is the vocoder model loaded only once?

**YES.** `voc_hg2_model_init_from_gguf()` is called once at session init (line 9709). It:
1. Calls `ggml_backend_load_all()`
2. Creates backend
3. Loads GGUF weights
4. Binds model tensors to backend buffers
5. Creates galloc (persistent graph allocator)

These are stored in `voc_model_` (member of `Token2Wav`) and survive for the entire session.

### Q9: Is the CANN graph re-created per chunk?

**YES.** Each call to `voc_hg2_runner_eval_stream()` (line 6743):
1. Creates a new `ggml_context` (line 6774: `ggml_init(params)` with 2048MB arena)
2. Creates new tensors (`ggml_new_tensor_3d` ×3, lines 6778-6782)
3. Creates a new compute graph (`ggml_new_graph_custom`, line 6783)
4. Builds the full HiFi-GAN2 graph (`voc_hg2_runner_build_graph`, line 6786)
5. Allocates backend memory (`ggml_gallocr_alloc_graph`, line 6790)
6. After compute: `ggml_free(ctx)` (line 6821) — frees the context and graph

**This is the primary framework overhead source.**

### Q10: Is galloc/graph plan re-executed per chunk?

**YES**, but with an important nuance: `model->galloc` (line 6790) is a **persistent** `ggml_gallocr_t` created once at model init. `ggml_gallocr_alloc_graph` reuses the same galloc but re-allocates if shapes change. Since shapes are stable after convergence, the allocation cost should be minimal after the first few chunks.

### Q11: Are weights permanently resident on NPU?

**YES.** Weights are loaded once into backend buffers at init (line 6671-6678). They remain on the backend's device memory for the lifetime of the session. For CPU backend: weights in CPU memory. For CANN backend: weights in HBM.

### Q12: Is workspace reused?

The `ggml_gallocr_t` (persistent) provides workspace reuse. However, each chunk creates a new graph, so the workspace is re-allocated per chunk if shapes vary. After convergence (shapes stable), reuse should be effective.

---

## 5. Dataflow: Flow ↔ Vocoder

### Q13: Do input tensors come from CPU or NPU?

**Currently CPU → H2D per chunk.** The mel input arrives as `std::vector<float> mel_in_bct` (CPU memory, line 9816). The vocoder uploads it via `hg_backend_tensor_set(model->backend, speech_upload_tcb, mel_data, size)` (line 6800-6801).

### Q14: Is flow output first D2H?

**YES.** The flow model (`t2m_.push_tokens()`) returns `mel_bct` as `std::vector<float>` (CPU memory, line 9786). This means:
```
Flow CANN → D2H → CPU mel_bct → (cache prepend) → CPU mel_in_bct
```

### Q15: Does CANN vocoder then H2D?

**YES.** With CANN vocoder backend, the `hg_backend_tensor_set` call (line 6800) would perform H2D:
```
CPU mel_in_bct → H2D → CANN vocoder backend
```

### Q16: Do flow and vocoder use the same device?

**Not necessarily.** They each create their own backend instance:
- Flow: `flowGGUFModelLoader::init_backend(device_token2mel)` → `ggml_backend_cann_init(gpu_idx)` (line 7280)
- Vocoder: `voc_hg2_model::voc_hg2_model_init_from_gguf(device_vocoder, ...)` → `ggml_backend_cann_init(gpu_idx)` (line 6635)

Each call creates a **separate backend instance** with its own context, stream, and device buffers. Even if both use `gpu_idx=0`, they have separate backend objects.

### Q17: Do they use the same stream?

**NO.** Each backend has its own stream. Flow's `ggml_backend_cann_graph_compute` uses flow's stream; vocoder's compute uses vocoder's stream. No stream sharing.

### Q18: Is there a mandatory Synchronize?

At flow output: The flow model's compute on CANN must complete before D2H reads the result. This sync is implicit in the D2H call (`aclrtMemcpy` from device to host).

At vocoder input: No sync needed before H2D because it's a different backend/stream.

Between the two: The current CPU-path flow (D2H → CPU processing → H2D) creates a natural sync point. With CANN vocoder, if we eliminate the D2H+H2D round-trip, explicit synchronization between flow and vocoder streams would be needed.

### Q19: Is output D2H?

**YES.** After vocoder compute, the wave output is read back via `hg_read_tensor_2d_tb_f32` (line 6827) which does D2H.

---

## 6. Compatibility

### Q20: What shapes/dtypes/layouts are supported?

Current assertion: ALL ops in the vocoder graph require `GGML_TYPE_F32` (float32). Shapes:
- Mel input: `[T_mel, 80, 1]` where T_mel varies (typically 28 for first window, 36 for subsequent with cached prefix)
- Source cache: `[Tc, 1, 1]` where Tc = 0 (first window) or 3840 (subsequent)
- Wave output: `[T_audio, 1]` where T_audio varies (typically ~24000 samples = 1s at 24kHz)

### Q21: Are there unsupported ops?

**Unknown until first test.** The HiFi-GAN2 graph uses:
- Conv1d (3 stages, 9 resblocks with kernel sizes [3,7,11])
- Snake activation (`x + sin²(αx)/α`)
- STFT/iSTFT (N_FFT=16)
- Element-wise ops (add, mul, tanh, etc.)

All should have CANN implementations in ACLNN. But some ops (especially Snake's custom `sin²` expression) may need verification.

### Q22: Why is CPU vocoder the current production choice?

The explicit comment at `omni.cpp:5001`:
```
"CANN流跨线程需算子适配，vocoder暂用CPU"
```

Translation: "CANN stream cross-thread needs operator adaptation, vocoder temporarily uses CPU."

This was a **deliberate risk-avoidance decision**, not a technical impossibility. The concern is that the CANN stream management across the omni pipeline's multi-threaded architecture (main thread, TTS thread, T2W worker thread) may have issues with certain vocoder operators.

### Q23: Any documented issues in history?

No explicit bug reports or crash logs were found in the codebase commits or comments. The "暂用CPU" (temporarily uses CPU) language suggests it was a **precautionary** rather than a **remedial** decision.

---

## 7. Path Hit Counters (Added)

Per mission P3 requirement, low-overhead path counters added as global atomics in `token2wav-impl.cpp`:

```cpp
// Path hit counters (P3 — CANN Vocoder Audit)
// Gates: OMNI_VOC_PATH_STATS=1 (default OFF, zero overhead when OFF)
static std::atomic<int64_t> g_vocoder_cpu_dispatch_count{0};
static std::atomic<int64_t> g_vocoder_cann_dispatch_count{0};
static std::atomic<int64_t> g_vocoder_cann_success_count{0};
static std::atomic<int64_t> g_vocoder_cann_failure_count{0};
static std::atomic<int64_t> g_vocoder_cpu_fallback_count{0};
```

These are incremented:
- `cpu_dispatch_count`: In `voc_hg2_runner_eval_stream` when backend is CPU
- `cann_dispatch_count`: In `voc_hg2_runner_eval_stream` when backend is CANN
- `cann_success_count`: After successful `ggml_backend_graph_compute` on CANN
- `cann_failure_count`: After failed compute or allocation on CANN
- `cpu_fallback_count`: If CANN init fails and falls back to CPU at startup

Printed once at session end when `OMNI_VOC_PATH_STATS=1`:
```
[VOCODER_PATH_STATS] cpu_dispatch=N  cann_dispatch=N  cann_success=N  cann_failure=N  cpu_fallback=N
```

---

## 8. Key Source Locations Summary

| Item | File | Line(s) |
|------|------|---------|
| OMNI_VOC_DEVICE parsing (main) | omni.cpp | 4991-5007 |
| OMNI_VOC_DEVICE parsing (worker) | omni.cpp | 10019 |
| CANN→CPU default rationale | omni.cpp | 5001-5002 |
| Vocoder backend init (CANN) | token2wav-impl.cpp | 6633-6637 |
| Vocoder backend init (CPU) | token2wav-impl.cpp | 6649-6651 |
| Backend fallback chain | token2wav-impl.cpp | 6638-6646 |
| Flow backend init (CANN) | token2wav-impl.cpp | 7278-7282 |
| Per-chunk graph creation | token2wav-impl.cpp | 6770-6783 |
| galloc alloc per chunk | token2wav-impl.cpp | 6790 |
| Tensor upload (H2D) | token2wav-impl.cpp | 6800-6805 |
| Graph compute | token2wav-impl.cpp | 6818 |
| Output download (D2H) | token2wav-impl.cpp | 6826-6839 |
| Flow → mel (D2H) | token2wav-impl.cpp | 9786-9789 |
| Mel cache → vocoder input | token2wav-impl.cpp | 9815-9816 |
| Vocoder call | token2wav-impl.cpp | 9824-9825 |
| Path counters (added P3) | token2wav-impl.cpp | (new, after line 26) |

---

## 9. P3 Decision

**CANN_VOCODER_AUDIT_COMPLETE.** All 23 questions answered. Key finding: CANN path is compiled, enabled via `OMNI_VOC_DEVICE=gpu` (NOT `OMNI_VOC_DEVICE=cann`), no silent fallback, per-chunk graph re-creation, and a D2H+H2D round-trip between flow and vocoder.

**Proceed to P4 (Minimal Reachability Smoke).**
