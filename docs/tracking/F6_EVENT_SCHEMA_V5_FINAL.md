# F6 Event Schema V5 — Final Unification

**Date:** 2026-08-01
**Status:** RESOLVED — no mismatch
**Supersedes:** F6_EVENT_SCHEMA_V4_FINAL.md (contained incorrect "22 functional events" claim)

## Resolution

The V4 document claimed "22 functional events" with STAGE_COUNT=21. This was a counting error.
There are exactly **21 events**, all stored in `E2EStageTiming::timestamps_ns[STAGE_COUNT]`.

## Enum→Functional Mapping

| Index | Enum Name | JSON Name | Semantic | Writer Thread | Request-Scoped |
|-------|-----------|-----------|----------|---------------|----------------|
| 0 | STAGE_request_received | request_received | R0: HTTP request arrival | HTTP handler | Yes |
| 1 | STAGE_prompt_processing_start | prompt_processing_start | P0: Prefill begins | LLM thread | Yes |
| 2 | STAGE_llm_first_token | llm_first_token | L0: First text token | LLM thread | Yes |
| 3 | STAGE_speak_token | speak_token | S0: First speak_token emitted | LLM thread | Yes |
| 4 | STAGE_talker_start | talker_start | A0: TTS first llama_decode | TTS thread (once-guard) | Yes |
| 5 | STAGE_talker_first_audio_token | talker_first_audio_token | A1: First audio token sampled | TTS thread (once-guard) | Yes |
| 6 | STAGE_talker_token_28 | talker_token_28 | T2W buffer reaches 28 tokens | T2W thread (once-guard) | Yes |
| 7 | STAGE_t2w_submit | t2w_submit | **Q0**: First T2W job submitted to queue | TTS thread (once-guard) | Yes |
| 8 | STAGE_t2w_dequeue | t2w_dequeue | **Q1**: First T2W job dequeued | T2W thread (once-guard) | Yes |
| 9 | STAGE_flow_start | flow_start | **F0**: Flow model begins | token2wav-impl (C8 mirror) | Yes (C8) |
| 10 | STAGE_flow_end | flow_end | **F1**: Flow model ends | token2wav-impl (C8 mirror) | Yes (C8) |
| 11 | STAGE_vocoder_start | vocoder_start | **V0**: Vocoder begins | token2wav-impl (C8 mirror) | Yes (C8) |
| 12 | STAGE_vocoder_end | vocoder_end | **V1**: Vocoder ends | token2wav-impl (C8 mirror) | Yes (C8) |
| 13 | STAGE_wav_ready | wav_ready | **W0**: First WAV file written | T2W thread (once-guard) | Yes |
| 14 | STAGE_client_first_audio | client_first_audio | C0: First audio sent to client | T2W thread (once-guard) | Yes |
| 15 | STAGE_request_done | request_done | Request complete | HTTP handler | Yes |
| 16 | STAGE_decode_loop_begin | decode_loop_begin | **D0**: Decode loop begins | LLM thread | Yes |
| 17 | STAGE_llm_first_decode_step | llm_first_decode_step | **D1**: First decode step | LLM thread | Yes |
| 18 | STAGE_tts_wake | tts_wake | **G0**: TTS thread wakes | TTS thread (once-guard) | Yes |
| 19 | STAGE_tts_first_decode | tts_first_decode | **G2**: First TTS decode call | TTS thread (once-guard) | Yes |
| 20 | STAGE_t2w_preprocess_end | t2w_preprocess_end | **Q2**: T2W preprocessing done, Flow input ready | T2W thread (C8) | Yes (C8) |

## Count Reconciliation

```
enum entries                    = 21  (lines with STAGE_xxx = N in E2EStage enum)
STAGE_COUNT                     = 21  (last enum entry)
stage_name() switch cases       = 21  (one case per enum entry)
timestamps_ns[] size            = STAGE_COUNT = 21
summary arrays size             = STAGE_COUNT = 21
record() bounds check           = stage < STAGE_COUNT (= 21)
reset() loop bound              = i < STAGE_COUNT (= 21)
JSON serializer loop bound      = i < STAGE_COUNT (= 21)
async_stages[] entries          = 8   (Q1, Q2, F0, F1, V0, V1, W0, C0)
async_names[] entries           = 8

ALL COUNTS MATCH. No discrepancy.
```

## Q0/Q1/Q2 Fixed Semantics

| Label | Stage | Definition |
|-------|-------|------------|
| **Q0** | STAGE_t2w_submit (7) | First T2W job submitted to queue |
| **Q1** | STAGE_t2w_dequeue (8) | First T2W job dequeued by worker |
| **Q2** | STAGE_t2w_preprocess_end (20) | T2W preprocessing completed (buffer merge, token accumulation), Flow input ready |

### Derived Intervals

```
Q0→Q1  = queue wait time
Q1→Q2  = T2W preprocessing (dequeue + buffer merge + token accumulation to WINDOW_SIZE)
Q2→F0  = dispatch gap (preprocess done → Flow actually begins)
F0→F1  = Flow model execution
F1→V0  = inter-stage gap (Flow→Vocoder handoff)
V0→V1  = Vocoder model execution
V1→W0  = WAV packaging + write
```

## Verification Checklist

- [x] Enum count = 21
- [x] STAGE_COUNT = 21
- [x] stage_name() cases = 21
- [x] async_stages[] = 8
- [x] timestamps_ns[STAGE_COUNT] = 21
- [x] JSON serializer iterates [0, STAGE_COUNT)
- [x] record() bounds checks stage < STAGE_COUNT
- [x] reset() clears all 21 entries
- [x] summary arrays sized STAGE_COUNT
- [x] Q0/Q1/Q2 semantics restored and documented
- [x] No "22nd functional event" myth
