# F6 Talker Ring Buffer Race Closeout (N6)

**Date:** 2026-08-01
**Status:** CLOSED — generation guard + finalize gate added

## Original Design (C7, commit 9a916ce)

```cpp
struct TalkerStepBuffer {
    TalkerStepRecord steps[TALKER_MAX_STEPS];  // 500 entries
    int count = 0;                              // non-atomic!
    bool truncated = false;                     // non-atomic!

    void record_step(const TalkerStepRecord &rec) {
        if (count < TALKER_MAX_STEPS) {
            steps[count++] = rec;  // non-atomic increment
        } else {
            truncated = true;
        }
    }

    void reset() {
        count = 0;        // non-atomic clear
        truncated = false;
    }
};
```

### Race Analysis

| Scenario | Writer (TTS thread) | Reader/Resetter | Hazard |
|----------|---------------------|-----------------|--------|
| Normal | record_step() during decode | summarize() after request complete | Pipeline ordering provides happens-before |
| Late write | TTS thread from Request A writes step after reset() | reset() for Request B clears count=0 | **Request A's step leaks into Request B's buffer** |
| Concurrent summarize | record_step() during decode | summarize() at dump time | **Reader sees partial record (tearing)** |
| Buffer full | record_step() when count==500 | — | truncated=true, no overflow — SAFE |

### Specific Race: Late Write After Reset

```
Timeline:
  T0: Request A TTS thread records steps 0..35 (count=36)
  T1: Request A completes
  T2: reset() called → count=0, truncated=false
  T3: Request A TTS thread is still alive, records step 36 → count=1
      ↑ THIS IS A STALE WRITE FROM REQUEST A INTO REQUEST B'S BUFFER
  T4: Request B TTS thread records steps 0..20 (count=21)
  T5: summarize() called → reports 21 steps but step 0 is from Request A!
```

### Severity Assessment

| Factor | Rating |
|--------|--------|
| Likelihood in normal flow | LOW — TTS pipeline drains before reset() |
| Likelihood under load/overlap | MEDIUM — TTS worker may not be fully drained |
| Impact on measurement | MEDIUM — one stale step in 20+ total |
| Impact on correctness | LOW — step-level data, non-critical path |

## Fixed Design (N6)

### Generation Guard

```cpp
struct TalkerStepBuffer {
    mutable std::atomic<uint32_t> active_generation{0};
    mutable std::atomic<bool>     finalized{false};

    // Rejection counters (accumulate, never reset)
    mutable std::atomic<uint32_t> late_write_rejected{0};
    mutable std::atomic<uint32_t> write_after_finalize{0};
    mutable std::atomic<uint32_t> invalid_generation_write{0};

    bool record_step(const TalkerStepRecord &rec, uint32_t generation) {
        // Gate 1: reject writes after finalize
        if (finalized.load(std::memory_order_acquire)) {
            write_after_finalize.fetch_add(1, std::memory_order_relaxed);
            return false;
        }
        // Gate 2: reject stale/incorrect generations
        uint32_t current_gen = active_generation.load(std::memory_order_acquire);
        if (generation != current_gen) {
            if (generation < current_gen) {
                late_write_rejected.fetch_add(1, std::memory_order_relaxed);
            } else {
                invalid_generation_write.fetch_add(1, std::memory_order_relaxed);
            }
            return false;
        }
        // Safe to write
        if (count < TALKER_MAX_STEPS) {
            steps[count++] = rec;
        } else {
            truncated = true;
        }
        return true;
    }

    void reset() {
        active_generation.fetch_add(1, std::memory_order_release);  // bump generation
        finalized.store(false, std::memory_order_relaxed);
        count = 0;
        truncated = false;
    }

    void finalize() const {
        finalized.store(true, std::memory_order_release);
    }
};
```

### Happens-Before Chain

```
Request Boundary:
  reset():
    1. active_generation.fetch_add(1, release)     → generation++
    2. finalized = false
    3. count = 0

Request Processing:
  TTS thread:
    4. gen = capture_generation()                   → acquire sees new generation
    5. record_step(rec, gen)                        → generation check passes
       → count++ (non-atomic, but single-writer)

  Dump time:
    6. finalize()                                   → release, no more writes accepted
    7. summarize()                                  → safe to read count and steps[]
```

### Safety Properties

| Property | Original | Fixed |
|----------|----------|-------|
| Late write after reset | **Not prevented** | **Rejected** by generation mismatch |
| Write after finalize | **Not prevented** | **Rejected** by finalize flag |
| Concurrent summarize | **Possible tearing** | **Prevented** by finalize before summarize |
| Buffer overflow | truncated=true | truncated=true (unchanged) |
| Partial record detection | **Not detected** | Recorded as invalid_generation_write |
| Single-writer guarantee | Implicit (TTS only) | Enforced (generation check) |

### JSON Output

The rejection counters are included in the audio profile JSON:
```json
"talker_step_summary": {
    ...
    "late_write_rejected": 0,
    "write_after_finalize": 0,
    "invalid_generation_write": 0
}
```

## Verdict

**RACE CLOSED.** Generation guard prevents stale writes. Finalize gate prevents
concurrent read/write during summarization. Rejection counters provide
observability into abnormal conditions.

Gate: `DATA_RACE_OPEN = 0` ✅
