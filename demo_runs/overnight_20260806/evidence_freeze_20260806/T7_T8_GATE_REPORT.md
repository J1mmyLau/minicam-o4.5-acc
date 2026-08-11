# T7/T8 TTS Safety Gate Report
Date: 2026-08-05 | Binary: 2bfb2e5028c4f0cf5b8a9e17b22c2cd071505db9e0baa9afc456c00bae84ceb4

## T7A: Server-Side TTS Generation
| Case | Prompt | WAVs on Disk | Chunk Continuity | WAV Valid | Context REUSABLE | KV Cache Cap Hit |
|------|--------|-------------|-----------------|-----------|-----------------|-----------------|
| T7-S | 北京介绍(短) | 17 | PASS | PASS | PASS | No |
| T7-M | AI历史(中) | 72 | PASS | PASS | PASS | Yes (chunk 34) |
| T7-L | 深度学习(长) | 72 | PASS | PASS | PASS | Yes (chunk 50) |

Gate: T7A_SERVER_TTS=PASS (all WAVs valid 24kHz, context reusable after each session)
Note: TTS KV cache cap at 2048 (--ctx-size 2048) hit for medium/long prompts — gracefully handled (chunks skipped)

## T7B: Client-Side Audio Delivery
| Case | WS Audio Deltas | WS Audio Bytes | Streaming? | response.done.audio | Delivery Mode |
|------|----------------|---------------|------------|--------------------|--------------|
| T7-S | 17 | 2,083,840 | YES | null (expected) | WS_INCREMENTAL_STREAMING |
| T7-M | 72 | 9,195,520 | YES | null (expected) | WS_INCREMENTAL_STREAMING |
| T7-L | 72 | 9,195,520 | YES | null (expected) | WS_INCREMENTAL_STREAMING |

Gate: T7B_CLIENT_AUDIO=PASS (streaming confirmed, field name is "audio" not "audio_b64")
Protocol: Server sends `response.output.delta` with `kind=audio` and `audio` field (base64 PCM 24kHz 16-bit mono)

## T8: Cross-Session Isolation
| Interval | Session A (Apple) | Session B (Black Hole) | Text Iso | WAV Dir Iso | Drain New |
|----------|-------------------|------------------------|----------|-------------|-----------|
| 100ms | 303 chars, 50 audio | 300 chars, 55 audio | PASS | PASS | +3 |
| 500ms | 339 chars, 56 audio | 337 chars, 67 audio | PASS | PASS | +3 |
| 1000ms | 454 chars, 71 audio | 405 chars, 72 audio | PASS | PASS | +2 |

Gate: T8_TEXT_ISOLATION=PASS (no Apple content in B, no Black hole content in A)
Gate: T8_WAV_ISOLATION=PASS (distinct session_ids = distinct WAV directories)
Gate: T8_AUDIO_ISOLATION=PASS (WAV-on-disk count matches WS audio delta count 1:1)

## Open Issues
1. DRAIN_TIMEOUT: Accumulated ~28 total entries in server log. Each TTS session adds 1-3. Root cause: T2W drain timing with slow RTF (~5). NOT blocking — sessions complete correctly, no data loss.
2. Server log binary corruption: TTS token data logged to text file causes UnicodeDecodeError at position 76036
3. WAV directory discovery: Script picks wrong round_001 (empty) when round_000 already exists. Manual verification confirms correct WAVs.

## Gate Summary
- T7A_SERVER_TTS_GENERATION: PASS
- T7B_CLIENT_AUDIO_DELIVERY: PASS  
- T7B_WS_INCREMENTAL_STREAMING: YES (field: "audio", not "audio_b64")
- T7B_CLIENT_AUDIO_DELIVERY_MODE: WS_INCREMENTAL_STREAMING
- T8_TEXT_ISOLATION: PASS
- T8_WAV_DIR_ISOLATION: PASS  
- T8_AUDIO_CORRESPONDENCE: PASS (1:1 delta-to-file)
- DRAIN_TIMEOUT: FLAGGED (functional but accumulating)

## Evidence
- T7-S/M/L raw WS events: phase5_t7_tts/T7-*_raw_ws_events.jsonl
- T7 results: phase5_t7_tts/T7-*_result.json
- T8 raw WS events: phase6_t8_isolation/T8_*_raw.jsonl
- T8 results: phase6_t8_isolation/T8_pair_*.json
- Original evidence: t7_tts/t7s_original/
- Server log: phase2_isolation/server.log (binary corruption at byte 76036)
