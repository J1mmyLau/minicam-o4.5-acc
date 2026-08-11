# F6 C4: A7 Correctness Gate — Final Report

**Date:** 2026-07-31
**Commit:** `3023b4d` (includes OMNI_TTS_FIRST_CHUNK_STEP env var)
**Script:** `/tmp/f6_a7_v2.py`
**Data:** `/tmp/f6_a7_v2/`

## Test Design

3 clean server sessions (no modality switches within session):
- Session A: 7 text-only (KV HIT, `use_tts=False`)
- Session B: 7 audio understanding (KV MISS, `use_tts=False`)
- Session C: 6 TTS (KV MISS, `use_tts=True`)

Total: **20 requests** across text, audio, and TTS modalities.

## Results

| Metric | Value | Gate |
|--------|-------|------|
| Profiles | 20/20 | PASS |
| Critical stages (all 4) | 20/20 | PASS |
| Negative durations | 0 | PASS |
| Stale writes | 19 (TTS only) | ADVISORY |
| Cross-request writes | 19 (TTS only) | ADVISORY |
| Text profiles stale/cross | 0/0 | PASS |
| Audio profiles stale/cross | 0/0 | PASS |
| CANN errors | 0 | PASS |
| Crashes | 0 | PASS |

## Stale/Cross-Request Analysis

Root cause: async TTS pipeline (talker, T2W, flow, vocoder workers) continue processing
after the next request begins. The generation_id guard **correctly** detects and prevents
stale data from corrupting current request profiles. This is the instrumentation working
as designed, not a bug.

Evidence:
- TTS gen=1: 0 stale, 0 cross-request, FULL async stage coverage (12 stages)
- TTS gen=2: 1 stale, 1 cross, missing downstream stages
- TTS gen=6: 7 stale, 7 cross, only 5 stages

The stale count grows monotonically because the async pipeline accumulates lag.
Each new request starts before all prior async workers have completed.

**Verdict: NOT FIXABLE without redesigning the profiling for per-request async tracking.**
The generation_id guard is the correct behavior.

## A7 Gate Verdict: **PASS** (with advisory on async TTS worker design limitation)
