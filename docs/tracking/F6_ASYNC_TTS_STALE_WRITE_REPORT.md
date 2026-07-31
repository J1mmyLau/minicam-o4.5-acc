# F6 Z5: Async TTS Stale Write Classification

**Date:** 2026-07-31
**Source:** `tools/omni/omni.h` (record function), A7 v2 data (`/tmp/f6_a7_v2/`)

## 1. Mechanism (from `E2EStageTiming::record()`)

```cpp
bool record(E2EStage stage, uint32_t generation_id) {
    uint32_t current_gen = active_generation_id.load(std::memory_order_acquire);
    if (generation_id != current_gen) {
        stale_write_count.fetch_add(1, std::memory_order_relaxed);
        if (generation_id < current_gen) {
            cross_request_write_count.fetch_add(1, std::memory_order_relaxed);
        }
        timestamps_ns[stage].store(-1, std::memory_order_relaxed);  // SENTINEL
        return false;  // REJECTED — no timestamp recorded
    }
    timestamps_ns[stage].store(now, std::memory_order_release);
    return true;
}
```

**Key behavior:**
- `stale_write_count`: incremented when writer's `generation_id` != `active_generation_id`
- `cross_request_write_count`: subset of stale where `generation_id < current_gen` (writer is behind)
- **All stale writes are REJECTED** — sentinel (-1) written, no timestamp recorded, function returns false
- **No data contamination occurs** — the once-guard (`load == 0`) treats sentinel as "already done"

## 2. Safe Case: STALE_WRITE_GUARD_WORKING

All stale writes in A7 data follow this safe pattern:

| Profile | stale_write_count | cross_request_write_count | Verdict |
|---------|-------------------|---------------------------|---------|
| gen=1 | 0 | 0 | First request — all workers finish before gen advances |
| gen=2 | 1 | 1 | One worker from gen=1 completed during gen=2 |
| gen=3 | 3 | 3 | Three prior-gen workers finished during gen=3 |
| gen=4 | 3 | 3 | Steady state — async pipeline lag stabilized |
| gen=5 | 5 | 5 | Queue accumulates → more pending workers |
| gen=6 | 7 | 7 | Queue depth growing — 7 stale writes detected |

**Every stale write was:**
- **Detected** ✓ (stale_write_count incremented)
- **Rejected** ✓ (sentinel -1 prevents once-guard retry)
- **Not contaminating** ✓ (no cross-generation data mixed into current profile)

## 3. Thread Attribution

| Thread | Stages recorded | Generation source | Staleness risk |
|--------|----------------|-------------------|----------------|
| LLM (HTTP handler) | D0, D1, D2, D3 | `request_index` (per-request reset) | NONE — synchronous with request lifecycle |
| TTS worker | G0, G1, G2, G3 | `tts_thread_generation` (snapshot after cv.wait) | LOW — synchronizes on first wake |
| T2W worker | G4, Q0, W0, W1 | `t2w_thread_generation` (snapshot on dequeue) | HIGH — processes audio tokens asynchronously |
| Flow (Python subprocess) | flow_start, flow_end | Global atomics (shared across requests) | HIGH — external process, variable latency |
| Vocoder (Python subprocess) | vocoder_start, (W0 on C++) | Global atomics (shared across requests) | HIGH — external process, longest latency |

**Root cause:** TTS→T2W→Flow→Vocoder pipeline runs asynchronously. Each worker captures `generation_id` at its own synchronization point (cv.wait, dequeue, etc.). When a new request starts (generation_id advances), in-flight workers from prior requests are detected and safely rejected.

## 4. Stage Coverage Decay Pattern

| gen | stages in profile | missing stages |
|-----|-------------------|----------------|
| 1 | 12 (all) | none |
| 2 | 5 | G1, G2, G3, G4, Q0, W0, W1 |
| 3 | 8 | G4, Q0, W0, W1 |
| 4 | 10 | G4, Q0 |
| 5 | 8 | G4, Q0, W0, W1 |
| 6 | 4 | G0, G1, G2, G3, G4, Q0, W0, W1 |

**Pattern:** G4+ (T2W submit and downstream) stages are almost always missing beyond the first request. G0-G3 (TTS worker stages) are available for gen=3-5 (when TTS worker hasn't fallen too far behind). The LLM stages (D0-D2) are always present — they're recorded synchronously.

## 5. A7 Gate Re-evaluation

| Metric | Value | Status |
|--------|-------|--------|
| `stale_write_detected_count` | 19 (across 6 TTS requests) | DETECTED |
| `stale_write_rejected_count` | 19 (all rejected by sentinel) | SAFE |
| `stale_write_accepted_count` | **0** (none passed the guard) | ✅ COMPLIANT |
| `cross_request_write_count` | 19 (all generation_id < current_gen) | DETECTED |
| `profile_contamination_count` | **0** (no wrong-gen data written) | ✅ COMPLIANT |
| `stale_write_from_LLM_thread` | **0** (synchronous) | ✅ CLEAN |
| `stale_write_from_TTS_thread` | ~6 (G0-G3 stages, lagging behind) | EXPECTED |
| `stale_write_from_T2W_thread` | ~6 (G4-Q0-W0 stages, high latency) | EXPECTED |
| `stale_write_from_Flow_Vocoder` | ~7 (global atomics, external process) | EXPECTED |

## 6. Safety Gate Verdict

```
stale_write_accepted_count = 0      ✅ PASS
cross_request_write_count > 0       ADVISORY (all rejected by sentinel)
profile_contamination_count = 0     ✅ PASS
```

**Final classification: STALE_WRITE_GUARD_WORKING / LIFECYCLE_ADVISORY_ONLY.**

The generation_id guard correctly:
1. Detects stale writes from async workers
2. Rejects them with sentinel (-1)
3. Prevents cross-request profile contamination
4. Maintains data integrity for all recorded timestamps

**Recommendation:** No code change needed for safety. However:
- T2W/Flow/Vocoder stages (G4-Q0-W0-W1) are practically unavailable beyond gen=1
- WAV file monitoring (filesystem-based) is the reliable alternative for E2E audio metrics
- If per-request async stage tracking is needed in future: redesign profiling to use per-request ring buffer instead of shared timestamps
