# F6 R5: Stale Write Final Values

**Date:** 2026-07-31
**Source:** `tools/omni/omni.h` (`E2EStageTiming::record()`), Z5 report, A7 v2 data

## Mechanism (recap)

```cpp
bool record(E2EStage stage, uint32_t generation_id) {
    uint32_t current_gen = active_generation_id.load(std::memory_order_acquire);
    if (generation_id != current_gen) {
        stale_write_count.fetch_add(1, std::memory_order_relaxed);
        if (generation_id < current_gen) {
            cross_request_write_count.fetch_add(1, std::memory_order_relaxed);
        }
        timestamps_ns[stage].store(-1, std::memory_order_relaxed);  // SENTINEL
        return false;  // REJECTED
    }
    // ... normal recording
}
```

## Final Values (from A7 v2 20-request gate)

| Metric | Value | Gate |
|--------|-------|------|
| `stale_write_detected_count` | 19 | DETECTED |
| `stale_write_rejected_count` | 19 | SAFE (all caught by sentinel -1) |
| `stale_write_accepted_count` | **0** | ✅ COMPLIANT |
| `cross_request_contamination_count` | **0** (19 cross-request writes — all REJECTED) | ✅ COMPLIANT |
| `profile_contamination_count` | **0** | ✅ COMPLIANT |

## Thread Attribution

| Thread | Stale Writes | Root Cause |
|--------|-------------|------------|
| LLM (HTTP handler) | **0** | Synchronous with request lifecycle |
| TTS worker | ~6 | Captures generation_id at cv.wait; may lag behind if TTS pipeline backs up |
| T2W worker | ~6 | Captures generation_id at dequeue; high-latency async processing |
| Flow+Vocoder (Python) | ~7 | External processes, global atomics, highest latency variance |

## Gate Verdict

```
STALE_WRITE_DETECTED       = 19
STALE_WRITE_REJECTED       = 19 (100% rejection rate)
STALE_WRITE_ACCEPTED       = 0
CROSS_REQUEST_CONTAMINATION = 0
PROFILE_DATA_CONTAMINATION  = 0

Gate: STALE_WRITE_GUARD_WORKING
      LIFECYCLE_ADVISORY_ONLY

No code change needed for safety.
```

## Impact on Measurement

- **D0-D2 (LLM stages)**: Always present — recorded synchronously, never stale
- **G0-G3 (TTS stages)**: Available for requests where TTS worker hasn't fallen behind
- **G4-Q0-W0 (T2W/Flow/Vocoder stages)**: Rarely available beyond gen=1 — async pipeline latency >> request rate
- **WAV monitoring (filesystem)**: Unaffected by stale writes — WAV files are written by external processes with their own lifecycle
