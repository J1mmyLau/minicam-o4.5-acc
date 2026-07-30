# F6 S8: Stage Gap Analysis — Truly Missing Stages

**Status:** COMPLETE
**Created:** 2026-07-30

---

## Executive Summary

Of the 14 neutral events in the V2 contract, **4 are truly missing** (no existing instrumentation at all), **6 have broken guards** (instrumentation exists but once-lifetime pattern breaks multi-request correctness), and **4 are correct**.

---

## Gap Classification

### Category A: MISSING (no instrumentation whatsoever)

| Event | Location | What to instrument | Priority |
|-------|----------|-------------------|----------|
| **D0** (decode_loop_begin) | Line 12581-12584 | Pipeline trace PE_DECODE_BEGIN exists; add E2E stage record | CRITICAL — F6 T0 anchor |
| **D1** (llm_first_decode_step) | Line 12755 | First `llama_loop_with_hidden_and_token()` call in decode loop | HIGH — needed for decode step latency |
| **G0** (tts_wake) | Line 7770-7774 | TTS thread `cv.wait()` returns | HIGH — needed for scheduling wait measurement |
| **G2** (tts_first_decode) | Line 3387 | First `llama_decode()` for TTS model in `prefill_with_emb_tts()` | HIGH — needed for TTS compute measurement |

### Category B: EXISTING BUT BROKEN GUARD (once-lifetime)

| Event | Existing Stage | Fix | Priority |
|-------|---------------|-----|----------|
| **G1** (tts_chunk_start) | STAGE_talker_start (line 6515) | Change `load==0` guard to per-request bool, or add reset() | MEDIUM |
| **G3** (tts_first_audio_token) | STAGE_talker_first_audio_token (line 6669) | Same fix | MEDIUM |
| **G4** (tts_token_28) | STAGE_talker_token_28 (line 10744) | Same fix | LOW |
| **G5** (tts_submit_to_t2w) | STAGE_t2w_submit (line 6915) | Same fix | MEDIUM |
| **Q0** (t2w_dequeue) | STAGE_t2w_dequeue (line 10584) | Same fix | MEDIUM |
| **W0** (wav_ready) | STAGE_wav_ready (line 10834) | Same fix | MEDIUM |

### Category C: CORRECT (no fix needed)

| Event | Existing Stage | Guard |
|-------|---------------|-------|
| **R0** (request_enter_decode) | STAGE_request_received (line 12508) | None — overwrites each request (correct for per-request t0) |
| **D2** (llm_first_token) | STAGE_llm_first_token (line 12803) | Local `llm_first_token_logged` bool (per-request correct) |
| **D3** (llm_first_speak_token) | STAGE_speak_token (line 12815) | NONE (needs once-guard, see below) |
| **W1** (client_first_audio) | STAGE_client_first_audio (line 10841) | `wav_idx == 0` condition (per-request correct) |

### Category D: CORRECT BUT NO GUARD (overwrites)

| Event | Existing Stage | Issue |
|-------|---------------|-------|
| **D3** (llm_first_speak_token) | STAGE_speak_token (line 12815) | No once-guard — fires on every SPEAK token. Only last value survives JSON dump. Correct for single-SPEAK-token requests; wrong for multi-SPEAK. Add `llm_first_speak_token_logged` bool. |

---

## Priority for F6 Instrumentation (S9)

### Critical Path (must add for F6 T0→T6 measurement)

```
D0  decode_loop_begin           ← F6 T0 anchor (currently PE_DECODE_BEGIN pipeline trace only)
D1  llm_first_decode_step       ← Needed for decode step latency
D2  llm_first_token             ← EXISTS (STAGE_llm_first_token)
D3  llm_first_speak_token       ← EXISTS (STAGE_speak_token) — add once-guard

G0  tts_wake                    ← Needed for scheduling wait (D3→G0)
G1  tts_chunk_start             ← EXISTS (STAGE_talker_start) — fix guard
G2  tts_first_decode            ← Needed for TTS compute (G1→G2)
G3  tts_first_audio_token       ← EXISTS (STAGE_talker_first_audio_token) — fix guard

G5  tts_submit_to_t2w           ← EXISTS (STAGE_t2w_submit) — fix guard
Q0  t2w_dequeue                 ← EXISTS (STAGE_t2w_dequeue) — fix guard
W0  wav_ready                   ← EXISTS (STAGE_wav_ready) — fix guard
W1  client_first_audio          ← EXISTS (STAGE_client_first_audio) — correct
```

### Secondary Path (nice to have)

```
P0  prefill_submit              ← For prefill/decode boundary measurement
P1  prefill_complete            ← For dynamic prefill latency
G4  tts_token_28                ← For token accumulation measurement
```

---

## Instrumentation Fix Strategy

### Option 1: Add reset() method (recommended)

```cpp
// In omni.h, add to E2EStageTiming:
void reset() {
    for (int i = 0; i < STAGE_COUNT; i++) {
        timestamps_ns[i].store(0, std::memory_order_relaxed);
    }
    talker_token_count = 0;
    no_speech = false;
    cannerror = 0;
    crash = 0;
}
```

Called at line 12508 (in stream_decode, alongside the existing flow/vocoder global reset):

```cpp
ctx_omni->e2e_stage.reset();  // ADD THIS
ctx_omni->e2e_stage.record(STAGE_request_received);
```

This makes all existing `load==0` once-guards correct for per-request semantics.

### Option 2: Add per-request bool guards (more surgical)

For each broken-guard stage, add a local bool (like `llm_first_token_logged`). This is more robust against future refactoring but more code.

### Recommendation: Option 1 + Option 2 for D3

Use `reset()` to fix the 6 broken-guard stages (G1, G3, G4, G5, Q0, W0). Add a local `speak_token_logged` bool for D3 (like D2's pattern).

---

## F6 Minimal Viable Instrumentation (S9 target)

For the F6 mission (LLM Decode → First Speak Token optimization), the minimal set of events needed:

```
D0 → D2 → D3 → G0 → G1 → G2 → G3 → G5 → Q0 → W0
```

This requires:
- **4 new events**: D0, D1, G0, G2
- **5 guard fixes**: G1, G3, G5, Q0, W0 (via reset())
- **1 guard addition**: D3 (add `speak_token_logged` bool)

Plus the E2EStage enum expansion from 16 to 20 (or 18 if we skip P0/P1).

---

## Staging Plan

### S9: Implement instrumentation
1. Add `reset()` method to E2EStageTiming
2. Call `reset()` at request boundary (line 12508)
3. Add 4 new enum values + record callsites
4. Add D3 once-guard
5. Bump STAGE_COUNT
6. Update stage_name() switch

### S10: Correctness smoke test
- Single request: verify all 13 events fire with correct ordering
- Multiple requests: verify events fire per-request (not just first)
- Verify no negative intervals

### S11: Overhead gate
- 10 matched pairs with instrumentation ON vs OFF
- Gate: median D0→W0 change ≤ 1%

### S12: Final status
- F6_1_TIMING_EVENT_SEMANTICS = PASS
- F6_2_INSTRUMENTATION = PASS
