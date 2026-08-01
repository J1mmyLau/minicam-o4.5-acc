# F6 C5: Global Fallback Audit — Critical Stage Dependencies

**Date:** 2026-08-01
**Source:** `tools/omni/omni.cpp`, `tools/omni/omni.h`

---

## Global Atomic Stages (PROCESS-SCOPED — NOT request-scoped)

From `tools/omni/omni.cpp:82-85`:

```cpp
std::atomic<int64_t> g_e2e_flow_start_ns{0};      // F0
std::atomic<int64_t> g_e2e_flow_end_ns{0};        // F1
std::atomic<int64_t> g_e2e_vocoder_start_ns{0};   // V0
std::atomic<int64_t> g_e2e_vocoder_end_ns{0};     // V1
```

And from `tools/omni/omni.h:257`:
```cpp
std::atomic<int64_t> timestamps_ns[STAGE_COUNT] = {};  // Per-request (reset() called at boundary)
```

## How Globals Are Written (in T2W worker)

The Flow/Vocoder globals are set in the T2W worker thread (lines ~10850-10900 in `omni.cpp`):

```cpp
// Flow start
g_e2e_flow_start_ns.store(ggml_time_ms(), std::memory_order_relaxed);
// ... flow computation ...
g_e2e_flow_end_ns.store(ggml_time_ms(), std::memory_order_relaxed);

// Vocoder start
g_e2e_vocoder_start_ns.store(ggml_time_ms(), std::memory_order_relaxed);
// ... vocoder computation ...
g_e2e_vocoder_end_ns.store(ggml_time_ms(), std::memory_order_relaxed);
```

## How Globals Are Read (in JSON writer)

From `tools/omni/omni.cpp:1077-1080`:

```cpp
add_global_fallback("flow_start",    g_e2e_flow_start_ns,    STAGE_flow_start);
add_global_fallback("flow_end",      g_e2e_flow_end_ns,      STAGE_flow_end);
add_global_fallback("vocoder_start", g_e2e_vocoder_start_ns, STAGE_vocoder_start);
add_global_fallback("vocoder_end",   g_e2e_vocoder_end_ns,   STAGE_vocoder_end);
```

The `add_global_fallback` function (line ~1090) reads the global atomic and stores it into `timestamps_ns[stage]` **if the stage is still 0** (i.e., wasn't set by `record()`):

```cpp
void add_global_fallback(const char *name, std::atomic<int64_t> &global, E2EStage stage) {
    int64_t global_val = global.load(std::memory_order_relaxed);
    int64_t existing = t.timestamps_ns[stage].load(std::memory_order_relaxed);
    if (existing == 0 && global_val > 0) {
        t.timestamps_ns[stage].store(global_val, std::memory_order_relaxed);
    }
}
```

## Contamination Scenario

```
Request N:
  1. reset() zeroes all globals + timestamps_ns[]
  2. HTTP handler processes request N
  3. T2W worker sets g_e2e_flow_start_ns = 500
  4. JSON writer calls add_global_fallback() → timestamps_ns[flow_start] = 500
  5. Request N completes cleanly

Request N+1:
  6. reset() zeroes all globals + timestamps_ns[]
  7. HTTP handler processes request N+1
  8. T2W worker for request N+1 sets g_e2e_flow_start_ns = 600
  9. BUT: if a LATE T2W worker from request N is still running:
     → g_e2e_flow_start_ns gets overwritten with request N's value
     → Request N+1's flow_start = request N's timestamp
```

**Probability in current setup:** LOW, because:
- Sequential ABBA with server restart between blocks means at most 1 request inflight at a time
- T2W worker drains before next request starts (server is sequential)

**But this is fragile.** Any future change that allows concurrent requests (or T2W worker doesn't drain synchronously) will trigger cross-request contamination.

## Current Risk Assessment

| Stage | Global | Risk in current sequential setup | Risk with concurrent requests |
|-------|--------|----------------------------------|------------------------------|
| flow_start | `g_e2e_flow_start_ns` | LOW (single request, worker drains) | HIGH (late write overwrites) |
| flow_end | `g_e2e_flow_end_ns` | LOW | HIGH |
| vocoder_start | `g_e2e_vocoder_start_ns` | LOW | HIGH |
| vocoder_end | `g_e2e_vocoder_end_ns` | LOW | HIGH |

## Fix Required (C5 ACTION)

### Approach: Request-Scoped Profile Handle via T2W Queue Item

1. **Add profile handle to T2W queue item:**
```cpp
struct T2WQueueItem {
    // existing fields...
    E2EStageTiming *profile_handle;  // request-scoped profile (or shared_ptr)
    uint32_t request_generation_id;
};
```

2. **T2W worker writes to handle, not globals:**
```cpp
// In T2W worker:
auto *profile = queue_item.profile_handle;
profile->record(STAGE_flow_start, queue_item.request_generation_id);
// ... flow computation ...
profile->record(STAGE_flow_end, queue_item.request_generation_id);
// ... vocoder computation ...
profile->record(STAGE_vocoder_start, queue_item.request_generation_id);
profile->record(STAGE_vocoder_end, queue_item.request_generation_id);
```

3. **Remove global atomics:**
```cpp
// DELETE: g_e2e_flow_start_ns, g_e2e_flow_end_ns,
//         g_e2e_vocoder_start_ns, g_e2e_vocoder_end_ns
```

4. **Remove add_global_fallback() calls** — no longer needed.

### Minimum Viable Fix (for Phase 3)

Even without full refactoring, at minimum:

1. **Add generation_id to global writes:**
```cpp
// Instead of raw store:
g_e2e_flow_start_ns.store((ggml_time_ms() << 32) | generation_id, ...);
```

2. **Validate generation_id on global read:**
```cpp
// In add_global_fallback:
int64_t raw = global.load(...);
uint32_t gen = raw & 0xFFFFFFFF;
int64_t ts = raw >> 32;
if (gen == current_request_generation) {
    // safe to use
}
```

This fixes the contamination risk without restructuring the T2W queue item.

## Deprecation Timeline

| Phase | Action |
|-------|--------|
| Phase 3 C5 | Document risk; add generation_id to global atomics (minimum fix) |
| Phase 3 C8 | Full refactor: request-scoped profile handle via T2W queue item |
| Post-Phase 3 | Remove global atomics entirely |

## Gate

```
critical_global_fallback_mask = {flow_start, flow_end, vocoder_start, vocoder_end}
critical_global_fallback_count MUST = 0 (by C8 completion)
```

Until C8, globals are acceptable with generation_id guard (minimum fix).
