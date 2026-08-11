# F6 S7: Neutral Event Contract V2

**Status:** COMPLETE
**Created:** 2026-07-30
**Replaces:** `F6_TIMING_EVENT_CONTRACT.md` (DRAFT_NEEDS_CORRECTION)

---

## Event Count

```
Total neutral events: 16

R0                                  1
P0, P1                              2
D0, D1, D2, D3                      4
G0, G1, G2, G3, G4, G5             6
Q0                                  1
W0, W1                              2
                              ----------
                               TOTAL 16
```

## Design Principles

1. **Neutral naming**: Events describe WHAT happened (hardware-observable), not WHY or WHERE
2. **Single semantic per event**: One event = one timestamp = one clear boundary
3. **Per-request correctness**: All events must fire correctly for EVERY request, not just the first
4. **Thread-tagged**: Every event belongs to exactly one thread
5. **Composable**: Downstream metrics are derived from event pairs, not embedded in events
6. **Generation-safe**: Stale worker writes from request N are rejected in request N+1

---

## Phase R: Request Lifecycle (HTTP handler thread)

| Event | Name | Thread | Location | Existing? | Semantic |
|-------|------|--------|----------|-----------|----------|
| **R0** | request_enter_decode | HTTP handler | stream_decode() entry, line 12508 | STAGE_request_received (rename) | stream_decode() function entry after HTTP parsing, session init, round sync. Prefill NOT yet awaited. |

---

## Phase P: Prefill (LLM thread)

| Event | Name | Thread | Location | Existing? | Semantic |
|-------|------|--------|----------|-----------|----------|
| **P0** | prefill_submit | HTTP handler | Line 12574-12576 (need_speek=true, cv.notify_all) | MISSING | LLM thread signaled to begin prefill |
| **P1** | prefill_complete | HTTP handler | Line 12579 (g_decode_cv.wait returns) | MISSING | Prefill finished, decode about to start |

Note: In async mode, P0→P1 includes: LLM thread wake-up + prompt eval (KV cache HIT = near-zero, MISS = ~144ms on FP16). This is the dynamic prefill window.

---

## Phase D: LLM Decode (HTTP handler thread)

| Event | Name | Thread | Location | Existing? | Semantic |
|-------|------|--------|----------|-----------|----------|
| **D0** | decode_loop_begin | HTTP handler | Line 12581-12584 | PE_DECODE_BEGIN (pipeline trace only) | Decode loop begins after prefill complete. This is the F6 T0 anchor. |
| **D1** | llm_first_decode_step | HTTP handler | Line 12755 (first llama_loop_with_hidden_and_token call) | MISSING | First LLM forward pass of the decode loop |
| **D2** | llm_first_token | HTTP handler | Line 12801-12803 | STAGE_llm_first_token | First token from LLM autoregressive decode |
| **D3** | llm_first_speak_token | HTTP handler | Line 12814-12819 | STAGE_speak_token (rename) | First LLM token with type == SPEAK |

---

## Phase G: Talker / TTS Generation (TTS thread)

| Event | Name | Thread | Location | Existing? | Semantic |
|-------|------|--------|----------|-----------|----------|
| **G0** | tts_wake | TTS thread | Line 7770-7774 (cv.wait returns) | MISSING | TTS thread wakes from cv.wait, queue has LLM tokens |
| **G1** | tts_chunk_start | TTS thread | Line 6514-6515 | STAGE_talker_start (rename, fix guard) | TTS begins processing first text chunk |
| **G2** | tts_first_decode | TTS thread | Line 3387 (llama_decode for TTS model in prefill_with_emb_tts) | MISSING | First TTS model forward pass |
| **G3** | tts_first_audio_token | TTS thread | Line 6668-6669 | STAGE_talker_first_audio_token (rename, fix guard) | First audio token sampled from TTS model output |
| **G4** | tts_token_28 | T2W thread | Line 10743-10744 | STAGE_talker_token_28 (fix guard) | Audio token buffer reaches WINDOW_SIZE (28) |
| **G5** | tts_submit_to_t2w | TTS thread | Line 6914-6915 | STAGE_t2w_submit (rename, fix guard) | T2WOut pushed to T2W queue, cv.notify_one |

Note: G4 is recorded in the T2W thread (not TTS), despite being named "talker_token_28". This is because the T2W thread receives individual audio tokens and accumulates them into a buffer. When the buffer reaches 28, the T2W thread records G4. The naming convention is corrected to reflect this.

---

## Phase Q: T2W Queue & Dispatch (T2W thread)

| Event | Name | Thread | Location | Existing? | Semantic |
|-------|------|--------|----------|-----------|----------|
| **Q0** | t2w_dequeue | T2W thread | Line 10583-10584 | STAGE_t2w_dequeue (fix guard) | T2W thread dequeues first T2WOut from queue |

---

## Phase W: Waveform Generation (T2W thread)

| Event | Name | Thread | Location | Existing? | Semantic |
|-------|------|--------|----------|-----------|----------|
| **W0** | wav_ready | T2W thread | Line 10833-10834 | STAGE_wav_ready (fix guard) | First WAV chunk produced (Flow+Voder complete) |
| **W1** | client_first_audio | T2W thread | Line 10840-10841 | STAGE_client_first_audio | First audio chunk emitted to client (wav_idx==0) |

---

## Derived Metrics (V2)

```
# LLM compute
D0_to_D2_ms   = D2 - D0    # Decode loop start → first LLM token
D0_to_D3_ms   = D3 - D0    # Decode loop start → first SPEAK token  ← PRIMARY F6 METRIC
D1_to_D2_ms   = D2 - D1    # First decode step latency

# Talker scheduling
D3_to_G0_ms   = G0 - D3    # SPEAK token → TTS thread wakes (queue dispatch + scheduling)
G0_to_G1_ms   = G1 - G0    # TTS wake → chunk processing start (preparation overhead)

# Talker compute
G1_to_G3_ms   = G3 - G1    # Chunk start → first audio token (TTS model forward pass)
G2_to_G3_ms   = G3 - G2    # TTS llama_decode → first audio token (TTS sampling)

# T2W pipeline
G3_to_G5_ms   = G5 - G3    # First audio token → submit to T2W (token accumulation to 28)
G5_to_Q0_ms   = Q0 - G5    # Submit → T2W dequeue (queue wait time)
Q0_to_W0_ms   = W0 - Q0    # Dequeue → WAV ready (Flow + Vocoder compute)
W0_to_W1_ms   = W1 - W0    # WAV ready → client emit (callback overhead)

# End-to-end critical path
D0_to_W0_ms   = W0 - D0    # Decode start → first audio ready
D0_to_W1_ms   = W1 - D0    # Decode start → first audio to client
```

---

## Comparison: Draft V1 → Corrected V2

| V1 Name | V1 Semantic | V2 Name | V2 Semantic | Change |
|---------|------------|---------|-------------|--------|
| T0 | Dynamic Prefill Complete / Decode Submitted | D0 | Decode loop begins (after prefill complete) | Relocated from line 12508 to 12581-12584 |
| T1 | First Main LLM Decode Step Starts | D1 | First autoregressive llama_decode call | Same location, renamed |
| T2 | First Main LLM Token Available | D2 | First LLM token from decode | Same location, renamed |
| T3 | Talker Becomes Eligible / Is Scheduled | G0 + G1 | TTS thread wake + chunk processing start | Split: T3 was one event, actually two |
| T4 | Talker First Decode Step Starts | G2 | First TTS llama_decode call | Same location, renamed |
| T5 | First Speak Token Logits Ready | G3 | First TTS audio token sampled | Renamed — "speak token logits" was ambiguous |
| T6 | First Valid Speak Token Accepted | D3 | First LLM token with type==SPEAK | Relocated — T6 was in TTS thread, actually in HTTP handler |
| T7 | (merged into T8 in V1) | G5 | T2WOut pushed to T2W queue | Restored — was incorrectly merged into T8 |
| T8 | T2W Worker Receives First Token | Q0 | T2W dequeues first token | Same location, renamed |
| T9 | First Audio Chunk Ready | W0 | First WAV chunk produced | Same location, renamed |
| — | (missing in V1) | W1 | First audio to client | New — was conflated with W0 |

---

## New Stages Required (compared to existing enum)

```
ADD to E2EStage enum (omni.h:217-235):
  STAGE_decode_loop_begin         // D0 — new, after prefill complete
  STAGE_llm_first_decode_step     // D1 — new, first llama_decode call
  STAGE_tts_wake                  // G0 — new, TTS thread cv.wait return
  STAGE_tts_first_decode          // G2 — new, first TTS llama_decode

RENAME existing (optional, for clarity):
  STAGE_request_received      →  (keep as R0, or repurpose as D0)
  STAGE_llm_first_token       →  STAGE_decode_first_token (D2)
  STAGE_speak_token           →  STAGE_decode_speak_token (D3)
  STAGE_talker_start          →  STAGE_tts_chunk_start (G1)
  STAGE_talker_first_audio_token → STAGE_tts_first_audio_token (G3)
  STAGE_t2w_submit            →  STAGE_tts_submit_to_t2w (G5)
  STAGE_t2w_dequeue           →  STAGE_t2w_dequeue (Q0 — keep name)

STAGE_COUNT: 16 → 20 (add 4 new stages)

REMOVE dead enum values (or instrument them):
  STAGE_prompt_processing_start (1) — remove or instrument
  STAGE_flow_start (9) — instrument via globals or remove
  STAGE_flow_end (10) — instrument via globals or remove
  STAGE_vocoder_start (11) — instrument via globals or remove
  STAGE_vocoder_end (12) — instrument via globals or remove
  STAGE_request_done (15) — remove or instrument
```

---

## Guard Fixes Required

| Event | Current Guard | Required Guard |
|-------|--------------|----------------|
| D0 | N/A (new) | Once per request (or overwrite — it's per-request t0) |
| D1 | N/A (new) | Once per request (local bool) |
| D2 | local llm_first_token_logged | OK as-is |
| D3 | NONE (fires every SPEAK) | Once per request (local bool, first SPEAK only) |
| G0 | N/A (new) | Once per request |
| G1 | load==0 (lifetime) | Once per request (or rely on reset) |
| G2 | N/A (new) | Once per request |
| G3 | load==0 (lifetime) | Once per request |
| G4 | load==0 (lifetime) | Once per request |
| G5 | load==0 (lifetime) | Once per request |
| Q0 | load==0 (lifetime) | Once per request |
| W0 | load==0 (lifetime) | Once per request |
| W1 | wav_idx==0 | OK as-is |

**Fix approach**: Add `E2EStageTiming::reset()` method, call at start of each request (line 12508, alongside request_index increment logic). Then all `load==0` guards become correct per-request once-guards.

---

## Validation Checklist

- [ ] D0 occurs AFTER prefill complete (P1)
- [ ] D1 ≤ D2 ≤ D3 (monotonic in HTTP handler thread)
- [ ] D3 occurs BEFORE G0 (SPEAK token before TTS wakes)
- [ ] G0 ≤ G1 ≤ G2 ≤ G3 (monotonic in TTS thread)
- [ ] G3 occurs BEFORE G5 (audio token before queue submit)
- [ ] G5 occurs BEFORE Q0 (submit before dequeue)
- [ ] Q0 occurs BEFORE W0 (dequeue before WAV ready)
- [ ] W0 occurs BEFORE W1 (WAV ready before client emit)
- [ ] All timestamps monotonic per-request
- [ ] No negative intervals
- [ ] reset() called at request boundary
- [ ] All events fire correctly for requests 2, 3, ... N in a session
