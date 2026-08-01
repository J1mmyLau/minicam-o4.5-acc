# F6 C8 Global Mirror Pointer Audit (N4+N5)

**Date:** 2026-08-01
**Status:** FIXED — process-global raw pointers replaced with thread_local RAII guard

## Original Design (commit 0377ade)

Four process-global `std::atomic<int64_t>*` pointers:

```cpp
std::atomic<int64_t>* g_c8_flow_start_ptr    = nullptr;  // omni.cpp:92
std::atomic<int64_t>* g_c8_flow_end_ptr      = nullptr;  // omni.cpp:93
std::atomic<int64_t>* g_c8_vocoder_start_ptr = nullptr;  // omni.cpp:94
std::atomic<int64_t>* g_c8_vocoder_end_ptr   = nullptr;  // omni.cpp:95
```

### Auditor Questions (N4)

| # | Question | Answer (original design) |
|---|----------|--------------------------|
| 1 | Process-global or thread_local? | **Process-global** — visible to all threads |
| 2 | Which thread sets them? | T2W worker thread (omni.cpp T2W main loop) |
| 3 | Which thread writes through them? | T2W worker thread, inside feed_window() (token2wav-impl.cpp e2e_record_ns) |
| 4 | Which thread clears them? | T2W worker thread, after feed_window() returns |
| 5 | Can request switch between set and clear? | **No in current architecture** — single T2W worker, synchronous feed_window() |
| 6 | Multiple T2W workers? | **No** — one T2W worker thread |
| 7 | Nested feed_window? | **No** — feed_window is not reentrant |
| 8 | Exception-safe clear? | **No** — if feed_window() throws, pointers remain stale |
| 9 | Early return safe? | **No** — `continue` in the loop before clear would leak pointers |
| 10 | Can Request B overwrite Request A's pointers? | **No in current architecture** but only because single-T2W-worker + synchronous-feed_window |
| 11 | Dangling pointer after profile retire? | **Theoretical risk** — if E2EStageTiming is on stack and T2W outlives it |
| 12 | Who owns the raw pointer target? | `E2EStageTiming::timestamps_ns[]` — owned by `omni_context::e2e_stage` |

### Happens-Before Analysis (original design)

Given single T2W worker + synchronous feed_window:
```
T2W worker iteration N:
  1. set g_c8_*_ptr → Profile_A          [store-relaxed]
  2. feed_window() blocks                [synchronous, same thread]
     - e2e_record_ns() writes through g_c8_*_ptr → Profile_A.timestamps_ns[]
  3. feed_window() returns
  4. clear g_c8_*_ptr → nullptr          [store-relaxed]
  5. loop back to step 1
```

**Verdict:** Safe in the current single-T2W-worker architecture, but FRAGILE:
- If feed_window() becomes async → broken
- If a second T2W worker is added → broken
- If an exception is thrown in feed_window → stale pointers
- If a `continue` before clear → stale pointers

### Cross-Request Contamination Scenario (original design)

Would require ALL of:
1. Second T2W worker thread exists, OR feed_window is async
2. Request A sets pointers to Profile A
3. Request B sets pointers to Profile B (overwriting A's)
4. Request A's Flow/Vocoder completes and writes → **goes to Profile B**

With single T2W worker + synchronous feed_window, this cannot happen because:
- Only one thread touches the pointers
- feed_window() blocks the thread, preventing the loop from advancing
- Pointers are cleared before the next iteration

## Fixed Design (N5)

Replaced 4 process-global raw pointers with a single thread_local context + RAII guard:

### token2wav-impl.h
```cpp
struct C8FlowVocoderTargets {
    std::atomic<int64_t>* flow_start    = nullptr;
    std::atomic<int64_t>* flow_end      = nullptr;
    std::atomic<int64_t>* vocoder_start = nullptr;
    std::atomic<int64_t>* vocoder_end   = nullptr;
    uint32_t               generation   = 0;
    int                    depth         = 0;  // nesting support
};

extern thread_local C8FlowVocoderTargets g_c8_thread_targets;

class C8ProfileScope {
    // Sets g_c8_thread_targets on construction
    // Restores previous context on destruction (RAII)
    // Non-copyable, non-movable
};
```

### Usage in T2W worker
```cpp
C8ProfileScope c8_scope(
    handle ? &handle->timestamps_ns[STAGE_flow_start]    : nullptr,
    handle ? &handle->timestamps_ns[STAGE_flow_end]      : nullptr,
    handle ? &handle->timestamps_ns[STAGE_vocoder_start] : nullptr,
    handle ? &handle->timestamps_ns[STAGE_vocoder_end]   : nullptr,
    generation);
// ... feed_window() loop ...
// C8ProfileScope destructor fires here, restoring previous context
```

### Safety Properties

| Property | Original (process-global raw ptr) | Fixed (thread_local + RAII) |
|----------|-----------------------------------|----------------------------|
| Cross-thread visibility | YES — any thread can read/write | NO — thread-local storage |
| Exception safety | NO — manual clear, skip on exception | YES — destructor always runs |
| Early return safety | NO — continue/break skip clear | YES — scope exit triggers destructor |
| Nesting support | NO — single set of pointers | YES — depth counter, save/restore |
| Generation validation | NO | YES — generation stored in context |
| Stale pointer after profile retire | Risk if profile freed | Same risk (target addresses don't change) |

### Remaining Risk

The pointers stored in `g_c8_thread_targets` point to `E2EStageTiming::timestamps_ns[]` entries.
These addresses are stable as long as `E2EStageTiming` is alive. Since `E2EStageTiming` is a member
of `omni_context` (heap-allocated, process-lifetime), this is safe.

Even if `reset()` clears the timestamps_ns values, the addresses remain valid — writes to cleared
slots are harmless (they'll be overwritten by the next valid request's record()).

## Verdict

**N5 FIX APPLIED.** Process-global raw pointers replaced with thread_local RAII guard.
Exception-safe, return-path-safe, nesting-safe, no cross-thread visibility.
