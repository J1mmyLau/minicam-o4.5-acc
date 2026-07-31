# F6 R0: Canonical Event Name Registry

**Date:** 2026-07-31
**Scope:** All F6 documents, gate matrices, CSVs, and summaries

## Canonical Names (MANDATORY in all F6 docs)

| Short Name | Canonical Full Name | Definition | Thread | Availability |
|-----------|-------------------|------------|--------|-------------|
| **D0** | DECODE_LOOP_BEGIN | HTTP handler enters decode loop | LLM (sync) | Always |
| **D1** | PREFILL_DONE | Prefill phase complete | LLM (sync) | Always |
| **D2** | MAIN_FIRST_TOKEN | First LLM token sampled | LLM (sync) | Always |
| **D3** | MAIN_FINAL_TOKEN | Last LLM token / EOS detected | LLM (sync) | Always |
| **G0** | TTS_WAKE | TTS worker wakes from cv.wait | TTS worker | Most requests |
| **G1** | TTS_AUDIO_PROMPT_DONE | Audio prompt embedding complete | TTS worker | Most requests |
| **G2** | TOKEN_CLASSIFICATION_DONE | Valid/invalid token classification done | TTS worker | Most requests |
| **G3** | TALKER_FIRST_AUDIO_TOKEN | First audio token sampled by Talker | TTS worker | ~43% of requests |
| **G4** | FIRST_T2W_SUBMIT | First 25-audio-token batch submitted to T2W queue | T2W worker | ~13% of requests |
| **Q0** | T2W_QUEUE_DEQUEUE | T2W dequeue from audio token queue | T2W worker | Rare |
| **W0** | FIRST_VALID_WAV_READY | First valid WAV file written to disk | Flow+Vocoder | Very rare (<2%) |
| **W1** | FINAL_WAV_READY | Final WAV file for request complete | Flow+Vocoder | Very rare |

## Interval Names (MANDATORY)

| Interval | Canonical Name | Formula | What It Measures |
|----------|---------------|---------|-----------------|
| **D0→D2** | MAIN_FIRST_TOKEN_LATENCY | D2 - D0 | Main LLM decode latency to first token |
| **D2→G0** | FIRST_TEXT_CHUNK_ACCUMULATION_AND_TTS_WAKE | G0 - D2 | Accumulate valid tokens + push to TTS queue + TTS worker wake |
| **G0→G3** | TALKER_TO_FIRST_AUDIO_TOKEN | G3 - G0 | TTS prompt processing + talker autoregressive generation to first audio token |
| **D0→G3** | DECODE_TO_FIRST_TALKER_AUDIO_TOKEN | G3 - D0 | Full path: LLM decode + text accumulation + TTS wake + talker first audio token |
| **G3→G4** | TALKER_AUDIO_TOKEN_ACCUMULATION | G4 - G3 | Talker generates 25 audio tokens before T2W submit |
| **G4→Q0** | T2W_QUEUE_LATENCY | Q0 - G4 | Audio token batch waiting in T2W queue |
| **Q0→W0** | T2W_FLOW_VOCODER_LATENCY | W0 - Q0 | T2W model + Flow matching + Vocoder processing |
| **D0→W0** | DECODE_TO_FIRST_VALID_WAV | W0 - D0 | End-to-end decode to first valid WAV on disk |
| **R0→W0** | REQUEST_TO_FIRST_VALID_WAV | W0 - R0 | Full user-facing latency: HTTP request arrival → first WAV ready |

## Forbidden Equivalences

| ❌ DO NOT WRITE | ✅ CORRECT |
|----------------|-----------|
| "D0→G3 = first audio" | "D0→G3 = DECODE_TO_FIRST_TALKER_AUDIO_TOKEN" |
| "D0→G3 = E2E first audio" | "D0→G3 is a proxy; true E2E first audio is D0→W0 or R0→W0" |
| "first speak token" | "first Talker audio token (G3)" — G3 is NOT a speak/heard token |
| "decode-to-speak" | "decode-to-first-talker-audio-token" unless W0 is also measured |
| "full pass-through to first audio" | "pass-through to first Talker audio token confirmed; W0 pass-through not yet measured" |
| "D0→G3 -151ms = user hears audio 151ms earlier" | "D0→G3 -151ms = Talker produces first audio token 151ms earlier; W0 latency not yet measured on same pairs" |
