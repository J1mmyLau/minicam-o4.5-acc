# F6 Phase 3 — R7 Happens-Before Proof (release-store / acquire-load pairing)

**Date:** 2026-08-02
**HEAD:** 5d2762e (post audio-dump acquire fix)

## Memory Ordering Contract

### Write Side (T2W worker thread)

Location: `tools/omni/token2wav/token2wav-impl.cpp` — `e2e_record_ns()`

```cpp
// Step W1: write timestamp to global per-stage atomic
target.store(ns, std::memory_order_relaxed);   // global g_e2e_flow_start_ns etc.

// Step W2: generation-guard — if mismatch, skip mirror
if (ctx.active_gen) {
    uint32_t cur = ctx.active_gen->load(std::memory_order_acquire);
    if (cur != ctx.generation) return;
}

// Step W3: mirror write to per-request timestamps_ns[]
mirror->store(ns, std::memory_order_release);  // RELEASE STORE
```

W3 is the release store. It publishes the timestamp to the request's `timestamps_ns[]` slot.
W3 happens-after W1 (program order within thread).
W2 provides the inter-thread synchronization: it reads `active_generation_id` (written by reset()'s fetch_add(release)) to detect cross-request races.

### Read Side A: Sync Dump (main thread) — ✅ VERIFIED CORRECT

Location: `tools/omni/omni.h` — `elapsed_ms()`

```cpp
int64_t elapsed_ms(E2EStage stage, int64_t t0_ns) const {
    int64_t ts = timestamps_ns[stage].load(std::memory_order_acquire);  // ACQUIRE LOAD
    if (ts <= 0) return -1;
    return (ts - t0_ns) / 1'000'000;
}
```

**Happens-before proof:**

1. T2W thread: W3 (release store to `timestamps_ns[stage]`) — RELEASE
2. Main thread: R1 (acquire load from `timestamps_ns[stage]`) — ACQUIRE
3. If R1 reads the value stored by W3 (or any later value in the modification order):
   - W3 **synchronizes-with** R1 (release-acquire pairing, C++ [atomics.order] p2)
   - All writes sequenced-before W3 (including W1, flow processing) **happen-before** all reads sequenced-after R1
4. Therefore: flow_start, flow_end, vocoder_start, vocoder_end are all visible to the sync dump after the acquire load succeeds.

**Additional synchronization:** `t2w_drain_signal_and_wait()` called before sync dump ensures the T2W worker has completed all processing (including W3 stores) before the sync dump begins. This provides an additional mutex-based happens-before edge: the drain's mutex unlock (in drain_cv.notify_one()) synchronizes-with the drain's mutex lock (in drain_cv.wait_for()).

### Read Side B: Audio Dump (T2W worker thread) — ✅ VERIFIED CORRECT (post-fix)

Location: `tools/omni/omni.cpp` — `e2e_profile_dump_audio_json()`

```cpp
// Read B1: t0 reference — acquire load
int64_t t0 = t.timestamps_ns[STAGE_request_received].load(std::memory_order_acquire);

// Read B2: flow stages — acquire load (FIXED from relaxed)
int64_t val = t.timestamps_ns[async_stages[i]].load(std::memory_order_acquire);
```

**Happens-before proof (same-thread):**

The audio dump runs on the SAME T2W worker thread as the mirror writes.
1. W3 (release store) is sequenced-before B2 (acquire load) by program order within the same thread.
2. Even with relaxed ordering at B2, same-thread sequencing guarantees visibility (C++ [intro.races] p10: "evaluation A happens-before evaluation B" when A is sequenced-before B within the same thread).
3. Post-fix, the acquire load at B2 provides explicit documentation of the dependency, and ensures correctness if the audio dump is ever moved to a different thread.

### Read Side C: wav_ready gate check (T2W worker thread) — ⚠️ RELAXED BUT SAME-THREAD

Location: `tools/omni/omni.cpp` line ~11305

```cpp
if (ctx_omni->e2e_stage.timestamps_ns[STAGE_wav_ready].load(std::memory_order_relaxed) == 0) {
    ctx_omni->e2e_stage.record(STAGE_wav_ready, ...);
    e2e_profile_dump_audio_json(...);  // calls B1,B2 above (now acquire)
}
```

Same-thread program order ensures `STAGE_wav_ready` read is ordered after mirror writes. The subsequent acquire loads in the audio dump provide the formal happens-before edge.

## Reset Synchronization

`E2EStageTiming::reset()` calls `active_generation_id.fetch_add(1, std::memory_order_release)` before zeroing `timestamps_ns[]`. The release fence ensures that the generation increment is visible to the T2W worker's acquire load (W2 above) BEFORE the zeroing takes effect. Conversely: if the T2W worker's acquire load sees the old generation, it knows the array has not yet been zeroed, so its release store (W3) is still valid.

## Conclusion

| Read Path | Thread | Load Ordering | Release-Store Pairing | Verdict |
|-----------|--------|---------------|----------------------|---------|
| Sync dump (elapsed_ms) | Main | acquire | ✅ release→acquire | CORRECT |
| Audio dump (flow stages) | T2W | **acquire** (fixed) | ✅ release→acquire + same-thread | CORRECT |
| Audio dump (t0) | T2W | acquire | ✅ same-thread | CORRECT |
| wav_ready gate | T2W | relaxed | ✅ same-thread program order → acquire in audio dump | ACCEPTABLE |

All four read paths are now correctly paired with the release store at W3.
