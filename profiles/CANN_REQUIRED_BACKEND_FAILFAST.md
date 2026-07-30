# CANN Required Backend Fail-Fast Design (P1)

**Date:** 2026-07-30
**Status:** IMPLEMENTED — 4 insertion points, 5 tracking state fields

---

## Objective

When the canonical CANN candidate configuration (`OMNI_T2W_DEVICE=cann-flow-only`,
`OMNI_VOC_DEVICE=gpu`) is requested but CANN is unavailable, the system must:

1. **Output a clear error** identifying which component failed and why
2. **Exit with non-zero** or return an error response (server must not silently start with CPU)
3. **Never silently fall back to CPU** for the canonical CANN configuration

---

## Design

### Layer 1: CANN Registry Availability Query

```cpp
// ggml-cann.h / ggml-cann.cpp
bool ggml_backend_cann_is_available();
```

Returns `true` iff `aclInit()` succeeded and CANN devices are registered in the
ggml backend registry. Safe to call from any thread at any time.

### Layer 2: omni_context Tracking State

Five new fields on `omni_context`:

```
cann_registry_available        // aclInit succeeded, devices registered
cann_backend_init_success      // at least one ggml_backend_cann_init() succeeded
cann_backend_init_failure      // at least one ggml_backend_cann_init() failed
cann_requested_but_unavailable // canonical CANN config requested, CANN missing
cpu_fallback_count             // incremented on each CANN→CPU fallback (non-fatal when CANN not required)
```

### Layer 3: Four Fail-Fast Insertion Points

#### FP-1: omni_init() — Flow Device Check

**File:** `tools/omni/omni.cpp`
**Trigger:** `OMNI_T2W_DEVICE=cann-flow-only` is set
**Check:** `ggml_backend_cann_is_available()`
**Action on failure:**
- Set `cann_requested_but_unavailable = true`
- Print ERROR with environment variable value
- Print FAIL-FAST notice
- Do NOT set `token2wav_defer_worker_init` (will not attempt CANN init)

#### FP-2: omni_init() — Vocoder Device Check

**File:** `tools/omni/omni.cpp`
**Trigger:** `OMNI_VOC_DEVICE=gpu` (or gpu:N) is set
**Check:** `ggml_backend_cann_is_available()`
**Action on failure:**
- Set `cann_requested_but_unavailable = true`
- Print ERROR and FAIL-FAST notice

#### FP-3: t2w_thread_func_cpp — Worker Thread Init

**File:** `tools/omni/omni.cpp`
**Trigger:** `init_from_prompt_cache_gguf()` returns false AND `cann_requested_but_unavailable` is true
**Action on failure:**
- Set `cann_backend_init_failure = true`
- Set `token2wav_initialized = false`
- Print FATAL error message
- **Return from worker thread** (no CPU fallback attempted)

#### FP-4: omni_init() — Non-Deferred CPU Fallback

**File:** `tools/omni/omni.cpp`
**Trigger:** GPU init fails AND `cann_requested_but_unavailable` is true
**Action on failure:**
- Skip CPU fallback entirely
- Print FATAL error message with `cpu_fallback_count`
- `init_ok` stays false → `omni_init()` fails → server returns error

---

## Behavior Matrix

| CANN Available | Config | Flow Backend | Vocoder Backend | Result |
|:-:|:-:|:-:|:-:|---|
| YES | cann-flow-only + gpu | CANN (worker thread) | CANN (worker thread) | ✅ CANN RTF |
| YES | (not set) + (not set) | CPU | CPU | ⚠️ CPU (expected, CANN not requested) |
| NO | cann-flow-only + gpu | FATAL: no fallback | FATAL: no fallback | ❌ `omni_init` fails, server returns error |
| NO | (not set) + (not set) | CPU | CPU | ⚠️ CPU (expected, CANN not requested) |
| NO | cann-flow-only + cpu | FATAL: no fallback | CPU (explicit) | ❌ `omni_init` fails |

---

## Test Plan

### Unit tests (manual verification):
1. Set `OMNI_T2W_DEVICE=cann-flow-only` with CANN driver stopped → verify `omni_init` fails
2. Set `OMNI_VOC_DEVICE=gpu` with CANN driver stopped → verify `omni_init` fails
3. Set both env vars with CANN driver running → verify normal CANN operation
4. Set neither env var with CANN driver stopped → verify CPU fallback works (expected)

### Integration tests:
- P2: 30× process restart matrix (verifies clean CANN re-init across process boundaries)
- P3: R11 regression (verifies CANN backend free/re-init lifecycle)

---

## Relationship to R15

R15 (server CANN re-init failure) was a symptom of the underlying `aclInit` lifecycle
issue. The R15 fix (accepting `ACL_ERROR_REPEAT_INITIALIZE` as non-fatal) is a
**defensive layer**, but the fail-fast mechanism is the **correctness layer**:

- **R15 defensive fix**: Prevents crash when `aclInit` is called redundantly
- **P1 fail-fast**: Prevents silent CPU fallback when CANN is explicitly required

Both layers together ensure that:
1. The system doesn't crash when `aclInit` returns 100002 (R15)
2. The system doesn't silently produce CPU-latency audio when CANN is required (P1)

---

## Files Modified

| File | Change |
|------|--------|
| `ggml/src/ggml-cann/ggml-cann.cpp` | Added `ggml_backend_cann_is_available()` |
| `ggml/include/ggml-cann.h` | Added declaration + documentation |
| `tools/omni/omni.h` | Added 5 CANN tracking fields to `omni_context` |
| `tools/omni/omni.cpp` | Added 4 fail-fast insertion points |
