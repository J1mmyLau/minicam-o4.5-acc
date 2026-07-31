# F6 B6B: Event Scope Audit

**Created:** 2026-07-31
**Source:** `tools/omni/omni.cpp` @ `4659239`

## 1. Code Trace: stream_decode() (simplex path)

```
Line 12778: int step_size = 10;
Line 12779: bool is_first_chunk = true;  // B6b addition

Line 12840-12849:
  int effective_step = (is_first_chunk && !ctx_omni->duplex_mode && ctx_omni->use_tts) ? 5 : step_size;

Line 12850: while (jl < effective_step && !llm_finish && ...) {
    Line 12857-12860: D1 (llm_first_decode_step) — recorded on FIRST decode step
    Line 12871-12872: is_valid_tts_token() → if valid: jl++, collect chunk_token_ids + hidden_states
    Line 12910-12912: D2 (llm_first_token) — recorded on FIRST token (any type)
    Line 12909-12918: D3 (speak_token) — recorded on first SPEAK-tagged token
    Line 12922+: End token checks (TURN_EOS, TTS_EOS, EOS, LISTEN, CHUNK_EOS)
    Line 13010-13015: response += tmp_str (text token appended to response)
}

// After inner loop exits:
Line 13106-13148: TTS queue push (LLMOut creation → queue push → cv.notify_all)
Line 13154: is_first_chunk = false;  // B6b addition
```

## 2. Code Trace: duplex_do_decode() (duplex path)

```
Line 11680: const int step_size = 10;
Line 11681: bool is_first_duplex_chunk = true;  // B6b addition

Line 11703-11704:
  int effective_duplex_step = (is_first_duplex_chunk && ctx_omni->use_tts) ? 5 : step_size;

Line 11704-11726: while (jl < effective_duplex_step && ...) {
    Line 11710-11712: llama_loop_with_hidden_and_token → generates token
    Line 11716-11721: is_valid_tts_token() → if valid: jl++, collect
    Line 11733+: Token type checks (TURN_EOS, TTS_EOS, EOS, LISTEN)
    Line 11772: response += std::string(tmp);
}

// After inner loop exits:
Line 11821-11841: TTS queue push (LLMOut → queue push → cv.notify_all)
Line 11845-11847: is_first_duplex_chunk = false;  // B6b addition
```

## 3. Event Timing Analysis

### Events recorded INSIDE the inner while loop (UNAFFECTED by step_size)

| Event | Stage | Recorded when | Affected by step_size? |
|-------|-------|---------------|----------------------|
| D1 | llm_first_decode_step | First autoregressive decode step | **NO** — once-guard, fires on step 1 regardless |
| D2 | llm_first_token | First token of any type | **NO** — once-guard, fires on token 1 regardless |
| D3 | speak_token | First SPEAK-tagged token | **NO** — once-guard, fires when SPEAK token appears |

### Events triggered AFTER inner loop exit (AFFECTED by step_size)

| Event | Stage | Recorded when | Affected by step_size? |
|-------|-------|---------------|----------------------|
| G0 | tts_wake | TTS worker wakes after chunk push | **YES** — earlier push = earlier wake |
| G1 | talker_start | Talker processing starts | **YES** — cascaded from G0 |
| G2 | tts_first_decode | First TTS decode step | **YES** — cascaded from G0 |
| G3 | talker_first_audio_token | First audio token from talker | **YES** — cascaded from G0 |
| G4 | t2w_submit | First T2W submit | **YES** — cascaded from G0 |
| Q0 | t2w_dequeue | T2W worker picks up batch | **YES** — cascaded from G0 |
| W0 | wav_ready | First valid WAV | **YES** — cascaded from G0 |
| W1 | client_first_audio | First audio to client | **YES** — cascaded from G0 |

## 4. Verified Answers

### Q1: Does D3 (speak_token) happen before or after first chunk submission?
**Before.** D3 is recorded inside the inner while loop at the moment the SPEAK token is generated. The chunk is submitted after the loop exits. D3 always precedes G0.

### Q2: Does step_size=5 affect D0→D3?
**No.** D0, D1, D2, D3 are all recorded inside the inner while loop at the moment their respective conditions are met. step_size only determines when the loop exits. Matched-pair data confirms: D0=15ms (both), D1=46→45ms (±1ms noise), D2=82ms (both identical).

### Q3: Does it only affect D2/D3→G0?
**Yes.** The entire improvement is in the gap between the last inner-loop event (D2/D3) and the first post-push event (G0). All downstream events (G1, G2, G3, G4, Q0, W0, W1) cascade from G0 with unchanged processing latency.

### Q4: Which event represents "first text handed to Talker"?
**G0 (tts_wake).** Recorded in the TTS thread when `cv.wait()` returns after `cv.notify_all()` from the LLM thread's queue push.

### Q5: Are simplex and duplex consistent?
**Yes.** Both paths have identical logic: `effective_step = is_first_chunk && use_tts ? 5 : step_size`, with `is_first_chunk` reset after first queue push.

### Q6: Does text-only keep step_size=10?
**Yes.** Guarded by `ctx_omni->use_tts`. When `use_tts=false`, effective_step = step_size = 10.

### Q7: Do subsequent chunks keep step_size=10?
**Yes.** `is_first_chunk` is set to false after the first successful queue push. Subsequent loop iterations use step_size=10.

### Q8: EOS with <5 tokens — how is it flushed?
The inner while loop exits on `llm_finish` (set by EOS detection at line 12964). The TTS push block at line 13106 has condition `(!response.empty() || llm_finish)`, so even with <5 valid tokens and empty response, the chunk is pushed when llm_finish=true.

### Q9: Do punctuation, control tokens, invalid tokens count toward jl?
**No.** Only tokens that pass `is_valid_tts_token()` increment `jl`. Punctuation, control tokens, and other non-TTS tokens are generated but NOT counted. They ARE appended to `response` for text output.

### Q10: Can an empty chunk be submitted?
**Yes, conditionally.** If `llm_finish=true` and `response.empty()`, an LLMOut with empty text and token lists is created and pushed. This signals the TTS thread to flush and finish.

## 5. Correct Optimization Name

Based on this audit, the optimization changes:
- **What:** Reduces the number of valid TTS tokens accumulated before first chunk dispatch from 10 to 5
- **Which interval:** D2/D3 → G0 (text accumulation → TTS worker wake)
- **What it does NOT change:** D0→D2 (LLM token generation speed), D0→D3 (LLM decode→speak token time)

### Accepted name: **EARLY_FIRST_TTS_CHUNK_DISPATCH**

Alternative valid names:
- `REDUCED_FIRST_TTS_CHUNK_ACCUMULATION`
- `FASTER_FIRST_TALKER_TRIGGER`

### Explicitly NOT:
- ❌ `LLM_DECODE_TO_SPEAK_TOKEN_OPTIMIZATION`
- ❌ `DECODE_TO_SPEAK_OPTIMIZATION`  
- ❌ `TTS_LATENCY_OPTIMIZATION` (too broad)

## 6. Conclusion

**B6b = EARLY_FIRST_TTS_CHUNK_DISPATCH.** It reduces the wait between LLM text generation and TTS worker activation by dispatching the first chunk after 5 valid tokens instead of 10. It does NOT accelerate the LLM's generation of speak tokens.
