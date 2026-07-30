# ACL Init Lifecycle Audit (P1)

**Date:** 2026-07-30
**Status:** COMPLETE — 10/10 questions answered — FAIL-FAST IMPLEMENTED

---

## Executive Summary

The CANN SDK `aclInit()` / `aclFinalize()` lifecycle was audited across the entire
llama.cpp-omni-operator codebase.

**Findings:**
- `aclInit(nullptr)` is called from 2 sites, both in `ggml-cann.cpp`
- `aclFinalize()` is called from **ZERO** sites — never invoked anywhere
- Silent CPU fallback chain exists in 2 independent code paths
- New `ggml_backend_cann_is_available()` API + tracking state added to omni_context

**Risk:** Process that exits without `aclFinalize()` may leave stale CANN driver state,
potentially causing `ACL_ERROR_REPEAT_INITIALIZE` on subsequent runs. This is the
suspected root cause of R15 server CANN re-init failures.

---

## Q1: Where is the FIRST aclInit call in the process lifecycle?

**Answer:** `ggml_backend_cann_reg()`, called indirectly from `llama_backend_init()`:
```
llama_backend_init()                             // llama.cpp
  → ggml_backend_load_all_from_file()            // ggml-backend-reg.cpp
    → ggml_backend_cann_reg()                    // ggml-cann.cpp:3113
      → aclInit(nullptr)                          // FIRST CALL
```

**Evidence:** `server-omni.cpp:106` calls `llama_backend_init()` before starting the HTTP server.

---

## Q2: How many aclInit calls per process?

**Answer:** 1+N, where N = number of CANN backends created.

1. `ggml_backend_cann_reg()` calls it once (guarded by `initialized` flag + mutex)
2. `ggml_backend_cann_init(device)` calls it again for each backend created (redundant; returns 100002)

With 2 NPU devices and canonical configuration (Flow + Vocoder):
- Flow on device 0: 1 call from `ggml_backend_cann_reg()` + 1 from `ggml_backend_cann_init(0)`
- Vocoder on device 0: 1 from `ggml_backend_cann_init(0)` (registry already initialized)

Total: 3 `aclInit()` calls, first succeeds, next 2 return 100002 (non-fatal).

---

## Q3: Is ACL_ERROR_REPEAT_INITIALIZE (100002) legal?

**Answer:** YES. CANN SDK documentation says `aclInit` "can be called only once in a process."
After the first successful call, subsequent calls return `ACL_ERROR_REPEAT_INITIALIZE = 100002`.
This is a non-fatal return code that indicates the runtime is already initialized.

**Our handling:** Both call sites accept 100002 as non-fatal:
```cpp
if (acl_ret != ACL_SUCCESS && acl_ret != ACL_ERROR_REPEAT_INITIALIZE) {
    // Only fatal errors beyond repeat-init cause failure
}
```

---

## Q4: What happens when aclInit fails in ggml_backend_cann_reg()?

**Answer:** The function returns `nullptr` instead of a valid registry pointer. This means:
- CANN devices are NOT registered in the ggml backend registry
- `register_backend(nullptr)` in `ggml-backend-reg.cpp:180-182` is a **silent no-op**
- `ggml_backend_init_by_type(GGML_BACKEND_DEVICE_TYPE_GPU)` won't find CANN

**Code evidence (`ggml-backend-reg.cpp:179-182`):**
```cpp
void ggml_backend_registry::register_backend(ggml_backend_reg_t reg) {
    if (reg == nullptr) return;  // SILENT NO-OP — no error message
    // ...
}
```

---

## Q5: What is the silent CPU fallback chain?

**Answer:** TWO independent fallback chains exist:

### Chain A: `ggml_backend_init_best()` (LLM backend)
```
ggml_backend_init_by_type(GPU)   → nullptr (CANN not registered)
ggml_backend_init_by_type(iGPU)  → nullptr (no iGPU on server)
ggml_backend_init_by_type(CPU)   → CPU backend (ALWAYS succeeds)
```
**Code:** `ggml-backend-reg.cpp:367-383`

### Chain B: `fm_loader_init_backend_gpu_idx()` (T2W Flow/Vocoder)
```
ggml_backend_cann_init(0)                  → nullptr (registry is null)
ggml_backend_init_by_type(GPU, nullptr)    → nullptr (CANN not registered)
ggml_backend_init_by_type(iGPU, nullptr)   → nullptr
ggml_backend_init_by_type(CPU, nullptr)    → CPU backend (ALWAYS succeeds)
```
**Code:** `token2wav-impl.cpp:2273-2298`

**Risk:** When CANN is unavailable, both chains silently fall back to CPU. The user sees
normal operation but with CPU RTF (~3.97) instead of CANN RTF (~0.234).

---

## Q6: What resources exist if aclInit partially succeeds?

**Answer:** Two scenarios:

**Scenario 1: Registry aclInit succeeds, but backend init fails.**
- `initialized = true` — CANN driver state exists
- CANN devices registered in ggml registry
- `ggml_backend_cann_is_available()` returns `true`
- Backend creation failure is at the per-backend level, not the registry level

**Scenario 2: Registry aclInit fails (returns error other than 100002).**
- `initialized` stays `false` (can retry on next call)
- No CANN devices registered
- `ggml_backend_cann_is_available()` returns `false`
- All downstream CANN calls will hit null registry → CPU fallback

---

## Q7: Who calls aclFinalize()?

**Answer:** NOBODY. **ZERO call sites in the entire codebase.**

CANN SDK documentation states: *"Need to call aclFinalize before the process exits."*

This is the underlying issue for R15: when a process exits without `aclFinalize()`,
the CANN driver may retain stale state. A new process that calls `aclInit()` may
encounter issues if the driver wasn't properly torn down.

**Should we add `aclFinalize()`?**
- Pro: Follows SDK requirements, clean driver state
- Con: `aclFinalize()` must be called before ANY other CANN API after it — in a
  multi-backend scenario, coordinating the finalization order is complex
- Current approach: Defensive error handling (accept 100002) + process restart matrix (P2)

---

## Q8: What is the aclInit/aclFinalize call count mismatch?

**Answer:** (1+N) `aclInit` calls, **0** `aclFinalize` calls.

Each run:
- `ggml_backend_cann_reg()` → `aclInit(nullptr)` — 1 call (the real one)
- `ggml_backend_cann_init(0)` → `aclInit(nullptr)` — up to N calls (all return 100002)
- `aclFinalize()` — **0 calls**

The SDK refcount mechanism (`aclFinalizeReference`) is also never used.

---

## Q9: Is multi-thread access to aclInit safe?

**Answer:** YES, but with caveats.

1. `ggml_backend_cann_reg()` has a **mutex guard** around the `initialized` check
2. Once `initialized = true`, subsequent calls return `&reg` without touching CANN APIs
3. `ggml_backend_cann_init()` calls `aclInit(nullptr)` but accepts 100002 — no side effects
4. The **worker-thread deferred init** mechanism avoids creating CANN backends in the
   main thread, preventing the cross-thread context issue documented in
   `ROOT_CAUSE_CONFIRMED_THREAD_OWNERSHIP`

**Race condition analysis:**
- Thread A: calls `ggml_backend_cann_reg()` → acquires mutex → `aclInit()` → sets `initialized`
- Thread B: calls `ggml_backend_cann_reg()` → waits for mutex → sees `initialized = true` → returns `&reg`
- Safe. Thread B never calls `aclInit` after Thread A.

---

## Q10: What happens on second server process re-registration?

**Answer:** Each process starts fresh:
- New process → `initialized = false` (static local variable)
- `aclInit(nullptr)` called fresh at `ggml_backend_cann_reg()` time
- If the previous process exited without `aclFinalize()`, the driver may have stale state
- **Risk:** stale driver state → `aclInit` returns error other than 100002 → registry null → CPU fallback

**Mitigation:** R15 defensive fixes accept `ACL_ERROR_REPEAT_INITIALIZE` as non-fatal.
P2 (30× process restart matrix) will experimentally verify this hypothesis.

---

## FAIL-FAST Implementation

### New API: `ggml_backend_cann_is_available()`

```cpp
// ggml-cann.cpp
bool ggml_backend_cann_is_available() {
    ggml_backend_reg_t reg = ggml_backend_cann_reg();
    return reg != nullptr;
}
```

### New tracking state in `omni_context`:

| Field | Type | Semantics |
|-------|------|-----------|
| `cann_registry_available` | bool | aclInit succeeded, devices registered |
| `cann_backend_init_success` | bool | at least one backend created successfully |
| `cann_backend_init_failure` | bool | at least one backend creation failed |
| `cann_requested_but_unavailable` | bool | canonical CANN config requested but CANN missing |
| `cpu_fallback_count` | int | number of CANN→CPU fallback events |

### Fail-Fast insertion points:

1. **omni_init() — Flow device check:** When `OMNI_T2W_DEVICE=cann-flow-only`, verify CANN
   availability. Set `cann_requested_but_unavailable = true` if not available.

2. **omni_init() — Vocoder device check:** When `OMNI_VOC_DEVICE=gpu`, verify CANN
   availability. Set `cann_requested_but_unavailable = true` if not available.

3. **t2w_thread_func_cpp — Worker init:** When CANN backend creation fails and
   `cann_requested_but_unavailable` is true, exit worker thread without falling back to CPU.
   Increment `cpu_fallback_count` otherwise.

4. **omni_init() — Non-deferred CPU fallback:** When GPU init fails and
   `cann_requested_but_unavailable` is true, skip CPU fallback (init_ok stays false).

---

## Gate Status

```
R15_ACL_INIT_GUARD             = IMPLEMENTED  (error checking + REPEAT_INITIALIZE)
P1_ACL_INIT_LIFECYCLE_AUDIT    = COMPLETE     (10/10 Q answered)
P1_FAIL_FAST_MECHANISM         = IMPLEMENTED  (4 insertion points)
```

## Next: P2 — 30× process restart matrix
