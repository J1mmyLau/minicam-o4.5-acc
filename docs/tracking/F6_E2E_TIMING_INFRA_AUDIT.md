# F6 S1: E2EStageTiming Infrastructure Audit

**Status:** COMPLETE
**Created:** 2026-07-30
**Worktree:** `/workspace/llama.cpp-omni-f6`
**Source:** `tools/omni/omni.h:237-289`, `tools/omni/omni.cpp`

---

## 1. Clock Source

```
RECORDED: std::chrono::steady_clock::now().time_since_epoch()
DOCUMENTED: CLOCK_MONOTONIC_RAW
```

**Finding:** `steady_clock` is NOT guaranteed to be `CLOCK_MONOTONIC_RAW`. On Linux/glibc, `steady_clock` typically maps to `CLOCK_MONOTONIC`, not `CLOCK_MONOTONIC_RAW`. `CLOCK_MONOTONIC` is subject to NTP adjustments (slewing), while `CLOCK_MONOTONIC_RAW` is not.

**Impact for F6:** Low. On modern kernels, NTP slew rates are small (<500ppm). For sub-second latency measurements, the difference is <1µs. For statistical profiling over many requests, this is negligible.

**Recommendation:** If nanosecond accuracy matters for cross-request comparison, switch to `clock_gettime(CLOCK_MONOTONIC_RAW, &ts)` directly. Otherwise, `steady_clock` is sufficient.

---

## 2. Atomic Semantics

```cpp
std::atomic<int64_t> timestamps_ns[STAGE_COUNT] = {};
// ...
void record(E2EStage stage) {
    timestamps_ns[stage].store(now_ns, std::memory_order_relaxed);
}
```

**Findings:**
- `memory_order_relaxed` means no synchronization with other atomic operations
- Cross-thread reads via `load(relaxed)` see eventually-consistent values
- No acquire/release pairing for causal ordering between threads
- **Correct for monotonic timestamps** under the assumption that each stage is written by ONE thread and read by a DIFFERENT thread (the reporting/dump thread)

**Risk assessment:** 
- Single-writer, single-reader per stage: SAFE
- No happens-before guarantees between stages: ACCEPTABLE (timestamps are independently monotonic)
- No memory barrier between `record()` calls on different threads: ACCEPTABLE (each timestamp is independently valid)

---

## 3. Once-Guard Analysis

### record() has NO once-guard

```cpp
void record(E2EStage stage) {
    if (!enabled || stage < 0 || stage >= STAGE_COUNT) return;
    auto now = std::chrono::steady_clock::now().time_since_epoch();
    timestamps_ns[stage].store(...);  // UNCONDITIONAL overwrite
}
```

### Callsite guards are inconsistent

| Stage | Guard Pattern | Correct for Multi-Request? |
|-------|---------------|---------------------------|
| STAGE_request_received | NONE | YES (overwrites each request — intended as per-request t0) |
| STAGE_llm_first_token | local `llm_first_token_logged` bool | YES (local variable recreated per request) |
| STAGE_speak_token | NONE | NO (fires on every SPEAK token; only last value survives) |
| STAGE_talker_start | `load==0` on timestamps_ns[] | NO (no per-request reset → fires once per session lifetime) |
| STAGE_talker_first_audio_token | `load==0` on timestamps_ns[] | NO (same as above) |
| STAGE_t2w_submit | `load==0` on timestamps_ns[] | NO (same as above) |
| STAGE_t2w_dequeue | `load==0` on timestamps_ns[] | NO (same as above) |
| STAGE_talker_token_28 | `load==0` on timestamps_ns[] | NO (same as above) |
| STAGE_wav_ready | `load==0` on timestamps_ns[] | NO (same as above) |
| STAGE_client_first_audio | `wav_idx == 0` condition | YES (wav_idx resets per request) |

### Root Cause

`E2EStageTiming` has **no `reset()` method**. At the end of each request (line 13225), only `request_index++` is incremented. The `timestamps_ns[]` array is NEVER cleared.

```cpp
// Line 13225-13227 (stream_decode return path)
e2e_profile_dump_json(ctx_omni->e2e_stage, dir);
ctx_omni->e2e_stage.request_index++;  // ← Only this. No timestamp reset.
```

**Consequence:** Stages using `timestamps_ns[X].load() == 0` as a once-guard fire **only on the first request** of a session. Subsequent requests see non-zero timestamps and skip recording.

---

## 4. Missing Stages (enum values with no callsites)

6 of 16 enum values have **no instrumentation**:

| Enum Value | Enum Name | Status |
|------------|-----------|--------|
| 1 | STAGE_prompt_processing_start | NEVER RECORDED — intended but never instrumented |
| 9 | STAGE_flow_start | Uses separate `g_e2e_flow_start_ns` global — defined but NEVER written with actual timestamp |
| 10 | STAGE_flow_end | Uses separate `g_e2e_flow_end_ns` global — never written |
| 11 | STAGE_vocoder_start | Uses separate `g_e2e_vocoder_start_ns` global — never written |
| 12 | STAGE_vocoder_end | Uses separate `g_e2e_vocoder_end_ns` global — never written |
| 15 | STAGE_request_done | NEVER RECORDED — intended but never instrumented |

The flow/vocoder globals are:
- Declared: lines 82-85
- Registered in JSON dump: lines 1001-1004
- Reset to 0: lines 12510-12513
- BUT **never stored with actual timestamps** anywhere in the codebase

These are **dead stages** — defined in the enum, emitted in JSON dumps (if they had non-zero values), but never populated.

---

## 5. Cross-Request Isolation

```
STRUCT LIFECYCLE: E2EStageTiming is a member of omni_context (omni.h:670)
SESSION LIFECYCLE: omni_context lives for the duration of an HTTP session
REQUEST LIFECYCLE: Multiple requests per session → e2e_stage shared across requests
```

**No per-request isolation mechanism exists:**
- No `reset()` method on E2EStageTiming
- No request-boundary clearing of timestamps
- The `request_index` field is incremented but not used as part of any guard

**Current behavior for N requests in a session:**
- Request 1: All stages recorded (some via once-guard = correct, some via no-guard = correct)
- Request 2+: Once-guarded stages = STALE (hold request-1 values), unguarded stages = overwritten
- No mechanism to distinguish "recorded this request" from "stale from prior request"

---

## 6. PipelineEvent Ring Buffer

A separate, lower-overhead tracing system exists:

```
Ring buffer: 8192 entries × 32 bytes = 256KB
Atomic push, no lock
Events: PE_T2W_SUBMIT, PE_FIRST_AUDIO_READY, PE_FIRST_SPEAK_TOKEN,
        PE_DECODE_BEGIN, PE_FIRST_AUDIO_EMIT, etc.
Controlled by: OMNI_PIPELINE_TRACE=1 env var
```

The pipeline trace has the `PE_DECODE_BEGIN` event (line 12582) which is the exact "decode loop begins" marker — but it's not part of E2EStageTiming.

---

## 7. Summary of Infrastructure Issues

| Severity | Issue | Impact on F6 |
|----------|-------|-------------|
| CRITICAL | No per-request reset → once-guard stages broken for multi-request | Blocks multi-request profiling |
| HIGH | STAGE_request_received semantics mismatch (decode entry, not request entry) | Must rename/relocate for F6 |
| HIGH | 6 dead stages (no instrumentation) | Missing flow/vocoder/prompt/done metrics |
| MEDIUM | STAGE_speak_token has no guard → overwrites on every SPEAK token | Only last SPEAK token timestamp survives |
| MEDIUM | steady_clock ≠ MONOTONIC_RAW as documented | Sub-µs accuracy risk |
| LOW | memory_order_relaxed for cross-thread timestamps | Acceptable for monotonic nanosecond counters |
| LOW | No causal ordering guarantees between stages | Acceptable — each timestamp is independently valid |

---

## 8. Design Recommendations (for after semantic audit)

1. **Add `reset()` method** to E2EStageTiming — called at the start of each request
2. **Replace `load==0` once-guards** with proper per-request bools (or rely on reset)
3. **Instrument the 6 dead stages** or remove them from the enum
4. **Add neutral event naming** (R0, P0-P1, D0-D2, G0-G5, Q0-Q1, W0) separate from existing stages
5. **Guard STAGE_speak_token** with a once-per-request bool
