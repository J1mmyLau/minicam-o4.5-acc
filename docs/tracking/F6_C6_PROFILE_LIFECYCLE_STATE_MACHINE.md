# F6 C6: Request Profile Lifecycle State Machine

**Date:** 2026-08-01
**Source:** `tools/omni/omni.h:251-371` (E2EStageTiming)

---

## Current Architecture

### Clock

`record()` uses `std::chrono::steady_clock::now()` → **nanosecond precision**.

JSON output divides by 1'000'000 → **millisecond display**.

Raw ns data exists in-memory but is truncated at serialization.

### Generation Guard

```
active_generation_id (atomic<uint32_t>)
  ↑ bumped by reset() (release) at each request boundary
  ↑ workers snapshot via capture_generation() after their wake sync point
  ↑ record() acquires active_generation_id, compares against caller's snapshot
  ↑ mismatch → stale_write_count++ (silent rejection!)
```

### Current Issues

1. **Silent rejection** — `record()` returns false on gen mismatch but caller rarely checks. G3/G4 missing from 115/120 FP16 profiles likely due to silent rejection.

2. **tts_thread_generation / t2w_thread_generation stale** — Workers snapshot these once at wake. If `reset()` is called between worker wake and worker record(), the generation is already stale. The worker never re-snapshots.

3. **No late-write diagnostics** — `stale_write_count` and `cross_request_write_count` are global accumulators. Not per-request, not logged at request completion. The only visibility is the final JSON.

---

## State Machine (Proposed)

```
                    HTTP handler calls reset()
                    ↓
  ┌─────────────────────────────────────────┐
  │              ACTIVE                      │
  │  generation_id = N                       │
  │  All timestamps_ns[] = 0                 │
  │  Accepting: D0-D3, R0 (main thread)      │
  └────────────┬─────────────────────────────┘
               │ TTS worker wakes, snapshots gen=N
               ↓
  ┌─────────────────────────────────────────┐
  │           TALKER_STARTED                 │
  │  G0 (tts_wake) recorded                  │
  │  G1 (talker_start) recorded              │
  │  Accepting: G2, T5-T7 (TTS thread)       │
  └────────────┬─────────────────────────────┘
               │ First audio token sampled
               ↓
  ┌─────────────────────────────────────────┐
  │         FIRST_AUDIO_TOKEN                │
  │  G3 (talker_first_audio_token) recorded  │
  │  Accepting: A0-A1, G4 (accumulation)     │
  └────────────┬─────────────────────────────┘
               │ Audio token buffer >= 25
               ↓
  ┌─────────────────────────────────────────┐
  │        ACCUMULATION_COMPLETE             │
  │  A1 (accumulation_threshold) recorded    │
  │  Accepting: G4 (t2w_submit)              │
  └────────────┬─────────────────────────────┘
               │ T2WOut pushed to queue
               ↓
  ┌─────────────────────────────────────────┐
  │           T2W_SUBMITTED                  │
  │  G4 (t2w_submit) recorded                │
  │  T2W worker wakes, snapshots gen=N       │
  └────────────┬─────────────────────────────┘
               │ T2W worker dequeues
               ↓
  ┌─────────────────────────────────────────┐
  │           T2W_DEQUEUED                   │
  │  Q0 (t2w_dequeue) recorded               │
  │  Accepting: F0-F1, V0-V1, W0-W1          │
  └────────────┬─────────────────────────────┘
               │ Flow + Vocoder complete
               ↓
  ┌─────────────────────────────────────────┐
  │           FIRST_WAV                      │
  │  W0 (wav_ready) recorded                 │
  │  W1 (client_first_audio) recorded        │
  └────────────┬─────────────────────────────┘
               │ Response draining, client done
               ↓
  ┌─────────────────────────────────────────┐
  │          RESPONSE_DRAINING               │
  │  All critical stages present             │
  │  Audio profile dumped                    │
  └────────────┬─────────────────────────────┘
               │ request_done, next request
               ↓
  ┌─────────────────────────────────────────┐
  │            FINALIZED                     │
  │  Waiting for reset() at next request     │
  └────────────┬─────────────────────────────┘
               │ reset() called
               ↓
  ┌─────────────────────────────────────────┐
  │            RETIRED                       │
  │  generation_id bumped to N+1             │
  │  All timestamps_ns[] = 0                 │
  │  Ready for next request                  │
  └─────────────────────────────────────────┘
```

---

## Guards (Proposed)

| Guard | Mechanism |
|-------|-----------|
| **No new-request reset of old profile** | `active_generation_id` bump in `reset()` invalidates in-flight workers |
| **No old-worker write to new generation** | `record()` rejects `generation_id != active_generation_id` |
| **No W0 before profile finalized** | W0 write checks `active_generation_id` — if stale, write sentinel and increment `stale_write_count` |
| **No global active_generation for async events** | T2W queue item carries `request_profile_handle` (pointer/shared_ptr) |

---

## Diagnostics (Proposed)

Per-request counters (added to JSON output):

| Field | Meaning |
|-------|---------|
| `late_write_detected` | Number of `record()` calls rejected due to generation mismatch |
| `late_write_rejected` | Number of sentinel writes (-1 stored in timestamps_ns[]) |
| `late_after_finalize` | Number of writes arriving after W0 (profile already dumped) |
| `cross_request_contamination` | Number of writes from gen N-1 that landed in gen N (via globals) |
| `duplicate_stage_write` | Number of stages written more than once (once-guard already fired) |

---

## Minimum Fix for Phase 3 (C5-C6 Intersection)

### Fix 1: Worker re-snapshots generation before each record

```cpp
// In TTS worker, after wake:
uint32_t gen = ctx_omni->e2e_stage.capture_generation();
ctx_omni->e2e_stage.tts_thread_generation = gen;

// Before recording G3:
gen = ctx_omni->e2e_stage.capture_generation();  // re-snapshot!
if (!ctx_omni->e2e_stage.record(STAGE_talker_first_audio_token, gen)) {
    // Log diagnostic
}
```

### Fix 2: T2W queue item carries profile handle

```cpp
struct T2WOut {
    // ... existing fields ...
    uint32_t request_generation_id;
    int request_index;
};
```

### Fix 3: Per-request diagnostic counters

```cpp
struct E2EStageTiming {
    // ... existing fields ...
    int late_write_count_this_request = 0;    // non-atomic, reset with reset()
    int duplicate_stage_count_this_request = 0;
};
```
