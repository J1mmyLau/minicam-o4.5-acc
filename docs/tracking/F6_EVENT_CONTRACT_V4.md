# F6 Event Contract V4 — Request-Scoped Timing

**Date:** 2026-08-01
**Status:** DEFINITIVE (freezes all known events, documents gaps)
**Replaces:** `F6_TIMING_EVENT_CONTRACT_V2.md` (superseded — V2 had incorrect thread assignments and incomplete guard analysis)

---

## Clock & Resolution

| Property | Value |
|----------|-------|
| Clock source | `ggml_time_ms()` — monotonic milliseconds |
| Resolution | **Integer milliseconds** (±1ms quantization) |
| Field name | `timestamps_ns` in struct (MISLEADING — stores ms, not ns) |
| Per-request reset | `E2EStageTiming::reset()` zeroes all `timestamps_ns[]` at request boundary |

---

## Event Definitions

### Phase R: Request Lifecycle

| # | Event | Semantic | File | Line | Thread | Scope | Guard | Criticality |
|---|-------|----------|------|------|--------|-------|-------|-------------|
| **R0** | `request_received` | HTTP handler enters stream_decode() | omni.cpp | 12760 | **HTTP handler** | Request | `record_unsafe()` — no gen guard | MEDIUM |

### Phase D: Main LLM Decode (HTTP handler thread)

| # | Event | Semantic | File | Line | Thread | Scope | Guard | Criticality |
|---|-------|----------|------|------|--------|-------|-------|-------------|
| **D0** | `decode_loop_begin` | Decode loop begins after prefill complete | omni.cpp | 12838 | **HTTP handler** | Request | `record_unsafe()` — no gen guard | HIGH (T0 anchor) |
| **D1** | `llm_first_decode_step` | First autoregressive llama_decode call | omni.cpp | 13023 | **HTTP handler** | Request | `record_unsafe()` + local bool `llm_first_decode_step_logged` | HIGH |
| **D2** | `llm_first_token` | First token from LLM decode | omni.cpp | 13075 | **HTTP handler** | Request | `record_unsafe()` + local bool `llm_first_token_logged` | HIGH |
| **D3** | `speak_token` | First LLM token with type==SPEAK | omni.cpp | 13090 | **HTTP handler** | Request | `record_unsafe()` — **NO ONCE GUARD** (fires every SPEAK) | MEDIUM |

**D3 bug:** No once-guard. If LLM produces multiple SPEAK tokens, D3 is overwritten each time. Only the LAST SPEAK token timestamp survives.

### Phase G: Talker / TTS Generation (TTS thread)

| # | Event | Semantic | File | Line | Thread | Scope | Guard | Criticality |
|---|-------|----------|------|------|--------|-------|-------|-------------|
| **G0** | `tts_wake` | TTS thread wakes from cv.wait | omni.cpp | 7945, 8663 | **TTS** | Request | `record()` + `tts_thread_generation` + atomic once-guard | HIGH |
| **G1** | `talker_start` | TTS begins processing first text chunk | omni.cpp | 6652 | **TTS** | Request | `record()` + `tts_thread_generation` (once via load==0) | HIGH |
| **G2** | `tts_first_decode` | First TTS model forward pass (llama_decode) | omni.cpp | 3507 | **TTS** | Request | `record()` + `tts_thread_generation` | MEDIUM |
| **G3** | `talker_first_audio_token` | First audio token sampled from TTS output | omni.cpp | 6806 | **TTS** | Request | `record()` + `tts_thread_generation` (once via load==0) | **CRITICAL** — MISSING in FP16 profiles |
| **G4** | `t2w_submit` | T2WOut pushed to T2W queue, cv.notify_one | omni.cpp | 7054 | **TTS** | Request | `record()` + `tts_thread_generation` (once via load==0) | **CRITICAL** — MISSING in FP16 profiles |
| **G5** | `talker_token_28` | Audio token buffer reaches WINDOW_SIZE (28) | omni.cpp | 10963 | **T2W** (not TTS!) | Request | `record()` + `t2w_thread_generation` (once via load==0) | MEDIUM |

**G0 dual callsite:** Lines 7945 and 8663 both record `tts_wake`. Both guarded by same atomic CAS — first one wins. Two different wake paths (direct notify vs. timeout/fallback).

**G3/G4 MISSING from FP16 profiles:** These are recorded with `record()` using `tts_thread_generation` guard. The fact they're absent from 115/120 FP16 profiles (only 5 have G3) suggests either:
1. `tts_thread_generation` is stale at record time (generation mismatch → record rejected)
2. The load==0 once-guard already fired in a previous request and wasn't reset
3. The TTS thread code path doesn't reach these record sites in FP16+CANN config

### Phase Q: T2W Queue (T2W thread)

| # | Event | Semantic | File | Line | Thread | Scope | Guard | Criticality |
|---|-------|----------|------|------|--------|-------|-------|-------------|
| **Q0** | `t2w_dequeue` | T2W thread dequeues first T2WOut from queue | omni.cpp | 10803 | **T2W** | Request | `record()` + `t2w_thread_generation` (once via load==0) | HIGH |

### Phase F: Flow (T2W thread — GLOBAL FALLBACK)

| # | Event | Semantic | File | Line | Thread | Scope | Guard | Criticality |
|---|-------|----------|------|------|--------|-------|-------|-------------|
| **F0** | `flow_start` | Flow matching begins | omni.cpp | 82 (global) | **T2W** | **GLOBAL** (g_e2e_flow_start_ns) | NONE — process-global atomic | MEDIUM |
| **F1** | `flow_end` | Flow matching complete | omni.cpp | 83 (global) | **T2W** | **GLOBAL** (g_e2e_flow_end_ns) | NONE — process-global atomic | MEDIUM |

### Phase V: Vocoder (T2W thread — GLOBAL FALLBACK)

| # | Event | Semantic | File | Line | Thread | Scope | Guard | Criticality |
|---|-------|----------|------|------|--------|-------|-------|-------------|
| **V0** | `vocoder_start` | Vocoder begins | omni.cpp | 84 (global) | **T2W** | **GLOBAL** (g_e2e_vocoder_start_ns) | NONE — process-global atomic | MEDIUM |
| **V1** | `vocoder_end` | Vocoder complete | omni.cpp | 85 (global) | **T2W** | **GLOBAL** (g_e2e_vocoder_end_ns) | NONE — process-global atomic | MEDIUM |

### Phase W: Waveform Output (T2W thread)

| # | Event | Semantic | File | Line | Thread | Scope | Guard | Criticality |
|---|-------|----------|------|------|--------|-------|-------|-------------|
| **W0** | `wav_ready` | First WAV chunk produced (Flow+Vocoder complete) | omni.cpp | 11060 | **T2W** | Request | `record()` + `t2w_thread_generation` (once via load==0) + direct `wav_ready_ns` parameter | **CRITICAL** |
| **W1** | `client_first_audio` | First audio chunk emitted to client (wav_idx==0) | omni.cpp | 11076 | **T2W** | Request | `record()` + `t2w_thread_generation` + `wav_idx==0` | MEDIUM |

---

## Scope Classification

### Request-Scoped (via `record()` with generation_id)
```
D0, D1, D2, D3 — HTTP handler thread, record_unsafe (no gen guard, but single-request-at-a-time)
G0, G1, G2, G3, G4 — TTS thread, record() with tts_thread_generation
G5, Q0, W0, W1 — T2W thread, record() with t2w_thread_generation
```

### Process-Global Fallback (CRITICAL GAP)
```
F0 (flow_start), F1 (flow_end) — g_e2e_flow_start_ns, g_e2e_flow_end_ns
V0 (vocoder_start), V1 (vocoder_end) — g_e2e_vocoder_start_ns, g_e2e_vocoder_end_ns
```

**Risk:** These globals are reset by `reset()` at each request boundary. A late Flow/Vocoder write from request N can contaminate request N+1's profile. The `add_global_fallback()` function in the JSON writer reads these globals as a fallback when the corresponding `timestamps_ns[]` stage is 0.

**Fix required (C5):** Flow/Vocoder events must carry request-scoped profile handles through the T2W queue item, instead of using process-global atomics.

---

## Events Missing from Current FP16 Profiles

| Event | Present in 120 pairs? | Reason |
|-------|----------------------|--------|
| G3 (talker_first_audio_token) | 5/120 | `record()` rejected — `tts_thread_generation` mismatch or once-guard already set |
| G4 (t2w_submit) | 0/120 | `record()` rejected — same mechanism |
| G5 (talker_token_28) | 0/120 | `record()` rejected in T2W thread |
| D3 (speak_token) | 0/120 | No once-guard, but maybe not reached or overwritten |

**Root cause hypothesis:** `E2EStageTiming::next_generation()` is called at request start (line ~12758 in HTTP handler), bumping `active_generation_id`. But `tts_thread_generation` and `t2w_thread_generation` are loaded BEFORE the worker threads see the new generation. If the workers use stale generation_id values, their `record()` calls fail the `generation_id != active_generation_id` check and are silently dropped.

---

## Phase 3 Required New Events

### Talker Step Instrumentation (P9)

| # | Event | Semantic | Thread | Notes |
|---|-------|----------|--------|-------|
| **T5** | `talker_step_begin` | Talker decode step N begins | TTS | Per-step, recorded in ring buffer |
| **T6** | `talker_logits_ready` | Talker logits computed for step N | TTS | Per-step |
| **T7** | `talker_audio_token` | Audio token accepted at step N | TTS | First occurrence = G3 equivalent |

### Audio Token Accumulation

| # | Event | Semantic | Thread | Notes |
|---|-------|----------|--------|-------|
| **A0** | `audio_accumulation_start` | First audio token pushed to accumulation buffer | T2W | After TTS→T2W token transfer |
| **A1** | `audio_accumulation_threshold` | Buffer reaches CHUNK_SIZE=25 | T2W | Triggers T2W submit |

### T2W Fine-Grained (replacing globals)

| # | Event | Semantic | Thread | Scope | Notes |
|---|-------|----------|--------|-------|-------|
| **Q1** | `t2w_preprocess_end` | Preprocessing before Flow begins | T2W | Request | Replaces global flow_start |
| **F0'** | `flow_begin` | Flow matching begins (request-scoped) | T2W | Request | Via profile handle, not global |
| **F1'** | `flow_end` | Flow matching complete (request-scoped) | T2W | Request | Via profile handle |
| **V0'** | `vocoder_begin` | Vocoder begins (request-scoped) | T2W | Request | Via profile handle |
| **V1'** | `vocoder_end` | Vocoder complete (request-scoped) | T2W | Request | Via profile handle |

---

## Derived Metrics (V4)

```
MAIN LLM:
  D0→D1  = D1 - D0   # Decode loop entry → first decode step
  D1→D2  = D2 - D1   # First decode step latency
  D0→D2  = D2 - D0   # Decode start → first LLM token (~28ms)

TALKER SCHEDULING:
  D2→G0  = G0 - D2   # First LLM token → TTS wake (bimodal: 0ms or ~221ms)

TALKER COMPUTE (requires P9):
  G0→G1  = G1 - G0   # TTS wake → chunk processing start
  G1→G2  = G2 - G1   # Chunk start → first TTS decode
  G2→G3  = G3 - G2   # First TTS decode → first audio token
  G0→G3  = G3 - G0   # TTS wake → first audio token

AUDIO ACCUMULATION (requires P9):
  G3→A0  = A0 - G3   # First audio token → accumulation start
  A0→A1  = A1 - A0   # Accumulation → threshold reached (CHUNK_SIZE=25)
  G3→A1  = A1 - G3   # First audio token → accumulation complete

T2W QUEUE (requires P9):
  A1→Q0  = Q0 - A1   # Threshold reached → T2W dequeue
  Q0→Q1  = Q1 - Q0   # Dequeue → preprocessing complete

FLOW + VOCODER (after C5 fix):
  Q1→F0  = F0 - Q1   # Preprocessing → Flow start
  F0→F1  = F1 - F0   # Flow duration (~135ms)
  F1→V0  = V0 - F1   # Flow→Vocoder handoff
  V0→V1  = V1 - V0   # Vocoder duration (~122ms)
  V1→W0  = W0 - V1   # Vocoder→WAV packaging

CRITICAL PATH (undecomposed → fully decomposed):
  G0→W0  ≈ 890ms     # CURRENT: TTS wake → WAV ready
  G0→Q0  ≈ 621ms     # TTS wake → T2W dequeue (UNDECOMPOSED REGION)
  Q0→W0  =  267ms     # T2W dequeue → WAV ready (Flow+VPN only)
```

---

## Guardrail Summary

| Rule | Rationale |
|------|-----------|
| All critical events must be request-scoped | No global fallback for G3, G4, Q0, F0, F1, V0, V1, W0 |
| T2W queue item must carry request-scoped profile handle | Eliminate `g_e2e_flow_start_ns` globals |
| Flow/Vocoder workers write to handle, not globals | Fix cross-request contamination risk |
| Once-guards must reset per-request | `reset()` already called — verify it clears all relevant stages |
| `record()` must not silently drop on generation mismatch | Log `late_write_rejected` count for diagnostics |
| Clock resolution documented as integer ms | No false precision claims |
