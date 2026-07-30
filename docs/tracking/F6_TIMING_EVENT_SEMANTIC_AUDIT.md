# F6 S3-S6: Timing Event Semantic Audit

**Status:** COMPLETE
**Created:** 2026-07-30
**Worktree:** `/workspace/llama.cpp-omni-f6`

---

## S3: T0 Correction — What STAGE_request_received Actually Records

### Location
```
FILE:  tools/omni/omni.cpp:12508
FN:    stream_decode()
CONTEXT: Top of stream_decode, AFTER HTTP parsing + session init, BEFORE prefill wait
```

### Actual sequence at callsite

```
Line 12507: ctx_omni->stream_decode_start_time = high_resolution_clock::now();
Line 12508: ctx_omni->e2e_stage.record(STAGE_request_received);     ← T0 IN DRAFT
Line 12509-12513: Reset flow/vocoder globals to 0
Line 12515-12517: Diagnostic log
Line 12556-12572: Start TTS/T2W threads (if not running)
Line 12574: ctx_omni->need_speek = true;
Line 12576: cv.notify_all();                  ← Signals LLM thread
Line 12577: print("wait prefill done");
Line 12579: g_decode_cv.wait(... prefill_done);  ← WAITS for prefill
Line 12581-12584: PE_DECODE_BEGIN             ← DECODE LOOP ACTUALLY STARTS HERE
Line 12702: for (int il = 0; il < max_tgt_len; )  ← LLM decode loop
```

### What STAGE_request_received DOES NOT include

STAGE_request_received is recorded BEFORE:
- The LLM thread is signaled (line 12574-12576)
- The prefill completes (line 12579)
- The decode loop begins (line 12581 / 12702)

### What STAGE_request_received DOES include

STAGE_request_received is recorded AFTER (in the server HTTP flow):
- HTTP request parsing (server-omni.cpp:264-275)
- Session context lock acquisition
- stream_decode() argument unpacking
- Round index synchronization (lines 12487-12494)

### What STAGE_request_received measures in the prefill-to-decode gap

In async mode:
1. `/v1/stream/prefill` calls `stream_prefill()` — this starts the prefill on the LLM thread
2. `/v1/stream/decode` calls `stream_decode()` — this records STAGE_request_received, then waits for prefill

The gap between `/v1/stream/prefill` completing and `/v1/stream/decode` starting is NOT captured by any E2E stage. This gap includes the HTTP client round-trip between the two API calls.

### Verdict

**STAGE_request_received is NOT "dynamic prefill complete / decode submitted."**

It is "stream_decode entry point" — the moment the server begins decode-phase processing. It is:

- **AFTER**: HTTP request parsing, session lookup, stream_decode argument parsing
- **BEFORE**: Prefill completion wait, decode loop start
- **EXCLUDES**: Client-side delay between prefill API and decode API

**Recommendation:** For F6's T0→T6 measurement (LLM decode → first speak token), T0 should be the actual decode loop start, not stream_decode entry. The correct marker is `PE_DECODE_BEGIN` (line 12581-12584) or a new stage recorded there.

---

## S4: First Main Token Source — Prefill Logits vs Autoregressive Decode

### Location
```
FILE:  tools/omni/omni.cpp:12801-12803
CONTEXT: Inside the LLM decode loop (for il < max_tgt_len), after llama_loop_with_hidden_and_token returns
GUARD:  Local bool llm_first_token_logged (declared at ~line 12690, per-request)
```

### Code flow

```
Line 12755: tmp = llama_loop_with_hidden_and_token(ctx_omni, ...);  ← LLM forward + sample
Line 12758: total_tokens_generated++;
Line 12801-12803:
    if (!llm_first_token_logged) {
        llm_first_token_logged = true;
        ctx_omni->e2e_stage.record(STAGE_llm_first_token);  ← FIRST AUTOREGRESSIVE TOKEN
    }
```

### Verdict

**STAGE_llm_first_token comes from AUTOREGRESSIVE DECODE, not prefill logits.**

Evidence:
1. The record is INSIDE the `for (int il = 0; il < max_tgt_len; )` decode loop (line 12702)
2. The decode loop is entered AFTER `g_decode_cv.wait(... prefill_done)` (line 12579)
3. `llama_loop_with_hidden_and_token` at line 12755 is the autoregressive step (generates one new token per call)
4. Prefill logits (first-token-from-prefill) would be available BEFORE the decode loop, during `g_decode_cv.wait`

**This is the correct semantic for F6's T2 (first LLM token from decode).** No correction needed.

---

## S5: Talker Trigger and Thread Semantics

### Context

There are TWO TTS thread functions:
- `tts_thread_func` (simplex mode) — line ~12564
- `tts_thread_func_duplex` (duplex mode) — line ~12561

Both call `generate_audio_tokens_local_simplex` for actual audio token generation.

### STAGE_talker_start Location

```
FILE:  tools/omni/omni.cpp:6514-6515
FN:    generate_audio_tokens_local_simplex()
THREAD: TTS thread
GUARD: timestamps_ns[STAGE_talker_start].load() == 0 (ONCE-LIFETIME)
```

### What triggers the TTS thread to process

```
Line 12574: ctx_omni->need_speek = true;
Line 12576: ctx_omni->llm_thread_info->cv.notify_all();  ← LLM thread signaled
// LLM thread runs, generates text tokens, pushes LLMOut to TTS queue
// TTS thread:
Line 7770-7774: cv.wait(lock, [&]{ return !queue.empty() || ...; })  ← TTS thread wakes
Line 7793-7804: Dequeue LLMOut from queue, accumulate text tokens
// ...then calls generate_audio_tokens_local_simplex for the chunk
Line 6514-6515: STAGE_talker_start recorded (first chunk only, once-lifetime)
```

### Is STAGE_talker_start a thread lifecycle event or per-request?

**Answer: It is a PER-SESSION-LIFETIME event, NOT per-request.**

The `load==0` once-guard means:
- First request of the session: STAGE_talker_start fires (correct)
- Subsequent requests: timestamps_ns is already non-zero → guard fails → never fires again

**This means STAGE_talker_start CANNOT be used as T3 (talker scheduled) for multi-request profiling.** For single-request profiling (F6 baseline), it works but measures the wrong thing — it measures the first chunk processing start, not the TTS thread wake-up from cv.wait.

### Where is the actual T3 (TTS thread wake-up)?

```
Line 7770-7774: TTS thread cv.wait returns (queue is non-empty)
```

This is the true "talker becomes eligible" event. There is NO existing stage here.

### Recommendation

For F6, T3 should be:
- **T3_wake**: TTS thread wakes from cv.wait (line 7770-7774) — NEW stage required
- **T3_start**: Talker starts first chunk processing (line 6514-6515) — existing but broken

---

## S6: Audio Token vs Speak Token Ordering

### The Two "Token" Events

| Event | Location | Thread | Semantic | Guard |
|-------|----------|--------|----------|-------|
| STAGE_speak_token | line 12815 | HTTP handler (stream_decode) | LLM generates token with type==SPEAK | NONE (fires every SPEAK token) |
| STAGE_talker_first_audio_token | line 6669 | TTS thread | TTS model generates first audio token | load==0 (once-lifetime) |

### Temporal Ordering

```
Time →

HTTP handler thread:
  llama_loop_with_hidden_and_token → sampled_token
  get_token_type(sampled_token) == SPEAK?
    YES → STAGE_speak_token recorded (line 12815)  ← T_LLM_SPEAK
  Push token to TTS queue (LLMOut)
  
TTS thread:
  cv.wait returns (queue non-empty)                  ← T_TTS_WAKE
  Dequeue LLMOut
  generate_audio_tokens_local_simplex()
    prefill_with_emb_tts → llama_decode (TTS model)  ← T_TTS_DECODE
    sample_tts_token → first audio token
    STAGE_talker_first_audio_token (line 6669)        ← T_TTS_FIRST_AUDIO
```

**STAGE_speak_token ALWAYS precedes STAGE_talker_first_audio_token in time.**

The causal chain is:
1. LLM generates SPEAK token → STAGE_speak_token (HTTP handler thread)
2. SPEAK token flows through LLMOut queue to TTS thread
3. TTS thread processes text tokens → generates audio tokens
4. First audio token → STAGE_talker_first_audio_token (TTS thread)

### Semantic Confusion in Draft Contract

The draft F6_TIMING_EVENT_CONTRACT.md mapped:
- T6 = STAGE_speak_token (LLM-level speak token)
- T5 = STAGE_talker_first_audio_token (TTS-level audio token)

But the draft also said: "T6 should be the first TTS audio token acceptance."

**This is wrong.** STAGE_speak_token is NOT a TTS audio token. It is an LLM text token with type SPEAK.

### Corrected Semantics

| Neutral Name | Description | Existing Stage? |
|---|---|---|
| D2 | LLM generates SPEAK-tagged token | STAGE_speak_token (line 12815) — correct location, wrong name |
| G0 | TTS thread wakes from cv.wait | MISSING |
| G1 | Talker starts processing first chunk | STAGE_talker_start (line 6515) — broken guard |
| G2 | TTS model forward pass | MISSING |
| G3 | First audio token sampled from TTS | STAGE_talker_first_audio_token (line 6669) — broken guard |
| Q0 | Audio token buffer reaches 28 (push to T2W queue) | STAGE_t2w_submit (line 6915) — broken guard |
| Q1 | T2W dequeues first token | STAGE_t2w_dequeue (line 10584) — broken guard |
| W0 | First WAV ready | STAGE_wav_ready (line 10834) — broken guard |
| W1 | First audio emitted to client | STAGE_client_first_audio (line 10841) — correct for single request |

---

## Consolidated Semantic Errors in Draft Contract (F6_TIMING_EVENT_CONTRACT.md)

| Error | Draft Claim | Actual Semantic | Severity |
|-------|------------|-----------------|----------|
| E1 | T0 = "Dynamic Prefill Complete / LLM Decode Submitted" | STAGE_request_received = stream_decode ENTRY (before prefill wait) | HIGH |
| E2 | T2 = "First Main LLM Token Available" from autoregressive decode | CORRECT — no error | — |
| E3 | T3 = "Talker Becomes Eligible / Is Scheduled" via STAGE_talker_start | STAGE_talker_start = first chunk processing start (not wake-up), once-lifetime broken | HIGH |
| E4 | T5 = STAGE_talker_first_audio_token, T6 = STAGE_speak_token | Temporal order is correct (STAGE_speak_token BEFORE STAGE_talker_first_audio_token) but draft implied opposite | HIGH |
| E5 | T6 = "First Valid Speak Token Accepted" | STAGE_speak_token is LLM-level SPEAK token detection, not TTS audio token acceptance | HIGH |
| E6 | T7 omitted — merged into T8 | STAGE_t2w_submit exists (line 6915) — queue push is a separate event from queue dequeue | MEDIUM |
