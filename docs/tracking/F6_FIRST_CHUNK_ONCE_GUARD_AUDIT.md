# F6 Phase 3 — First-Chunk Stage Recording Semantics Audit (R5)

**Date:** 2026-08-02
**HEAD:** `aabd12e`

## Executive Summary

**Verdict: FIRST-CHUNK SEMANTICS ARE CORRECTLY INTENDED, BUT ONCE-GUARD IS ON GLOBAL ATOMIC**

The code intends to record only the FIRST chunk's Flow/Vocoder timestamps. The mechanism (`e2e_record_ns_oneshot`) is conceptually correct. However, the once-guard checks the GLOBAL atomic (`g_e2e_flow_start_ns`) rather than the per-request slot, which creates a vulnerability: if the global is reset between chunks of the same request, the once-guard fails and subsequent chunks can overwrite first-chunk data.

## Code Analysis

### Recording Points (`token2wav-impl.cpp`)

```cpp
// Line 9956: Flow start — before push_tokens()
e2e_record_ns_oneshot(g_e2e_flow_start_ns);
// ... push_tokens (Flow execution) ...
// Line 9962: Flow end — after push_tokens()
e2e_record_ns_oneshot(g_e2e_flow_end_ns);

// Line 9991: Vocoder start — before vocoder
e2e_record_ns_oneshot(g_e2e_vocoder_start_ns);
// ... vocoder execution ...
// Line 9998: Vocoder end — after vocoder
e2e_record_ns_oneshot(g_e2e_vocoder_end_ns);
```

### Once-Guard Mechanism (`token2wav-impl.cpp:102-107`)

```cpp
static void e2e_record_ns_oneshot(std::atomic<int64_t>& target) {
    if (!g_e2e_profile_enabled) return;
    // Only record if not already set (one-shot for first window only)
    if (target.load(std::memory_order_relaxed) != 0) return;  // ← GLOBAL atomic check
    e2e_record_ns(target);
}
```

### Mirror to Per-Request (`token2wav-impl.cpp:81-100`)

```cpp
static void e2e_record_ns(std::atomic<int64_t>& target) {
    // ... sets global atomic ...
    target.store(ns, std::memory_order_relaxed);

    // Mirror to per-request slot via thread_local context
    const C8FlowVocoderTargets& ctx = g_c8_thread_targets;
    if (!ctx.flow_start) return;  // ← guards ALL mirroring
    
    std::atomic<int64_t>* mirror = nullptr;
    if (&target == &g_e2e_flow_start_ns)       mirror = ctx.flow_start;
    else if (&target == &g_e2e_flow_end_ns)     mirror = ctx.flow_end;
    else if (&target == &g_e2e_vocoder_start_ns) mirror = ctx.vocoder_start;
    else if (&target == &g_e2e_vocoder_end_ns)   mirror = ctx.vocoder_end;
    if (mirror) mirror->store(ns, std::memory_order_relaxed);
}
```

### Global Reset Per-Request (`omni.cpp:12986-12989`)

```cpp
g_e2e_flow_start_ns.store(0, std::memory_order_relaxed);
g_e2e_flow_end_ns.store(0, std::memory_order_relaxed);
g_e2e_vocoder_start_ns.store(0, std::memory_order_relaxed);
g_e2e_vocoder_end_ns.store(0, std::memory_order_relaxed);
```

## Semantic Analysis

### Multi-Chunk Behavior (within single request)

```
Chunk 1: once-guard(g_e2e_flow_start_ns) → global=0 → records → global=ts1
         once-guard(g_e2e_flow_end_ns)   → global=0 → records → global=ts2

Chunk 2: once-guard(g_e2e_flow_start_ns) → global=ts1≠0 → BLOCKED ✓ (first-chunk preserved)
         once-guard(g_e2e_flow_end_ns)   → global=ts2≠0 → BLOCKED ✓
```

**This is correct**: the first chunk's timestamps are recorded and subsequent chunks cannot overwrite them.

### Cross-Request Vulnerability

```
Request A, Chunk 1: records flow_start=ts1, flow_end=ts2
Request A, Chunk 2: blocked by once-guard (correct)

Main thread: resets g_e2e_flow_start_ns=0 (for request B)
Request A, Chunk 2: once-guard finds global=0 → RE-RECORDS flow_start=ts1' ← BUG!
```

If the main thread resets globals before the T2W worker finishes ALL chunks, subsequent chunks can overwrite first-chunk data.

### Missing flow_start in C9 Audio Profiles

The C9 audio profiles (22/22) are missing `flow_start` while `flow_end` is present. This indicates:
1. `g_c8_thread_targets.flow_start` was non-null (otherwise flow_end wouldn't be mirrored either)
2. But `e2e_record_ns_oneshot(g_e2e_flow_start_ns)` didn't call `e2e_record_ns()`
3. This means `g_e2e_flow_start_ns.load()` was non-zero at the time of recording

**Root cause hypothesis**: `g_e2e_flow_start_ns` was not reset to 0 between requests, so the once-guard blocked the first chunk's flow_start recording. This would happen if the main thread's reset (line 12986) raced with the T2W worker.

## Fix Requirements

### Required: Per-Request Once-Guard

The once-guard MUST check the per-request slot, not the global atomic:

```cpp
static void e2e_record_ns_oneshot(std::atomic<int64_t>& target) {
    if (!g_e2e_profile_enabled) return;
    
    // Check per-request slot first (via thread_local context)
    const C8FlowVocoderTargets& ctx = g_c8_thread_targets;
    if (ctx.flow_start) {
        std::atomic<int64_t>* mirror = nullptr;
        if (&target == &g_e2e_flow_start_ns)       mirror = ctx.flow_start;
        else if (&target == &g_e2e_flow_end_ns)     mirror = ctx.flow_end;
        else if (&target == &g_e2e_vocoder_start_ns) mirror = ctx.vocoder_start;
        else if (&target == &g_e2e_vocoder_end_ns)   mirror = ctx.vocoder_end;
        
        // Per-request once-guard: skip if already recorded for THIS request
        if (mirror && mirror->load(std::memory_order_relaxed) != 0) return;
    }
    
    // Global once-guard as fallback (for sync profile)
    if (target.load(std::memory_order_relaxed) != 0) return;
    
    e2e_record_ns(target);
}
```

### Required: Add Formal F0/F1/V0/V1/W0 Once-Guards

The formal semantic contract requires:
- `first_flow_begin` (F0): never overwritten
- `first_flow_end` (F1): never overwritten
- `first_vocoder_begin` (V0): never overwritten
- `first_vocoder_end` (V1): never overwritten
- `first_wav` (W0): already has once-guard at line 11280

### Verification After Fix

After applying the fix, verify:
1. Multi-chunk: first-chunk timestamps preserved across all chunks
2. Cross-request: per-request slots are request-scoped (no cross-contamination)
3. Sync/audio parity: sync and audio profiles agree on flow/vocoder values
4. No negative durations
