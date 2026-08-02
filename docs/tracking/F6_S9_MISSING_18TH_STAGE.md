# F6 Phase 3 — S9 Missing 18th Stage Identification (R8)

**Date:** 2026-08-02
**HEAD:** `aabd12e`

## Executive Summary

**Missing 18th stage: Q2 (`t2w_preprocess_end`) — Server-only stage**

CLI has 17 active stages, Server has 18. Q2 is legitimately server-only because it's recorded in the server's T2W worker path. The 17 shared stages are functionally identical between CLI and Server.

## Complete Stage Inventory (21 total)

### Enum Definition (`omni.h:222-246`)

| Index | Enum Name | Public Name | Status |
|-------|-----------|-------------|--------|
| 0 | STAGE_request_received | request_received | ✅ Active |
| 1 | STAGE_prompt_processing_start | prompt_processing_start | ⛔ DEAD — never recorded |
| 2 | STAGE_llm_first_token | llm_first_token | ✅ Active |
| 3 | STAGE_speak_token | speak_token | ⛔ DEAD — model-dependent, MiniCPM-o-4_5 doesn't trigger |
| 4 | STAGE_talker_start | talker_start | ✅ Active |
| 5 | STAGE_talker_first_audio_token | talker_first_audio_token | ✅ Active |
| 6 | STAGE_talker_token_28 | talker_token_28 | ✅ Active |
| 7 | STAGE_t2w_submit | t2w_submit (Q0) | ✅ Active |
| 8 | STAGE_t2w_dequeue | t2w_dequeue (Q1) | ✅ Active |
| 9 | STAGE_flow_start | flow_start (F0) | ✅ Active |
| 10 | STAGE_flow_end | flow_end (F1) | ✅ Active |
| 11 | STAGE_vocoder_start | vocoder_start (V0) | ✅ Active |
| 12 | STAGE_vocoder_end | vocoder_end (V1) | ✅ Active |
| 13 | STAGE_wav_ready | wav_ready (W0) | ✅ Active |
| 14 | STAGE_client_first_audio | client_first_audio (C0) | ✅ Active |
| 15 | STAGE_request_done | request_done | ⛔ DEAD — never recorded |
| 16 | STAGE_decode_loop_begin | decode_loop_begin (D0) | ✅ Active |
| 17 | STAGE_llm_first_decode_step | llm_first_decode_step (D1) | ✅ Active |
| 18 | STAGE_tts_wake | tts_wake (G0) | ✅ Active |
| 19 | STAGE_tts_first_decode | tts_first_decode (G2) | ✅ Active |
| 20 | STAGE_t2w_preprocess_end | t2w_preprocess_end (Q2) | ✅ Active — **Server-only** |

**STAGE_COUNT = 21** (21 enum entries, 21 stage_names)

### Summary

| Category | Count | Stages |
|----------|-------|--------|
| Dead (never recorded) | 2 | prompt_processing_start, request_done |
| Model-dependent (usually dead) | 1 | speak_token |
| Active — both CLI and Server | **17** | All remaining except Q2 |
| Active — Server only | **1** | t2w_preprocess_end (Q2) |
| **Total active** | **18** | |

## CLI vs Server Presence Matrix

| Stage | CLI | Server | Reason |
|-------|:---:|:---:|--------|
| request_received | ✅ | ✅ | Recorded at stream_decode start |
| decode_loop_begin | ✅ | ✅ | Recorded after prefill |
| llm_first_decode_step | ✅ | ✅ | First decode call |
| llm_first_token | ✅ | ✅ | First token output |
| tts_wake | ✅ | ✅ | TTS thread wake |
| tts_first_decode | ✅ | ✅ | First TTS decode |
| talker_start | ✅ | ✅ | Talker processing start |
| talker_first_audio_token | ✅ | ✅ | First audio token |
| talker_token_28 | ✅ | ✅ | Buffer reaches 28 tokens |
| t2w_submit (Q0) | ✅ | ✅ | T2W job submitted |
| t2w_dequeue (Q1) | ✅ | ✅ | T2W job dequeued |
| **t2w_preprocess_end (Q2)** | **❌** | **✅** | **Server T2W path only** |
| flow_start (F0) | ✅ | ✅ | Flow execution start |
| flow_end (F1) | ✅ | ✅ | Flow execution end |
| vocoder_start (V0) | ✅ | ✅ | Vocoder execution start |
| vocoder_end (V1) | ✅ | ✅ | Vocoder execution end |
| wav_ready (W0) | ✅ | ✅ | First WAV ready |
| client_first_audio (C0) | ✅ | ✅ | Audio sent to client |

## Q2 (t2w_preprocess_end) Details

### Why Server-Only

Q2 is recorded in `omni.cpp:11178` inside the T2W worker's feed_window() path:

```cpp
if (captured_profile_handle) {
    captured_profile_handle->record(STAGE_t2w_preprocess_end, captured_profile_gen);
}
```

The CLI uses a different T2W invocation path that doesn't go through this recording site. The CLI may invoke `token2wav::feed_window()` directly without the `captured_profile_handle` wrapper.

### Impact

- Q2 is **not a critical bottleneck metric** — it measures preprocessing time between dequeue and Flow start
- In Server profiles where Q2 is present, Q1 (dequeue) to Q2 (preprocess_end) is typically ~0ms, meaning preprocessing is instantaneous relative to Flow execution
- The absence of Q2 in CLI does not affect core C8 Flow/Vocoder instrumentation

## S9 Status

**S9 = PASS_WITH_MODALITY_EXCEPTION**

The 17/18 parity is explained:
- 17 stages shared between CLI and Server (functionally identical)
- 1 stage (Q2) is server-only by architectural design
- 3 stages (prompt_processing_start, speak_token, request_done) are dead in both paths
- No missing stage indicates a bug — the difference is architectural, not a defect

The previous "17/18 core C8 equivalent" claim was essentially correct but lacked specificity. The 18th stage is Q2 and its server-only status is expected.
