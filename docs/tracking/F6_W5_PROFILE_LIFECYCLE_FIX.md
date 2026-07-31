# F6 W5-W7: Profile Lifecycle Fix for Reliable W0 Observability

**Date:** 2026-07-31
**Status:** DESIGN → IMPLEMENTATION
**Scope:** Fix W0 attribution and profile lifecycle WITHOUT changing inference behavior

---

## Root Cause (from W2/W3)

1. **Profile JSON dumped at decode return** (L13355) — BEFORE async Flow+Vocoder completes
2. **T2W worker captures wrong generation** (L10663) — captures `active_generation_id` at dequeue time, which is already the NEXT request's generation
3. **Global flow/vocoder atomics cleared by each reset()** (L12611-12614)

## Design Constraints (from W7)

- ❌ Do NOT change model decode, FIRST_TTS_CHUNK_STEP, CHUNK_SIZE, Talker token policy, T2W algorithm, Flow/Vocoder, KV cache format
- ❌ Do NOT add stream synchronize to critical path
- ❌ Do NOT add worker join to first-audio critical path
- ❌ Do NOT add busy wait
- ❌ Do NOT add hot-path file writes (per-token/per-chunk I/O)
- ❌ Do NOT delay all request completion to mask lifecycle issues
- ✅ Profile writes are ONE per request, not per-chunk (acceptable)

---

## Fix 1: Pass generation_id Through T2W Queue

### Why

Currently, `t2w_thread_generation` is captured at T2W dequeue time (L10663), which is AFTER `reset()` has bumped `active_generation_id` for the next request. The T2W worker processes request N's audio but records events with generation N+1.

### Change

**omni.h:100 — Add field to T2WOut:**
```cpp
struct T2WOut {
    std::vector<llama_token> audio_tokens;
    bool is_final = false;
    bool is_chunk_end = false;
    int round_idx = -1;
    uint32_t generation_id = 0;  // F6 W5: generation at TTS submit time (correct attribution)
    std::chrono::steady_clock::time_point enqueue_time = std::chrono::steady_clock::now();
};
```

**omni.cpp:6965 — Set generation at push time:**
```cpp
t2w_out->generation_id = ctx_omni->e2e_stage.tts_thread_generation;
```

**omni.cpp:10663 — Use stored generation instead of capture:**
```cpp
// OLD: ctx_omni->e2e_stage.t2w_thread_generation = ctx_omni->e2e_stage.capture_generation();
// NEW: use generation from queue item (correct attribution to originating request)
uint32_t stored_gen = t2w_out->generation_id;
```

**All T2W worker record() calls (L10668, L10828, L10918, L10925):**
```cpp
// OLD: ctx_omni->e2e_stage.record(STAGE_t2w_dequeue, ctx_omni->e2e_stage.t2w_thread_generation);
// NEW: ctx_omni->e2e_stage.record(STAGE_t2w_dequeue, stored_gen);
```

### Verification
- W0 recorded with generation_id = request N's generation (not N+1)
- If request N+1 has started (reset() bumped gen to N+1), W0 record with gen=N will be rejected as stale
- BUT: the stale rejection is CORRECT — the profile for request N was already dumped at decode return
- Fix 2 below addresses this by deferring the dump

---

## Fix 2: Two-Phase Profile Dump

### Why

Profile JSON is dumped at decode return (L13355). At that point:
- Sync stages (D0, D2, G0, G3, G4) are recorded ✅
- Async stages (Q0, Flow, Vocoder, W0) are NOT yet complete ❌

### Approach

Add a profile state to `E2EStageTiming`. The profile JSON is:
- **Phase 1** (decode return): Written as `profile_status: "partial"` — contains sync stages only
- **Phase 2** (W0 arrival or timeout): Overwritten as `profile_status: "complete"` or `"terminal_missing_w0"`

### Change

**omni.h — Add to E2EStageTiming:**
```cpp
enum ProfileState : int32_t {
    PROFILE_ACTIVE = 0,           // Request in progress
    PROFILE_PARTIAL_DUMPED = 1,   // Sync stages written at decode return
    PROFILE_COMPLETE = 2,         // W0 arrived, full profile written
    PROFILE_TERMINAL_MISSING_W0 = 3,  // Timeout/error, W0 never arrived
};
std::atomic<int32_t> profile_state{PROFILE_ACTIVE};
```

**omni.cpp:13352 — Phase 1 dump (decode return):**
```cpp
if (ctx_omni->e2e_stage.enabled) {
    if (ctx_omni->e2e_stage.dump_mode == E2E_DUMP_FULL) {
        const char *profile_dir = getenv("OMNI_E2E_PROFILE_DIR");
        std::string dir = profile_dir ? profile_dir : (ctx_omni->base_output_dir + "/e2e_profile");
        // Write PARTIAL profile
        e2e_profile_dump_json(ctx_omni->e2e_stage, dir, 
            ctx_omni->use_tts ? "partial" : "complete");
        if (ctx_omni->use_tts) {
            ctx_omni->e2e_stage.profile_state.store(PROFILE_PARTIAL_DUMPED);
        } else {
            ctx_omni->e2e_stage.profile_state.store(PROFILE_COMPLETE);
        }
    } else {
        ctx_omni->e2e_stage.summary_accumulate();
    }
    ctx_omni->e2e_stage.request_index++;
}
```

**omni.cpp:10918 — Phase 2 dump (W0 arrival in T2W thread):**
```cpp
// After recording W0:
if (ctx_omni->e2e_stage.timestamps_ns[STAGE_wav_ready].load() > 0) {
    // Overwrite partial profile with complete
    if (ctx_omni->e2e_stage.dump_mode == E2E_DUMP_FULL) {
        const char *profile_dir = getenv("OMNI_E2E_PROFILE_DIR");
        std::string dir = profile_dir ? profile_dir : (ctx_omni->base_output_dir + "/e2e_profile");
        e2e_profile_dump_json(ctx_omni->e2e_stage, dir, "complete");
    }
    ctx_omni->e2e_stage.profile_state.store(PROFILE_COMPLETE);
}
```

### One Write Per Request
- Non-TTS: 1 write (complete, at decode return)
- TTS with W0: 2 writes (partial at decode return + complete at W0)
- TTS without W0: 1 write (partial at decode return; terminal status assigned by timeout cleanup or process exit)

---

## Fix 3: Flow/Vocoder → Per-Stage Timestamps (Not Global Atomics)

### Why

`g_e2e_flow_start_ns` etc. are global atomics cleared by every `reset()`. They should use the same per-stage `timestamps_ns[]` with generation guards.

### Change

The flow/vocoder stages are written by the T2W worker (or flow/vocoder worker threads). With Fix 1, the T2W worker has the correct `stored_gen`. The flow/vocoder stages should be recorded via the same `record(stage, stored_gen)` path.

**Remove global atomics** (omni.cpp:82-85, omni.h:517-520, omni.cpp:12611-12614):
```cpp
// REMOVE:
// std::atomic<int64_t> g_e2e_flow_start_ns{0};
// ...
// g_e2e_flow_start_ns.store(0, std::memory_order_relaxed);  // in reset()
```

**Replace with per-stage record() calls** in the flow/vocoder thread:
```cpp
// Instead of: g_e2e_flow_start_ns.store(now, ...);
// Use:       ctx_omni->e2e_stage.record(STAGE_flow_start, stored_gen);
```

**Update dump_json to read from timestamps_ns[]** for flow/vocoder stages instead of global atomics.

### Alternative (if flow/vocoder are in separate threads without access to stored_gen):
Store `stored_gen` in a shared location accessible to flow/vocoder threads (e.g., in the T2W queue item, passed through the pipeline context).

---

## W6: Profile Finalization State Machine

```
                          ┌─────────────────────┐
                          │   PROFILE_ACTIVE     │
                          │   (request start)    │
                          └─────────┬───────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
          ┌─────────────────┐             ┌─────────────────┐
          │  TTS request    │             │  Non-TTS req    │
          │  (use_tts=true) │             │  (use_tts=false)│
          └────────┬────────┘             └────────┬────────┘
                   │                               │
                   ▼                               │
          ┌─────────────────┐                      │
          │  Sync stages     │                      │
          │  D0,D2,G0,G3,G4  │                      │
          └────────┬────────┘                      │
                   │                               │
                   ▼                               ▼
          ┌─────────────────┐             ┌─────────────────┐
          │PROFILE_PARTIAL  │             │PROFILE_COMPLETE │
          │_DUMPED          │             │(dump at decode   │
          │(dump at decode  │             │ return)          │
          │ return)         │             └─────────────────┘
          └────────┬────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
        ▼                     ▼
┌───────────────┐    ┌────────────────────┐
│ W0 arrives    │    │ Timeout / Error    │
│ (T2W thread)  │    │ (no W0 after N s)  │
└───────┬───────┘    └─────────┬──────────┘
        │                      │
        ▼                      ▼
┌───────────────┐    ┌────────────────────┐
│PROFILE_COMPLETE│   │PROFILE_TERMINAL    │
│(overwrite JSON)│   │_MISSING_W0         │
└───────────────┘   │(write final JSON)   │
                    └────────────────────┘
```

### States

| State | Meaning | JSON status field | Who transitions |
|-------|---------|-------------------|-----------------|
| PROFILE_ACTIVE | Request in progress | — | HTTP handler (at reset) |
| PROFILE_PARTIAL_DUMPED | Sync stages written, waiting for W0 | `"partial"` | HTTP handler (at decode return) |
| PROFILE_COMPLETE | All stages including W0 written | `"complete"` | T2W worker (at W0) or HTTP handler (non-TTS) |
| PROFILE_TERMINAL_MISSING_W0 | W0 never arrived | `"terminal_missing_w0"` | Cleanup/timeout handler |

---

## Implementation Order

1. **Fix 1** first: Add `generation_id` to T2WOut, set at push, use at dequeue (omni.h + omni.cpp)
   - Smallest change, most critical impact
   - Stops the cross-request attribution bug
   
2. **Fix 3** second: Move flow/vocoder to per-stage timestamps
   - Removes global atomics cleared by reset()
   - Enables complete pipeline timing in profile
   
3. **Fix 2** third: Two-phase profile dump
   - Requires Fix 1 + Fix 3 for correctness
   - Adds profile state tracking
   - Achieves W0 in final profile JSON

---

## Regression Check: No Inference Impact

All changes are in profiling/timing code paths only:
- `T2WOut` struct gets one new field (no change to audio processing)
- `record()` calls use a different generation source (same function, different argument)
- JSON dump may write twice instead of once (I/O only, no computation change)
- `profile_state` is a new atomic field (no impact on hot path)

No change to:
- Model decode loop
- TTS/talker generation
- T2W/Flow/Vocoder computation
- Token classification
- KV cache
- Audio format/output
