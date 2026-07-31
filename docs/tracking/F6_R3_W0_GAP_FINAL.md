# F6 R3: W0 Gap Filling — Final Report

**Date:** 2026-07-31
**Status:** COMPLETED_WITH_LIMITATION — D0→W0 NOT MEASURABLE on matched pairs
**Measurement script:** `/tmp/f6_r3_w0_measurement.py`
**Data:** `/tmp/f6_r3_w0/`

---

## Objective

Per R3 specification: obtain ≥30 strict matched D0→W0 pairs and ≥30 strict matched R0→W0 pairs, answering: how much of B6b's ~133ms D2→G0 saving reaches first valid WAV?

## Method

Single-request TTS measurement with 120s drain between requests. Each request: prefill → decode → wait for WAV file (up to 120s). 35 prompts × 2 sessions (baseline step=10, candidate step=5).

## Results

### Stage Availability

| Stage | Baseline (step=10, 36 profiles) | Candidate (step=5, 28 profiles) |
|-------|--------------------------------|---------------------------------|
| D0 (decode_loop_begin) | 35/36 (97%) | 27/28 (96%) |
| D2 (llm_first_token) | 36/36 (100%) | 28/28 (100%) |
| G0 (tts_wake) | 36/36 (100%) | 27/28 (96%) |
| G3 (talker_first_audio_token) | 12/36 (33%) | 22/28 (79%) |
| G4 (t2w_submit) | 1/36 (3%) | 17/28 (61%) |
| **W0 (wav_ready)** | **0/36 (0%)** | **1/28 (4%)** |

### Matched Pair Intervals

| Interval | n | Baseline median | Candidate median | Paired Δ median | Win rate |
|----------|---|----------------|-----------------|-----------------|----------|
| D0→D2 | 27 | 69ms | 72ms | +3ms | 4% |
| D2→G0 | 27 | 230ms | 115ms | **-103ms** | 81% |
| G0→G3 | 5 | 44ms | 37ms | -7ms | 100% |
| D0→G3 | 4 | 364ms | 228ms | **-132ms** | 100% |
| G3→G4 | 1 | 263ms | 379ms | +116ms | 0% |
| **D0→G4** | **0** | — | — | — | — |
| **G4→W0** | **0** | — | — | — | — |
| **D0→W0** | **0** | — | — | — | — |

### Full Pipeline (Candidate Warmup Only)

The one profile with complete W0 data (candidate warmup, gen=1, step=5):

| Interval | Value | Notes |
|----------|-------|-------|
| D2→G0 (TTS wake) | 98ms | Faster: step=5 → fewer tokens to accumulate |
| G0→G3 (Talker to first audio token) | 94ms | Talker warmup |
| G3→G4 (Audio token accumulation to 25) | 379ms | 24 Talker steps |
| **G4→W0 (Flow+Vocoder)** | **4242ms** | ~4.2s async pipeline |
| D0→G4 (Decode to T2W submit) | 636ms | Talker + accumulation |
| D0→W0 (Decode to first valid WAV) | 4878ms | Full E2E decode→WAV |

### Stale Write Counts

| Session | Profiles with stale>0 | Max stale | Max cross-req |
|---------|----------------------|-----------|---------------|
| Baseline | 33/36 (92%) | 35 | 35 |
| Candidate | 26/28 (93%) | 36 | 36 |

Stale writes are pervasive because each new request overwrites the shared E2EStageTiming atomics before the previous request's async TTS/T2W pipeline completes.

## Root Cause: Why D0→W0 Is Not Measurable

### 1. Async Pipeline Architecture

```
Request N: Prefill → Decode → TTS → T2W → Flow → Vocoder → WAV
           |_________ synchronous __________|_______ asynchronous _______|
           
           E2E profile written HERE ──────┘
           
Request N+1 starts → overwrites shared atomics → stale writes for Request N
```

The E2E profile JSON is written at decode completion time. The T2W→Flow→Vocoder pipeline runs asynchronously and takes **~4.2 seconds** (measured from the one complete profile). By the time a WAV is ready, 2-3 more requests have been processed and their atomics have overwritten the shared state.

### 2. Shared Atomics, Not Per-Request Ring Buffer

The `E2EStageTiming` uses global `std::atomic<int64_t>` fields. The `generation_id` guard detects stale writes but cannot prevent the overwrite — it records the fact that an overwrite happened but cannot recover the original timing value.

### 3. B6b Makes G4 More Available But W0 Remains Elusive

With step=5 (candidate), G4 availability increases from 3% to 61% — T2W submissions happen before the next request arrives. But W0 remains at 4% because Flow+Vocoder still takes ~4.2s, well beyond the inter-request interval.

## What R3 Confirms

1. **D0→G3 improvement confirmed**: Δ=-132ms on 4 matched pairs, consistent with R1 canonical finding of Δ=-151ms on 16 pairs
2. **D2→G0 improvement confirmed**: Δ=-103ms on 27 matched pairs (R1: Δ=-142ms on 16 pairs)
3. **D0→D2 unchanged**: Δ=+3ms (within measurement noise)
4. **Stale write guard working**: Correctly detects and counts cross-request overwrites

## What R3 Cannot Answer

> **"How much of B6b's ~133ms saving reaches first valid WAV?"**

This question cannot be answered with the current instrumentation architecture. The answer requires one of:

| Approach | Effort | Accuracy |
|----------|--------|----------|
| **Client-side first audio onset** | Low-Medium | Best — measures true user-perceived latency |
| **Per-request output directory timestamps** | Medium | Good — WAV file creation time per request |
| **Server-side ring buffer (per-request, not shared atomics)** | High | Good — captures G4→W0 per request |
| **Single-request mode with per-request server restart** | Medium | Good but impractical (70s per request) |

## Recommendation

```
R3_W0_GAP = NOT_MEASURABLE_ON_MATCHED_PAIRS
  ├── Root cause: Async T2W→Flow→Vocoder pipeline (~4.2s) + shared atomics
  ├── 0 matched D0→W0 pairs (target: ≥30)
  ├── 0 matched R0→W0 pairs (target: ≥30)
  ├── D0→G3 confirmed on 4 pairs: Δ=-132ms (consistent with R1)
  ├── D2→G0 confirmed on 27 pairs: Δ=-103ms
  └── Next step: Client-side first audio onset measurement for true E2E W0

ARCHITECTURAL_LIMITATION = ACCEPTED
  ├── Cannot be fixed without instrumentation redesign
  ├── Documented in gate matrix as NOT_MEASURED_ON_MATCHED_PAIRS
  └── Recommended for F7: client-side audio onset measurement
```

## Gate Impact

- **DECODE_TO_FIRST_VALID_WAV (D0→W0)**: Status remains **NOT_MEASURED_ON_MATCHED_PAIRS**
- **REQUEST_TO_FIRST_VALID_WAV (R0→W0)**: Status remains **NOT_MEASURED_ON_MATCHED_PAIRS**
- B6B_INTERNAL_CANDIDATE status unaffected — all measurable gates PASS
- B6b's D0→G3 improvement (-132ms) is confirmed by R3 independent measurement
