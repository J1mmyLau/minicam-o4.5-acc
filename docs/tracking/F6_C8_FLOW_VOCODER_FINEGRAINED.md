# F6 C8: Flow/Vocoder Fine-Grained Events

**Date:** 2026-08-01
**Depends on:** C5 (global fallback audit), C7 (Talker per-step instrumentation)
**Status:** PLAN (implementation pending)

---

## Current State

Flow/Vocoder events use **process-global atomics** (`g_e2e_flow_start_ns`, etc.):
- Written by T2W worker thread
- Read by JSON dump as fallback when `timestamps_ns[stage] == 0`
- Reset by `E2EStageTiming::reset()` at request boundary

This works for sequential processing but is fragile:
1. Late writes from request N can contaminate request N+1
2. No per-request event attribution
3. Cannot decompose T2W dequeue→WAV into sub-stages reliably

---

## Current Resolution

At millisecond resolution (current JSON output):
```
t2w_dequeue → WAV = 267ms (p50)
  Flow:      135ms (p50) — from global atomic
  Vocoder:   122ms (p50) — from global atomic
  Residual:    0ms (at ms resolution)
```

The 0ms residual at ms resolution is an artifact — the true pre-Flow and post-Vocoder overheads are sub-millisecond.

---

## C8 Target

Add **request-scoped** Flow/Vocoder stages:

| Event | Name | Thread | Scope | Notes |
|-------|------|--------|-------|-------|
| **Q1** | `t2w_preprocess_end` | T2W | Request | Preprocessing before Flow begins |
| **F0** | `flow_begin` | T2W | Request | Flow matching begins |
| **F1** | `flow_end` | T2W | Request | Flow matching complete |
| **V0** | `vocoder_begin` | T2W | Request | Vocoder begins |
| **V1** | `vocoder_end` | T2W | Request | Vocoder complete |

### Derived metrics:
```
Q0→Q1  = Q1 - Q0   # Dequeue → preprocessing complete (was 0ms at ms res)
Q1→F0  = F0 - Q1   # Preprocessing → Flow start
F0→F1  = F1 - F0   # Flow duration (was ~135ms from global)
F1→V0  = V0 - F1   # Flow→Vocoder inter-stage overhead
V0→V1  = V1 - V0   # Vocoder duration (was ~122ms from global)
V1→W0  = W0 - V1   # Vocoder→WAV packaging
```

This decomposes the 267ms T2W→WAV region and explains the sub-millisecond residual.

---

## Implementation Plan

### Step 1: Add request-scoped profile handle to T2W queue item

In the T2W queue item struct (currently in token2wav-impl or omni types):
```cpp
struct T2WOut {
    // ... existing fields ...
    uint32_t request_generation_id;
    int      request_index;
    // Pointer to the owning request's E2EStageTiming (NOT owned by T2WOut)
    E2EStageTiming *profile_handle;
};
```

### Step 2: Record Flow/Vocoder events via profile handle

In the T2W worker (token2wav-impl.cpp or equivalent):
```cpp
// After preprocessing
if (queue_item.profile_handle) {
    queue_item.profile_handle->record(STAGE_t2w_preprocess_end, queue_item.request_generation_id);
}

// Flow begin
if (queue_item.profile_handle) {
    queue_item.profile_handle->record(STAGE_flow_start, queue_item.request_generation_id);
}
// ... flow computation ...
// Flow end
if (queue_item.profile_handle) {
    queue_item.profile_handle->record(STAGE_flow_end, queue_item.request_generation_id);
}

// Vocoder begin
if (queue_item.profile_handle) {
    queue_item.profile_handle->record(STAGE_vocoder_start, queue_item.request_generation_id);
}
// ... vocoder computation ...
// Vocoder end
if (queue_item.profile_handle) {
    queue_item.profile_handle->record(STAGE_vocoder_end, queue_item.request_generation_id);
}
```

### Step 3: Remove global atomics

```cpp
// DELETE:
// std::atomic<int64_t> g_e2e_flow_start_ns{0};
// std::atomic<int64_t> g_e2e_flow_end_ns{0};
// std::atomic<int64_t> g_e2e_vocoder_start_ns{0};
// std::atomic<int64_t> g_e2e_vocoder_end_ns{0};
```

### Step 4: Remove add_global_fallback() calls

In `e2e_profile_dump_json()`, remove the fallback lambdas for flow/vocoder stages since they'll now come from `timestamps_ns[]`.

---

## New STAGE Enum Additions

```cpp
// Add to E2EStage enum in omni.h:
STAGE_t2w_preprocess_end,   // 20 — Q1: T2W preprocessing before Flow
// (flow_start, flow_end, vocoder_start, vocoder_end already exist at 9-12)
```

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| T2W queue item doesn't have profile handle field | Add field to T2WOut struct |
| Worker outlives request (profile handle dangling) | Use generation_id guard (already in `record()`) |
| Profile handle nullptr | Guard all writes with `if (profile_handle)` |
| token2wav-impl.cpp in separate compilation unit | Profile handle is just a pointer — no link dependency |

---

## Gate: T2W_WAV_RESIDUAL_EXPLAINED

After C8 implementation:
- Verify that `Q0→Q1 + Q1→F0 + F0→F1 + F1→V0 + V0→V1 + V1→W0 ≈ Q0→W0`
- Residual should be <0.1% of T2W→WAV (previously 0ms at ms resolution)
- Demonstrate that the former 0ms residual was a quantization artifact
