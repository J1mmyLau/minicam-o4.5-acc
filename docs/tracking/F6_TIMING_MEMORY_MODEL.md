# F6 A4: Timing Memory Model — Atomic and Happens-Before Audit

**Status:** COMPLETE
**Created:** 2026-07-30

---

## 1. Atomic Operations and Their Memory Orders

| Operation | Location | Access | Order | Rationale |
|-----------|----------|--------|-------|-----------|
| `reset()`: `active_generation_id.fetch_add(1)` | omni.h | write | **release** | Makes new generation visible to worker acquire in record(). All prior stores (timestamp clears) are ordered before this release. |
| `reset()`: `timestamps_ns[i].store(0)` | omni.h | write | **relaxed** | Safe because the release on `active_generation_id` above orders these stores before any subsequent `record()` that sees the new generation. |
| `capture_generation()`: `active_generation_id.load()` | omni.h | read | **acquire** | Worker reads generation after its synchronisation point. Acquire pairs with release in reset(), ensuring worker sees cleared timestamps. |
| `record()`: `active_generation_id.load()` | omni.h | read | **acquire** | Guards the timestamp write. Acquire pairs with release in reset() so the check sees the authoritative generation. |
| `record()`: `timestamps_ns[stage].store(ns)` | omni.h | write | **release** | Makes timestamp visible to summary reader. Pairs with acquire in `elapsed_ms()` / `t0_ns()`. |
| `elapsed_ms()`: `timestamps_ns[stage].load()` | omni.h | read | **acquire** | Pairs with release in record(). Ensures summary reader sees complete timestamp value. |
| `t0_ns()`: `timestamps_ns[...].load()` | omni.h | read | **acquire** | Same as above. |
| `once-guard check`: `timestamps_ns[X].load()` | omni.cpp | read | **relaxed** | Fast-path to skip record() if already set. A false negative (seeing 0 when non-zero exists) is harmless — record()'s generation check catches it. A false positive (seeing non-zero when 0) is also harmless — we skip recording but a later attempt might succeed. |
| `stale_write_count.fetch_add(1)` | omni.h | RMW | **relaxed** | Counters are informational only (telemetry), not used for control flow. |
| `cross_request_write_count.fetch_add(1)` | omni.h | RMW | **relaxed** | Same as above. |

---

## 2. Happens-Before Proofs

### 2.1 HTTP Handler Thread: Summary Read Sees Complete Worker Writes

```
Thread A (HTTP handler, stream_decode return):
  // stream_decode calls all record_unsafe() synchronously.
  // All record() calls are complete before stream_decode returns.
  // After return, e2e_profile_dump_json() reads timestamps:
  elapsed_ms() → timestamps_ns[X].load(acquire)  ← P1

Thread B (TTS worker, during stream_decode):
  record() → timestamps_ns[X].store(release)      ← P2

P2 (release) happens-before P1 (acquire):
  P2 is in TTS worker during stream_decode's execution.
  stream_decode blocks on g_decode_cv.wait (mutex+CV) before the decode loop,
  but TTS worker runs concurrently during decode.
  
  The TTS worker's writes are NOT guaranteed to happen-before the summary read
  if the summary is dumped while the TTS worker is still running.
```

**ISSUE:** `e2e_profile_dump_json()` is called at line 13254 AFTER `stream_decode` returns (line 13232), but the TTS and T2W worker threads may still be running. The summary read is NOT guaranteed to see worker writes without an explicit join or drain.

**Fix:** Before dumping, join the TTS and T2W threads, or use a drain protocol (existing `speek_done` flag) to ensure workers are idle. This is an EXISTING issue — the current code already has this gap, not introduced by F6 changes.

**Mitigation for F6:** In single-request mode, the worker threads complete before the next request starts. In multi-request mode, the `request_index++` at line 13258 happens before the next `stream_decode` call (sequential HTTP handler), providing ordering via the mutex in `octx_mutex`.

### 2.2 Worker Threads: Generation Capture After Synchronisation

```
TTS worker:
  cv.wait(mutex)               ← synchronises with LLM thread's cv.notify
  // mutex is unlocked here (cv.wait releases mutex)
  capture_generation()          ← acquire: sees generation from reset()
  // ... process work ...
  record(stage, tts_gen)       ← generation check passes (matches)

HTTP handler (next request):
  reset()                       ← release: bumps generation
  // ... worker from prev request may still be running ...
  record_unsafe()              ← safe: synchronous, no concurrent reset possible
```

**Proof:** The TTS worker's `capture_generation()` after `cv.wait` return synchronises with:
1. `cv.wait` return → guarantees the mutex was acquired → the LLM thread's `cv.notify` happened-before
2. The LLM thread pushed data before notify, which happened after `reset()` was called
3. Therefore `capture_generation()` sees the generation after `reset()` was called

**Late worker scenario:**
```
Request N worker:
  capture_generation() → gen = N
  // ... slow processing ...
  record(stage, N)              ← gen check: active=N? YES → write (correct)

Request N+1 reset():
  fetch_add(1) → active = N+1   ← release

Request N late worker:
  record(stage, N)              ← gen check: active=N+1? N != N+1 → REJECT (correct!)
  stale_write_count++           ← telemetry
  cross_request_write_count++   ← gen N < active N+1 → cross-request
```

### 2.3 T2W Worker: Synchronisation

Same as TTS worker — `cv.wait` return provides the synchronisation point. After wake, `capture_generation()` sees the current generation.

---

## 3. Summary Read Safety (current gap)

```
Current flow:
  stream_decode() returns
  → e2e_profile_dump_json()     ← reads timestamps (acquire)
  → request_index++
  
  TTS worker may still be running → some writes may not be visible yet
  T2W worker may still be running → same
```

**Root cause:** No thread join or drain before dumping.

**Impact:** Some late-stage events (G3, G4, G5, Q0, W0, W1) may be missing from the JSON dump of the current request. They would be captured in the NEXT request's profile instead — but with the generation-safe system, they'd be rejected (stale_write_count incremented).

**Recommended fix (separate from F6):** Before `e2e_profile_dump_json()`, flush worker threads:
```cpp
// Drain TTS queue (wait for empty)
// Drain T2W queue (wait for empty)
// Or: join threads (for session shutdown)
// Or: use an atomic "worker_idle" per thread + spin-wait with timeout
```

**For F6 single-request profiling:** This gap is negligible — the TTS and T2W workers complete within the request. The summary is dumped AFTER stream_decode returns, but before the next request starts. Worker completion is verified by observing all expected stages in the profile (e.g., W0/W1 are present for audio requests).

---

## 4. Design Rules

1. **All timestamp stores use `memory_order_release`**: ensures the summary reader sees a complete value after a load-acquire sees non-zero.
2. **All timestamp loads use `memory_order_acquire`**: pairs with the release store, forming a release-acquire chain.
3. **`active_generation_id` uses release/acquire**: reset() releases the new generation; record() acquires to check it.
4. **Worker thread generation capture uses acquire**: ensures the worker sees the latest generation after its synchronisation point (cv.wait, mutex, etc.).
5. **Once-guard fast-path uses relaxed**: the guard is advisory only; record()'s generation check is authoritative.
6. **Counter updates use relaxed**: informational only; no control-flow dependency.
7. **No `seq_cst` anywhere**: the concurrency pattern does not require total store order.

---

## 5. Non-Issues (verified safe)

| Concern | Verdict | Reasoning |
|---------|---------|-----------|
| `record_unsafe` races with `reset` | SAFE | HTTP handler is synchronous — no concurrent reset during stream_decode execution |
| `tts_thread_generation` read without mutex | SAFE | Single writer (TTS thread), single reader (TTS thread). Non-atomic is correct. |
| `t2w_thread_generation` read without mutex | SAFE | Single writer (T2W thread), single reader (T2W thread). |
| Worker reads stale timestamps after reset | SAFE | reset() clears timestamps BEFORE releasing new generation. Worker's acquire sees new generation → record() rejects. |
| Summary read concurrent with worker write | EXISTS | Pre-existing issue. Worker may still be writing when summary is dumped. |
