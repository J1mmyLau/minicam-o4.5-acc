# F6 TIMING EVENT CONTRACT V1 — LLM Decode → First Speak Token [SUPERSEDED]

**Status: SUPERSEDED by `F6_TIMING_EVENT_CONTRACT_V2.md`** (2026-07-30)
**Created:** 2026-07-30
**Worktree:** `/workspace/llama.cpp-omni-f6`
**Branch:** `perf/f6-decode-to-speak`

> ⚠️ This V1 draft has 5 confirmed semantic errors. Use V2 instead.
> Errors: E1 (T0 wrong location), E3 (T3 wrong semantic), E4 (T5/T6 order), E5 (T6 wrong level), E6 (T7 omitted). See `F6_TIMING_EVENT_SEMANTIC_AUDIT.md`.

---

## Clock Source

All timestamps use `CLOCK_MONOTONIC_RAW` via `std::chrono::steady_clock::now().time_since_epoch().count()` (nanoseconds).

---

## Event Definitions

### T0 — Dynamic Prefill Complete / LLM Decode Submitted

```
STAGE:          STAGE_request_received  (existing, repurposed as T0 anchor)
FILE:           tools/omni/omni.cpp
LINE:           12508
THREAD:         HTTP handler thread
SOURCE:         std::chrono::steady_clock
SEMANTICS:      stream_decode has received the request, reset interrupt state,
                and is about to signal the LLM thread to begin.
                This is the effective "decode request submitted" timestamp.
CRITICAL PATH:  YES — marks the start of T0→T6 measurement window
EXISTING STAGE: STAGE_request_received (line 218, enum value 0)
```

### T1 — First Main LLM Decode Step Starts

```
STAGE:          NEW: STAGE_main_decode_start
FILE:           tools/omni/omni.cpp
LINE:           2188 (eval_tokens_with_hidden → llama_decode for first autoregressive token)
                OR ~12755 (llama_loop_with_hidden_and_token call)
THREAD:         HTTP handler thread (stream_decode caller)
SOURCE:         std::chrono::steady_clock
SEMANTICS:      First llama_decode() call that generates a new token (not prompt/system eval).
                The distinction from T2 is that T1 is pre-decode, T2 is post-decode.
                In the LLM decode loop (line 12702), the first call through
                llama_loop_with_hidden_and_token → sample_with_hidden_and_token →
                eval_id_with_hidden → eval_tokens_with_hidden → llama_decode.
CRITICAL PATH:  YES — marks the start of LLM compute
STATUS:         New stage to be added
```

### T2 — First Main LLM Token Available

```
STAGE:          STAGE_llm_first_token (existing)
FILE:           tools/omni/omni.cpp
LINE:           12801-12803
THREAD:         HTTP handler thread
SOURCE:         std::chrono::steady_clock
SEMANTICS:      First token from LLM autoregressive decode is available.
                After llama_loop_with_hidden_and_token returns, before
                token is pushed to TTS queue.
                Guarded by llm_first_token_logged flag.
CRITICAL PATH:  YES
EXISTING STAGE: STAGE_llm_first_token (line 220, enum value 2)
```

### T3 — Talker Becomes Eligible / Is Scheduled

```
STAGE:          STAGE_talker_start (existing, repurposed)
FILE:           tools/omni/omni.cpp
LINE:           6515 (tts_thread_func_duplex) or equivalent in tts_thread_func
                AND line 7770-7774 (TTS thread cv.wait wake-up)
THREAD:         TTS thread (tts_thread_func_duplex or tts_thread_func)
SOURCE:         std::chrono::steady_clock
SEMANTICS:      TTS thread wakes from cv.wait after LLM pushes first token block.
                STAGE_talker_start is recorded when the talker becomes ready
                to process the first chunk (line 6515).
                The cv.wait wake-up at line 7770-7774 is the scheduling event.
CRITICAL PATH:  YES
EXISTING STAGE: STAGE_talker_start (line 222, enum value 4)
NOTE:           STAGE_talker_start may need re-recording closer to cv wake-up for
                accurate scheduling-wait measurement.
```

### T4 — Talker First Decode Step Starts

```
STAGE:          NEW: STAGE_talker_first_decode
FILE:           tools/omni/omni.cpp
LINE:           3387 (prefill_with_emb_tts → llama_decode for TTS model)
                Via call chain: generate_audio_tokens_local (7247) →
                prefill_with_emb_tts (7247) → llama_decode (3387)
THREAD:         TTS thread
SOURCE:         std::chrono::steady_clock
SEMANTICS:      First llama_decode() call on ctx_tts_llama for audio token generation.
                This is when the talker starts its compute for the first speak token.
CRITICAL PATH:  YES
STATUS:         New stage to be added
```

### T5 — First Speak Token Logits Ready

```
STAGE:          STAGE_talker_first_audio_token (existing)
FILE:           tools/omni/omni.cpp
LINE:           4089 (sample_tts_token → llama_get_embeddings_ith)
                Recorded at line 6669
THREAD:         TTS thread
SOURCE:         std::chrono::steady_clock
SEMANTICS:      TTS model's first forward pass complete.
                Hidden state retrieved via llama_get_embeddings_ith.
                Logits computed through head_code projection.
                First audio token about to be sampled.
CRITICAL PATH:  YES
EXISTING STAGE: STAGE_talker_first_audio_token (line 223, enum value 5)
```

### T6 — First Valid Speak Token Accepted/Submitted

```
STAGE:          STAGE_speak_token (existing)
FILE:           tools/omni/omni.cpp
LINE:           12815 (stream_decode, after llama_loop_with_hidden_and_token)
                Also line 7312-7342 (sample_tts_token return, token pushed to output_audio_tokens)
THREAD:         TTS thread (for audio token acceptance)
SOURCE:         std::chrono::steady_clock
SEMANTICS:      First valid audio token from TTS model accepted.
                Token passes validation (in-range, non-EOS).
                Pushed to output_audio_tokens and stream_buffer.
                This is the transition point from "generating audio tokens" to
                "audio tokens ready for T2W processing".
CRITICAL PATH:  YES
EXISTING STAGE: STAGE_speak_token (line 221, enum value 3)
NOTE:           STAGE_speak_token recorded at line 12815 is in stream_decode context
                (LLM text token that triggers speak). The TTS audio token acceptance
                at line 7312-7342 is a different event. For F6 T0→T6, T6 should be
                the first TTS audio token acceptance (which directly feeds T2W).
                May need to differentiate: STAGE_speak_token_text (LLM) vs
                STAGE_speak_token_audio (TTS first audio token).
```

### T7 — Speak Token Enters T2W Queue

```
STAGE:          STAGE_t2w_submit (existing)
FILE:           tools/omni/omni.cpp
LINE:           6915 (stream_buffer push to t2w_thread_info->queue)
THREAD:         TTS thread
SOURCE:         std::chrono::steady_clock
SEMANTICS:      stream_buffer reaches FIRST_CHUNK_SIZE (28 tokens).
                T2WOut object created with accumulated audio tokens.
                Pushed to t2w_thread_info->queue, cv.notify_one() called.
CRITICAL PATH:  YES
EXISTING STAGE: STAGE_t2w_submit (line 225, enum value 7)
```

### T8 — T2W Worker Receives First Token

```
STAGE:          STAGE_t2w_dequeue (existing)
FILE:           tools/omni/omni.cpp
LINE:           10583-10585
THREAD:         T2W thread (t2w_thread_func_cpp)
SOURCE:         std::chrono::steady_clock
SEMANTICS:      T2W thread wakes from cv.wait, dequeues first T2WOut.
                Guarded by first-dequeue check (timestamps_ns == 0).
CRITICAL PATH:  YES
EXISTING STAGE: STAGE_t2w_dequeue (line 226, enum value 8)
```

### T9 — First Audio Chunk Ready

```
STAGE:          STAGE_wav_ready (existing)
FILE:           tools/omni/omni.cpp
LINE:           10833-10834
THREAD:         T2W thread
SOURCE:         std::chrono::steady_clock
SEMANTICS:      Token2WavSession::feed_window returns true.
                chunk_wav contains PCM audio samples.
                Audio output callback invoked.
                First audio chunk produced from Flow+Voder pipeline.
CRITICAL PATH:  YES
EXISTING STAGE: STAGE_wav_ready (line 229, enum value 13)
```

---

## F6 DERIVED METRICS

From the T0-T9 timestamps, compute per-request:

```
main_llm_first_token_ms       = T2 - T0
talker_schedule_wait_ms       = T4 - T2   (NEW: requires T4 = STAGE_talker_first_decode)
talker_first_step_ms          = T5 - T4   (NEW: requires T4)
speak_decision_ms             = T6 - T5
speak_to_t2w_queue_ms         = T8 - T6   (was T6→T7; adjusted: T8-T6 captures queue+dispatch)
token_to_t2w_queue_depth_ms   = T7 - T6
t2w_queue_wait_ms             = T8 - T7
first_audio_compute_ms        = T9 - T8
decode_to_first_speak_ms      = T6 - T0   ← PRIMARY F6 METRIC
request_to_first_audio_ms     = T9 - T0   ← SECONDARY (excludes client network)
```

## GAPS: New Stages Required

Two stages need to be added to the `E2EStage` enum:

```cpp
// In omni.h, after STAGE_prompt_processing_start (line 219):
STAGE_main_decode_start,       // T1: first autoregressive llama_decode
// In omni.h, after STAGE_talker_start (line 222):
STAGE_talker_first_decode,     // T4: Talker's first llama_decode call
```

And `STAGE_COUNT` must be bumped from 16 to 18.

Recording locations:
- `STAGE_main_decode_start`: Insert at line ~12755 in `stream_decode`, just before `llama_loop_with_hidden_and_token` call (guarded by `once` flag)
- `STAGE_talker_first_decode`: Insert at line ~3387 in `prefill_with_emb_tts`, or at line ~7247 in `generate_audio_tokens_local`, before the first `prefill_with_emb_tts` call (guarded by `once` flag)

---

## EXISTING INFRASTRUCTURE TO PRESERVE

| Component | File:Line | Purpose |
|-----------|-----------|---------|
| E2EStageTiming | omni.h:237 | Per-request nanosecond timestamps |
| STAGE_COUNT=16 | omni.h:234 | Current stage count (→ 18 after adding 2) |
| timestamps_ns[] | omni.h:242 | Atomic int64_t array, 0 = not recorded |
| record(stage) | omni.h:249 | Records monotonic timestamp if enabled |
| enabled flag | omni.h:241 | bool for instrumentation on/off |
| elapsed_ns(a,b) | omni.h:255 | Compute interval between stages |
| stage_name() | omni.h:269 | Human-readable stage name |

---

## THREAD OWNERSHIP

| Event | Thread | Function |
|-------|--------|----------|
| T0 | HTTP handler | stream_decode |
| T1 | HTTP handler | stream_decode → eval_tokens_with_hidden |
| T2 | HTTP handler | stream_decode |
| T3 | TTS thread | tts_thread_func_duplex / tts_thread_func |
| T4 | TTS thread | generate_audio_tokens_local → prefill_with_emb_tts |
| T5 | TTS thread | generate_audio_tokens_local → sample_tts_token |
| T6 | TTS thread | generate_audio_tokens_local |
| T7 | TTS thread | generate_audio_tokens_local |
| T8 | T2W thread | t2w_thread_func_cpp |
| T9 | T2W thread | t2w_thread_func_cpp |

---

## INSTRUMENTATION RULES

1. **Diagnostic mode**: Record all stages per request. Output full event trace to log file (not stdout).
2. **Statistical mode**: Record all stages per request. Output ONE summary line per request with all derived metrics. No per-token logging.
3. **Overhead validation**: Run 10 matched pairs with instrumentation ON vs OFF. If median T0→T6 changes >1%, reduce overhead (batch writes, avoid string formatting in hot path).
4. **Atomic access**: All timestamps use `std::atomic<int64_t>` with `memory_order_relaxed` (monotonic writes on single threads, reads are eventually consistent).
5. **Once guards**: T1, T3, T4, T5, T6 must be guarded by `once` flags to avoid recording on subsequent tokens/chunks.

---

## VALIDATION CHECKLIST

- [ ] T0→T1 interval is negligible (dynamic prefill already done, just function call overhead)
- [ ] T1→T2 is the main LLM compute (llama_decode + sampling)
- [ ] T2→T3 is queue push + cv notify + TTS thread wake (scheduling overhead)
- [ ] T3→T4 is TTS preparation (embedding merge, projection, normalization)
- [ ] T4→T5 is TTS model forward pass
- [ ] T5→T6 is audio token sampling + validation
- [ ] T6→T7 is token accumulation to FIRST_CHUNK_SIZE (28 tokens)
- [ ] T7→T8 is T2W queue dispatch
- [ ] T8→T9 is Flow+Voder audio generation
- [ ] T0→T6 ≤ T0→T9 (speak token should precede first audio)
- [ ] All timestamps monotonic per-request
- [ ] No negative intervals
