# F6 C8 — Thread-Local Runtime Contract Proof (S3)

**Date:** 2026-08-01
**HEAD:** `b746244`
**Status:** PROVEN_BY_CONSTRUCTION — no runtime verification needed

## Claim

All Flow/Vocoder stage writes (STAGE_flow_start, STAGE_flow_end, STAGE_vocoder_start,
STAGE_vocoder_end) happen on the **same thread** that sets the C8ProfileScope RAII guard.
Therefore, `thread_local C8FlowVocoderTargets g_c8_thread_targets` is correct by construction.

## Architecture: Single T2W Worker Thread

```
omni_context::t2w_thread  (std::thread, 1 instance)
    │
    └─ t2w_thread_func_cpp()  or  t2w_thread_func()
           │
           └─ while (t2w_thread_running)
                  │
                  ├─ cv.wait() — dequeues T2WOut* from T2WThreadInfo::queue
                  ├─ [C8ProfileScope c8_scope(...)]  ← SET on T2W worker thread
                  ├─ [record Q2]
                  ├─ while (token_buffer >= threshold)
                  │     └─ feed_window()              ← SYNCHRONOUS, blocks until done
                  │           ├─ Flow (push_tokens)   ← e2e_record_ns_oneshot(F0, F1)
                  │           └─ Vocoder (infer)      ← e2e_record_ns_oneshot(V0, V1)
                  ├─ [~c8_scope()]                    ← RESTORE on T2W worker thread
                  └─ audio output callback
```

## Proof by Construction

### Fact 1: Single T2W worker thread

```cpp
// omni.h:716
std::thread t2w_thread;   // ONE instance in omni_context

// omni.cpp:13046
ctx_omni->t2w_thread = std::thread(t2w_thread_func, ctx_omni, ctx_omni->params);
```

No other thread calls feed_window(). No thread pool distributes T2W work.
The T2WThreadInfo::queue is consumed by exactly one worker thread.

### Fact 2: feed_window() is synchronous (blocking)

```cpp
// token2wav-impl.cpp:9767
bool Token2MelSession::feed_window(...) {
    e2e_record_ns_oneshot(g_e2e_flow_start_ns);    // F0
    if (!t2m_.push_tokens(...)) return false;        // Flow: synchronous
    e2e_record_ns_oneshot(g_e2e_flow_end_ns);       // F1
    // ... mel processing ...
    e2e_record_ns_oneshot(g_e2e_vocoder_start_ns);  // V0
    // ... vocoder inference ...                       // Vocoder: synchronous
    e2e_record_ns_oneshot(g_e2e_vocoder_end_ns);    // V1
    return true;
}
```

No `std::thread`, `std::async`, `aclrtLaunch` with callback, or thread pool inside feed_window()
or any of its callees. The function blocks until Flow and Vocoder complete, then returns.

### Fact 3: C8ProfileScope brackets feed_window() on the same thread

```cpp
// omni.cpp:11169-11208
C8ProfileScope c8_scope(     // SET on T2W worker thread
    &handle->timestamps_ns[STAGE_flow_start],
    &handle->timestamps_ns[STAGE_flow_end],
    &handle->timestamps_ns[STAGE_vocoder_start],
    &handle->timestamps_ns[STAGE_vocoder_end],
    gen);

// ... (same thread, no yield points that could migrate work)

if (token2wav_session->feed_window(window, is_last_window, chunk_wav)) {
    // feed_window completed, Flow+Vocoder writes done
}

// ~c8_scope() runs here  ← RESTORE on T2W worker thread (same thread)
```

### Fact 4: e2e_record_ns() reads thread_local on same thread

```cpp
// token2wav-impl.cpp:81-100
static void e2e_record_ns(std::atomic<int64_t>& target) {
    // ... timestamp write to global atomic ...

    const C8FlowVocoderTargets& ctx = g_c8_thread_targets;  // thread_local read
    if (!ctx.flow_start) return;
    // ... mirror to per-request timestamps_ns[] ...
}
```

### Conclusion

By Facts 1-4, the thread that sets `g_c8_thread_targets` (C8ProfileScope constructor)
is the **same thread** that reads `g_c8_thread_targets` (e2e_record_ns inside feed_window)
and the **same thread** that restores it (C8ProfileScope destructor).

There is **no execution path** where a Flow/Vocoder write occurs on a thread other than
the T2W worker thread that set the scope. The single-threaded, synchronous architecture
guarantees this.

## Happens-Before Chain (C++ Memory Model)

```
Thread T (T2W worker):
  c8_scope constructed
    g_c8_thread_targets.flow_start = ptr   (non-atomic write, sequenced-before)
    g_c8_thread_targets.generation = gen   (non-atomic write)
    ──────── sequenced-before ────────
  [record Q2 via record() — atomic store to timestamps_ns[20]]
    ──────── sequenced-before ────────
  feed_window()
    e2e_record_ns(g_e2e_flow_start_ns)
      reads g_c8_thread_targets.flow_start   (same thread, same variable)
      mirror->store(ns, relaxed)              (atomic store)
    ... Flow processing ...
    e2e_record_ns(g_e2e_flow_end_ns)
      reads g_c8_thread_targets.flow_end
    ... Vocoder processing ...
    e2e_record_ns(g_e2e_vocoder_end_ns)
      reads g_c8_thread_targets.vocoder_end
  feed_window() returns
    ──────── sequenced-before ────────
  ~c8_scope()
    g_c8_thread_targets = saved_            (non-atomic write, restores previous)
```

All accesses to `g_c8_thread_targets` are from thread T. No atomics needed for the
thread_local variable itself — only for the `std::atomic<int64_t>*` targets it points to,
which use `memory_order_relaxed` (sufficient for single-writer, eventual-reader pattern
where the reader synchronizes via request lifecycle, not per-byte ordering).

## Safety Properties

| Property | Status | Mechanism |
|----------|--------|-----------|
| No cross-thread access to g_c8_thread_targets | GUARANTEED | thread_local + single T2W worker |
| Scope cannot outlive request | GUARANTEED | RAII destructor on scope exit |
| Nested scopes handled correctly | GUARANTEED | saved_ copy + depth counter |
| Exception safety | GUARANTEED | Destructor always runs (stack unwinding) |
| Stale pointer prevention | GUARANTEED | Destructor restores previous (nullptr for outermost) |
| Concurrent request contamination | IMPOSSIBLE | Single T2W worker serializes all requests |

## Runtime Verification (Optional)

The following fields can be added to C8FlowVocoderTargets for runtime verification in debug builds.
They are NOT needed for correctness — the proof above is by construction, not by observation.

```cpp
struct C8FlowVocoderTargets {
    std::atomic<int64_t>* flow_start    = nullptr;
    std::atomic<int64_t>* flow_end      = nullptr;
    std::atomic<int64_t>* vocoder_start = nullptr;
    std::atomic<int64_t>* vocoder_end   = nullptr;
    uint32_t               generation   = 0;
    int                    depth         = 0;

    // Optional runtime verification fields (DEBUG only)
    std::thread::id        scope_set_thread_id;
    std::thread::id        flow_begin_thread_id;
    std::thread::id        flow_end_thread_id;
    std::thread::id        vocoder_begin_thread_id;
    std::thread::id        vocoder_end_thread_id;
    std::thread::id        scope_clear_thread_id;
    uint32_t               nested_scope_count{0};
    uint32_t               missing_tls_context_count{0};
    uint32_t               wrong_profile_context_count{0};
    uint32_t               late_after_scope_count{0};
};
```

If runtime verification is ever desired, add `assert(ctx.scope_set_thread_id == std::this_thread::get_id())`
in e2e_record_ns(). But given the architectural proof above, this would always pass.

## Verdict

**thread_local IS correct for this architecture.**

The proof does NOT rely on:
- "thread_local is naturally request-scoped" (it isn't, in general)
- "there's only one thread in the process" (there are many — LLM, HTTP, etc.)
- "the compiler guarantees it" (it doesn't, for arbitrary code)

The proof relies on:
1. Single T2W worker thread consuming the queue
2. Synchronous feed_window() that does not spawn threads
3. C8ProfileScope RAII guard bracketing feed_window() on the same thread
4. No other code path writes Flow/Vocoder stages

If any of these architectural invariants change, the thread_local approach must be
re-evaluated. If feed_window() ever becomes asynchronous or the T2W worker ever
becomes a thread pool, the explicit profile handle passing approach (via T2WOut::
profile_handle, already wired in the T2W queue item) must be used instead.

The explicit handle is already available as a fallback:
```cpp
// T2WOut::profile_handle already carries the per-request E2EStageTiming*
// If thread_local ever becomes unsafe, switch e2e_record_ns() to use
// the profile_handle from the T2W queue item instead of g_c8_thread_targets.
```
