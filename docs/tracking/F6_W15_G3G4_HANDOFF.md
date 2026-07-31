# F6 W15: G3→G4 Next-Bottleneck Handoff

**Date:** 2026-07-31
**Status:** HANDOFF COMPLETE
**Observability Tag:** `fp16-f6-w0-observability-20260731` (`c3b3440`)
**B6b Internal Tag:** `fp16-f6-early-tts-dispatch-internal-20260731` (`00a2755`) — UNCHANGED

---

## W0 Observability Closeout Summary

### Problem
W0 (STAGE_wav_ready) was BROKEN — only 1/64 profiles had `wav_ready`. Root cause: three lifecycle defects in E2E stage timing.

### Fixes Applied (W5)

| Fix | Description | Files |
|-----|-------------|-------|
| **Fix 1** | `generation_id` + `request_index` through T2W queue | `omni.h:105-106`, `omni.cpp` (18 sites) |
| **Fix 2** | Audio completion profile (`e2e_XXXX_audio.json`) at W0 arrival | `omni.cpp:1016-1073`, `omni.cpp:11043-11055` |
| **Fix 2 hardening** | W0 timestamp survives concurrent `reset()` via direct parameter | `omni.cpp:1016,1041-1044` |
| **Global fallback fix** | Per-stage check before global atomics — no duplicate JSON keys | `omni.cpp:1059-1072` |
| **Fix 3** | Flow/vocoder per-stage timestamps (not global atomics) | **DEFERRED** |

### Verified (W8-W11)

| Gate | Result | Evidence |
|------|--------|----------|
| W8: W0 smoke | 5/5 (100%) W0 presence | `runs/w8_smoke/e2e_0000_audio.json` |
| W9: Overhead | ~55ns/token, ~500μs/dump | Static analysis of `record()`/`record_unsafe()`/JSON dump |
| W11: Pass-through | Δ=0ms (same clock, same atomic) | 3 pairs where both partial and audio profiles have wav_ready |

---

## Current Bottleneck: G3→G4 (Talker Audio Token Accumulation)

```
Pipeline (server-side, same monotonic clock):
  R0: request_received
  D0: decode_loop_begin
  D2: llm_first_speak_token
  G0: tts_wake
  G3: talker_first_audio_token     ← first audio token from Talker
  G4: t2w_submit                   ← 25 tokens accumulated → T2W queued
  Q0: t2w_dequeue
  Flow: flow_start → flow_end
  Vocoder: vocoder_start → vocoder_end
  W0: wav_ready                    ← first valid WAV buffer ← NOW OBSERVABLE
  W1: client_first_audio           ← emitted to client
```

### G3→G4 Gap

| Metric | Value | Notes |
|--------|-------|-------|
| G3→G4 latency | ~302ms | 24 talker token steps × ~12.6ms each |
| CHUNK_SIZE | 25 tokens | ENGINEERING_POLICY — must stay at 25 |
| Tokens to accumulate after G3 | 24 | (25 - 1, G3 is the first token) |
| Talker step time | ~12.6ms | CPU-only talker (CANN lowering bug fixed at `7df34a1`) |

### B6b Effect on G3→G4

B6b (`EARLY_FIRST_TTS_CHUNK_DISPATCH`) reduces D2→G0 by ~55% (step 10→5 for first chunk). This shifts the bottleneck downstream to G3→G4:

- **Without B6b**: D2→G0 dominates (~290ms), G3→G4 is secondary (~302ms)
- **With B6b**: D2→G0 reduced (~115ms), G3→G4 becomes the PRIMARY bottleneck (~302ms)
- **Net gain**: ~175ms improvement in D2→G0, but G3→G4 remains at ~302ms

### Why G3→G4 Matters

G3→G4 is the time from "first audio token exists" to "enough tokens (25) to start Flow+Vocoder." Every millisecond saved in G3→G4 directly reduces wav_ready (W0). With B6b accelerating the LLM→TTS wake-up, the audio token accumulation becomes the dominant first-audio component.

---

## Observability Infrastructure for G3→G4 Optimization

### What's Now Measurable

| Measurement | How | Where |
|------------|-----|-------|
| G3 timestamp | `STAGE_talker_first_audio_token` | Per-stage `timestamps_ns[]` |
| G4 timestamp | `STAGE_t2w_submit` (recorded at T2W queue push) | Per-stage `timestamps_ns[]` |
| G3→G4 delta | `G4 - G3` (same clock, same thread) | Partial profile or audio profile |
| W0 timestamp | `STAGE_wav_ready` (recorded at first WAV) | Audio completion profile |
| Full pipeline | D0→W0 (all 16 stages) | Partial + audio profiles combined |

### Profile Files

| File | Content | When Written | Thread |
|------|---------|-------------|--------|
| `e2e_XXXX.json` | Sync stages (D0..G4) + partial async | Decode return | HTTP handler |
| `e2e_XXXX_audio.json` | Async stages (Q0..W1) | First WAV ready | T2W worker |

Both files use the same `request_index` for correlation.

### Enabling Profiling

```bash
export OMNI_E2E_PROFILE=1              # FULL mode (per-request JSON)
export OMNI_E2E_PROFILE=summary        # SUMMARY mode (aggregate only)
export OMNI_E2E_PROFILE_DIR=/path/to/profiles
```

---

## What's Deferred

| Item | Reason | Priority |
|------|--------|----------|
| **Fix 3**: Flow/vocoder per-stage timestamps | Global atomics cleared by reset() — back-to-back requests lose flow/vocoder data | Medium (non-blocking for single-request profiling) |
| **Server multi-decode**: Consecutive request handling | Server creates TTS/T2W threads once; `joinable()` prevents re-creation | Medium (needed for production A/B) |
| **D0=0 in non-async path**: `STAGE_decode_loop_begin` not recorded | Only recorded in `if (ctx_omni->async)` block — non-streaming mode misses D0 | Low (use `llm_first_decode_step` as alternative) |
| **Full 120-pair A/B**: True B6b E2E matched measurement | Requires multi-decode server + fixed-prompt harness + 4h runtime | Medium (infrastructure validated with 5-pair pilot) |

---

## Guardrails (Carry Forward)

1. B6b tag `fp16-f6-early-tts-dispatch-internal-20260731` at `00a2755` — DO NOT MOVE
2. CHUNK_SIZE=25 — ENGINEERING_POLICY, DO NOT MODIFY
3. Do NOT train DSpark
4. Do NOT start new performance optimizations
5. B6b status: OPT_IN_READY / DEFAULT_OFF
6. No DEFAULT_ON, OFFICIAL_AUDIO_QUALITY_PASS, or OFFICIAL_FIRST_AUDIO_RESULT claims

---

## Binary Fingerprint

```
SHA256: 42c97f40c0738366e076f6e3352f8f4931e2e8898e29f1a688ad571e794398a3
Build:  cmake --build . --target llama-omni-server -j8
Branch: perf/f6-decode-to-speak
Commit: c3b3440
```

---

## Next Phase: G3→G4 Audio Accumulation Optimization

**Status: UNLOCKED** — W0 observability restored. The infrastructure now supports:

1. Measuring G3→G4 directly (both timestamps on same clock)
2. Verifying improvements via W0 delta (wav_ready reduction)
3. A/B comparison with matched pairs (when multi-decode server is available)
4. Pass-through reconciliation (Δ=0ms guarantee from same atomic)

**Recommended first action**: Fix 3 (flow/vocoder per-stage timestamps) to enable back-to-back profiling. Then address server multi-decode to enable efficient A/B testing. Then optimize G3→G4 audio token accumulation.
