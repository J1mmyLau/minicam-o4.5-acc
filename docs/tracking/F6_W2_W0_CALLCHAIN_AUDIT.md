# F6 W2: W0 Complete Call Chain Audit

**Date:** 2026-07-31
**Source:** `tools/omni/omni.cpp`, `tools/omni/omni.h`
**Method:** grep trace of all STAGE_* record() callsites, generation capture points, profile dump, and reset() calls

---

## Complete Call Chain: Talker Audio Token → WAV Ready

```
STEP  STAGE                    THREAD    GENERATION SOURCE       FILE:LINE      ASYNC?
────  ───────────────────────  ────────  ──────────────────────  ────────────   ──────
 1    tts_wake (G0)            TTS       tts_thread_generation   omni.cpp:7855  No (sync with decode)
                                                                 omni.cpp:8555
 2    tts_first_decode         TTS       tts_thread_generation   omni.cpp:3434  No
 3    talker_start             TTS       tts_thread_generation   omni.cpp:6579  No
 4    talker_first_audio_token TTS       tts_thread_generation   omni.cpp:6733  No
      (G3)
 5    t2w_submit (G4)          TTS       tts_thread_generation   omni.cpp:6979  No
      ── TTS→T2W QUEUE BOUNDARY ──
 6    t2w_dequeue              T2W       t2w_thread_generation   omni.cpp:10668 YES ⚠️
 7    talker_token_28          T2W       t2w_thread_generation   omni.cpp:10828 YES
 8    flow_start               T2W       GLOBAL ATOMIC           omni.cpp:?     YES ⚠️⚠️
 9    flow_end                 T2W       GLOBAL ATOMIC           omni.cpp:?     YES ⚠️⚠️
10    vocoder_start            T2W       GLOBAL ATOMIC           omni.cpp:?     YES ⚠️⚠️
11    vocoder_end              T2W       GLOBAL ATOMIC           omni.cpp:?     YES ⚠️⚠️
12    wav_ready (W0)           T2W       t2w_thread_generation   omni.cpp:10918 YES ⚠️⚠️⚠️
13    client_first_audio       T2W       t2w_thread_generation   omni.cpp:10925 YES ⚠️⚠️⚠️
```

## Generation Capture Points

| Variable | Captured At | Time | Thread |
|----------|------------|------|--------|
| `tts_thread_generation` | omni.cpp:7851 (simplex) / 8551 (duplex) | TTS wake (sync with decode) | TTS worker |
| `t2w_thread_generation` | omni.cpp:10663 | T2W dequeue (after cv.wait) | T2W worker |
| `active_generation_id` | Bumped by `reset()` at omni.cpp:12608 | Start of each `stream_decode` | HTTP handler |

## Profile Lifecycle (Critical Path)

```
TIME  EVENT                                    FILE:LINE       active_gen  W0 state
────  ───────────────────────────────────────  ──────────────  ──────────  ────────
T0    stream_decode() starts                   omni.cpp:12605  —           —
T0+ε  e2e_stage.reset()                        omni.cpp:12608  N           Cleared to 0
      - active_generation_id bumped (N-1 → N)
      - ALL timestamps_ns[] cleared to 0
      - Global flow/vocoder atomics cleared

T1    LLM decode → text tokens → TTS dispatch   —               N           —
T2    TTS worker: capture tts_thread_gen = N    omni.cpp:7851   N           —
T3    Talker generates audio tokens             —               N           —
T4    G3: talker_first_audio_token recorded     omni.cpp:6733   N           —
T5    Talker accumulates 25 tokens              —               N           —
T6    G4: t2w_submit → push to T2W queue       omni.cpp:6979   N           —

      ═══════════ DECOMPRESSION BOUNDARY ═══════════
      At this point: LLM is done, decode is completing
      T2W/Flow/Vocoder have NOT started yet

T7    stream_decode() returns                   omni.cpp:13345  N           —
T8    E2E profile JSON DUMPED                   omni.cpp:13355  N           = 0 ❌
      - W0 (wav_ready) = 0 → NOT in JSON
      - G4 (t2w_submit) = present → in JSON
      - request_index++

      ═══════════ NEXT REQUEST MAY START ═══════════

T9    NEXT stream_decode() starts               omni.cpp:12605  —           —
T9+ε  e2e_stage.reset() AGAIN                   omni.cpp:12608  N+1         Cleared ❌
      - G0, G3, G4 from request N are WIPED
      - Global flow/vocoder atomics cleared

      ═══════════ ASYNC PIPELINE NOW PROCEEDS ═══════════

T10   T2W worker wakes (cv.wait satisfied)      omni.cpp:10655  N+1         —
T10+ε capture t2w_thread_gen = N+1              omni.cpp:10663  N+1         —
      ⚠️ Captured N+1, but processing request N's audio!

T11   t2w_dequeue recorded (gen=N+1)            omni.cpp:10668  N+1         —
T12   Flow runs (global atomics)                —               N+1 (or N+2) —
T13   Vocoder runs (global atomics)             —               N+1 (or N+2) —
T14   WAV buffer ready                          —               N+1 (or N+2) —
T15   wav_ready recorded (gen=N+1)              omni.cpp:10918  N+1 or N+2  SET ❌

      ⚠️ THREE FAILURE MODES POSSIBLE AT T15:
      
      MODE A: active_gen == N+1 (request N+1 still active)
        → record() succeeds, but W0 from request N is written to request N+1's profile
        → Cross-request contamination (NOT caught by stale guard!)
      
      MODE B: active_gen == N+2 (request N+2 started)
        → record() rejects: generation_id (N+1) != active (N+2)
        → stale_write_count++, sentinel (-1) written
        → W0 LOST FOREVER
      
      MODE C: active_gen == N (rare: server slow, T2W fast)
        → Only happens for warmup with long drain
        → W0 correctly recorded in its own request's profile ✅

T16   NEXT request dumps JSON                   omni.cpp:13355  N+1          May contain
      → If Mode A: JSON contains W0 from wrong request              misattributed W0
      → If Mode B: JSON contains no W0 (sentinel -1, not 0)
      → If Mode C: JSON correctly contains W0 (warmup only)
```

## Root Cause: Three Design Defects

### Defect 1: Profile JSON Dumped Before Async Pipeline Completes

**Location:** `omni.cpp:13352-13355`
**Thread:** HTTP handler (synchronous)

The E2E profile JSON is written at `stream_decode()` return time. At this point:
- LLM decode is complete
- TTS/Talker may be complete (G3, G4 available)
- T2W/Flow/Vocoder have NOT started (or are still running)
- W0 is guaranteed to be 0 at dump time

**Fix:** Either defer JSON dump until W0 arrives (or timeout), or write W0 in a separate post-completion record.

### Defect 2: T2W Thread Captures Wrong Generation

**Location:** `omni.cpp:10663`
**Thread:** T2W worker

`t2w_thread_generation = capture_generation()` is called at T2W dequeue time, which is AFTER `reset()` has already bumped `active_generation_id` for the NEXT request. The T2W worker processes request N's audio but captures generation N+1.

When W0 is recorded with generation N+1:
- If request N+1 is still active → W0 misattributed to wrong request (Mode A)
- If request N+2 has started → W0 rejected as stale (Mode B)

### Defect 3: Global Flow/Vocoder Atomics Cleared Per-Request

**Location:** `omni.cpp:12611-12614`
**Thread:** HTTP handler

```cpp
g_e2e_flow_start_ns.store(0, std::memory_order_relaxed);
g_e2e_flow_end_ns.store(0, std::memory_order_relaxed);
g_e2e_vocoder_start_ns.store(0, std::memory_order_relaxed);
g_e2e_vocoder_end_ns.store(0, std::memory_order_relaxed);
```

These are GLOBAL atomics (not per-request `timestamps_ns[]`). They get cleared at every `stream_decode` start, making cross-request Flow/Vocoder timing impossible.

## Why the Warmup Worked (1/64)

The candidate warmup (e2e_0000.json) has W0 because of a special condition:

1. The warmup is the VERY FIRST request after server start
2. `omni_init` + warmup prefill/decode may block until first audio is produced
3. The 120s drain in the R3 script (`time.sleep(DRAIN_S)`) allows the async pipeline to complete
4. No subsequent request starts during the drain → `reset()` is not called → generation stays at 1
5. T2W worker dequeues while generation is still 1 → W0 recorded correctly
6. Profile JSON is dumped AFTER the 120s drain → W0 is present

For all subsequent requests (e2e_0001 through e2e_0035):
1. Decode completes quickly (no blocking on Flow+Vocoder)
2. Profile JSON dumped immediately (W0 = 0)
3. Next request's `reset()` bumps generation BEFORE T2W dequeues
4. W0 either misattributed (Mode A) or rejected (Mode B)

## Thread Ownership Summary

| Thread | Role | Key Calls |
|--------|------|-----------|
| **HTTP handler** | Request lifecycle | `reset()` (L12608), `dump_json()` (L13355) |
| **LLM decode** | Token generation | Token classify → TTS wake |
| **TTS worker** | Talker generation | G0 (L7855), G3 (L6733), G4 (L6979), `tts_thread_generation` capture (L7851) |
| **T2W worker** | Audio synthesis | Dequeue (L10663), W0 (L10918), `t2w_thread_generation` capture (L10663) |

## Stale Write Confirmation

The R3 data confirms Defect 2:
- Baseline: 33/36 profiles have stale_write_count > 0 (92%)
- Candidate: 26/28 profiles have stale_write_count > 0 (93%)
- These stale writes are TTS/T2W thread events from request N being rejected during request N+1

## Fix Priority

| Fix | Effort | Impact |
|-----|--------|--------|
| **Defer profile JSON dump** until W0 or timeout | Medium | W0 appears in its own request's profile |
| **Pass request-scoped generation to T2W queue** (not capture at dequeue) | Low | W0 attributed to correct request |
| **Convert global flow/vocoder atomics to per-stage timestamps** | Low | Flow+Vocoder timing preserved across requests |
| **Request-scoped profile handle** (shared_ptr pattern) | High | Complete lifecycle safety |

## W0 Observability Verdict

```
W0_OBSERVABILITY_ROOT_CAUSE = PROFILE_DUMP_BEFORE_ASYNC_PIPELINE_COMPLETION
  ├── PRIMARY:   JSON dumped at decode return (L13355), W0 always 0 at that time
  ├── SECONDARY: T2W captures generation at dequeue (L10663), which is already next request's gen
  ├── TERTIARY:  Global flow/vocoder atomics cleared by each reset() (L12611-12614)
  └── Only 1/64 profiles has W0 because only the warmup had drain before next reset()
```
