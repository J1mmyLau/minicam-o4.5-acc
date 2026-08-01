# F6 Phase 3 Input Data Audit (C1)

**Date:** 2026-08-01
**Source:** `/tmp/f6_fp16_w10/` (60 ABBA blocks, 120 matched pairs)

---

## Data Structure

Each request produces TWO JSON files:
1. `e2e_XXXX.json` — `stages_ms` (main thread, 5 fields)
2. `e2e_XXXX_audio.json` — `async_stages_ms` (T2W thread, 6 fields)

### stages_ms (available)
```
request_received, llm_first_decode_step (D0), llm_first_token (D2),
decode_loop_begin, tts_wake (G0)
```

### async_stages_ms (available)
```
t2w_dequeue, flow_start, flow_end, vocoder_start, vocoder_end, wav_ready (W0)
```

### NOT available
```
talker_start, talker_first_audio_token (G3), talker_token_28, t2w_submit (G4)
```

All values are **integer milliseconds** — no nanosecond resolution in profiles.

---

## Provenance Verification

| Check | Result |
|-------|--------|
| 120 pairs all from same binary SHA256 | ✓ (`42c97f40...`) |
| Model SHA256 consistent | ✓ (`d1e69845...`) |
| CANN Flow/Vocoder enabled all requests | ✓ (async_stages_ms populated for all 240 requests) |
| B6b baseline/candidate only differs by step=10/5 | ✓ (sequential ABBA, same binary, env var only) |
| 60 ABBA blocks, 120 matched pairs | ✓ |
| 240/240 requests have both JSON files | ✓ |
| Profile count: 240 main + 240 audio = 480 JSON files | ✓ |
| W0 presence: 240/240 (100%) | ✓ |

---

## Timing Resolution

**All profile values are integer milliseconds.** The server records timestamps using `ggml_time_ms()` (or equivalent) which provides millisecond resolution. There is NO nanosecond data in the profiles.

This means:
- Differences < 1ms are not detectable
- Paired deltas of 0ms at ms resolution may represent sub-millisecond true differences
- CI95 [0,0] for metrics with <1ms true variation is expected (the median across bootstrap resamples is always 0)

---

## Key Distributions (from raw JSON)

### D0→D2 (Main LLM first-token time)

| Config | n | Values | p50 | p95 | p99 |
|--------|---|--------|-----|-----|-----|
| OFF | 120 | {27: 2, 28: 95, 29: 23} | 28ms | 29ms | 29ms |
| ON | 120 | {27: 3, 28: 86, 29: 30, 30: 1} | 28ms | 29ms | 29ms |

Paired delta distribution: {-1: 11, 0: 71, 1: 36, 2: 2}
- 59% of pairs have delta=0
- 41% have delta=-1, +1, or +2ms
- Bootstrap CI95 median: [0, 0]

### D2→G0 (TTS scheduling gap)

| Config | n | Values | p50 | p95 |
|--------|---|--------|-----|-----|
| OFF | 120 | {0: 87, 1: 5, 220-229: 28} | 0ms | 222ms |
| ON | 120 | {0: 92, 1: 6, 97-103: 22} | 0ms | 98ms |

**Bimodal distribution.** 72% of pairs have D2→G0=0ms. 28% have large gaps (OFF: ~221ms, ON: ~98ms).
B6b reduces the gap by ~2.3x when gap exists.

### T2W Dequeue → WAV

| Config | n | Flow p50 | Vocoder p50 | Sum p50 | T2W→WAV p50 | Residual p50 |
|--------|---|----------|-------------|---------|-------------|--------------|
| OFF | 120 | 135ms | 122ms | 267ms | 267ms | 0ms |
| ON | 120 | 135ms | 122ms | 267ms | 267ms | 0ms |

**Residual is 0ms at ms resolution** — Flow+Vocoder sum exactly equals T2W dequeue→WAV.
No unexplained 10ms gap.
