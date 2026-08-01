# F6 Phase 3 — N8 Server Smoke Test Report (S7)

**Date:** 2026-08-01
**HEAD:** `6320bd3` (RelWithDebInfo build)
**Binary:** `build-f6-phase3-relwithdebinfo/bin/llama-omni-server`
**SHA256:** `c13c04a081850c2eb46fb828775603672acd86518c6ecd9de324635831ed04bc`

## Executive Summary

**Verdict: PASS (5/5 + 2/2 enhanced)**

N8 server async smoke test completed via production WebSocket API. All text-only, KV MISS, and TTS-enabled requests processed successfully with correct profiles generated.

## Test Configuration

| Setting | Value |
|---------|-------|
| Server port | 8085 |
| Server PID | 789709 |
| Model | MiniCPM-o-4_5-Q4_K_M.gguf |
| Context | 2048 |
| NPU layers | 99 |
| OMNI_TTS_FIRST_CHUNK_STEP | 10 |
| OMNI_E2E_PROFILE | 1 |
| OMNI_E2E_PROFILE_DIR | /tmp/f6_phase3_n8_smoke/profiles |
| F6_PHASE3_TALKER_STATS | 1 |

## Test Results

### Phase 1: Text-Only 5-Request Smoke (KV HIT / Consecutive)

Single WebSocket session, 5 consecutive turn_based requests:

| # | Label | Type | Text Len | Deltas | Elapsed | Prefill | Generate | n_tokens | KV Cache | Status |
|---|-------|------|----------|--------|---------|---------|----------|----------|----------|--------|
| 1 | short_zh_1 | Short ZH | 29 | 2 text | 27016ms | 4119ms | 22896ms | 39 | 61 | ✅ |
| 2 | short_zh_2 | Short ZH | 9 | 1 text | 10153ms | 0ms | 10152ms | 26 | 87 | ✅ |
| 3 | long_zh | Long ZH | 208 | 13 text | 134031ms | 0ms | 134030ms | 185 | 272 | ✅ |
| 4 | en | EN | 31 | 1 text | 11752ms | 0ms | 11751ms | 32 | 304 | ✅ |
| 5 | mixed_zh_en | Mixed ZH+EN | 215 | 12 text | 121612ms | 0ms | 121611ms | 146 | 450 | ✅ |

**KV HIT**: Requests 2-5 all show prefill=0ms, confirming KV cache reuse of system prompt.
**Consecutive**: All 5 requests processed on same session, KV cache grows cleanly 61→87→272→304→450.

### Phase 2: KV MISS (Fresh Session)

| # | Label | Type | Text Len | Elapsed | Prefill | Generate | n_tokens | KV Cache | Status |
|---|-------|------|----------|---------|---------|----------|----------|----------|--------|
| 1 | kv_miss_zh | Short ZH | 52 | 39664ms | 4950ms | 34713ms | 54 | 76 | ✅ |

**KV MISS**: Fresh session with prefill=4950ms, confirming full system prompt prefill executed.

### Phase 3: TTS-Enabled (Full C8 Instrumentation)

| # | Label | Text Len | Text Deltas | Audio Deltas | Elapsed | Prefill | Generate | n_tokens | Status |
|---|-------|----------|-------------|--------------|---------|---------|----------|----------|--------|
| 1 | tts_zh_short | 45 | 3 | 4 | 53854ms | 0ms | 32239ms | 52 | ✅ |

**TTS Profile**: 18 stages recorded including Flow (9547ms) and Vocoder (639ms). Audio profile with 124 talker steps generated.

### Profile Files Generated

| File | Size | Content |
|------|------|---------|
| e2e_0000.json | 858B | TTS sync profile: 18 stages (full Flow/Vocoder) |
| e2e_0000_audio.json | 16KB | TTS audio profile: 7 async stages + 124 talker steps |
| e2e_0001.json | 364B | Text-only sync: 4 stages |
| e2e_0002.json | 364B | Text-only sync: 4 stages |
| e2e_0003.json | 364B | Text-only sync: 4 stages |
| e2e_0004.json | 364B | Text-only sync: 4 stages |
| e2e_0005.json | 364B | KV MISS sync: 4 stages |

### Rejection Counters (Ring Buffer Safety)

| Counter | Value | Expected | Status |
|---------|-------|----------|--------|
| late_write_rejected | 0 | May be >0 (benign) | ✅ |
| write_after_finalize | 0 | Must be 0 | ✅ |
| invalid_generation_write | 0 | Must be 0 | ✅ |

### TTS Profile Timeline

```
Stage                    Time (ms)    Delta from start
──────────────────────   ─────────    ───────────────
request_received                0                0
decode_loop_begin             988              988
llm_first_decode_step        1960             1960
llm_first_token              2852             2852
tts_wake                    11401            11401
tts_first_decode            11571            11571
talker_start                11571            11571
t2w_submit (Q0)             11902            11902
t2w_dequeue (Q1)            11902            11902
flow_start (F0)             11902            11902
flow_end (F1)               21449            21449
vocoder_start (V0)          21449            21449
vocoder_end (V1)            22088            22088
wav_ready (W0)              22089            22089
client_first_audio (C0)     22090            22090

Key intervals:
  Flow duration:        9547 ms
  Vocoder duration:      639 ms
  T2W queue+compute:   10187 ms
  LLM prefill:           892 ms
  LLM→TTS handoff:      8549 ms
  Talker→Audio:        10519 ms
```

## Coverage

| Requirement | Status | Notes |
|-------------|--------|-------|
| 2 short ZH | ✅ | Text responses correct |
| 1 long ZH | ✅ | 208 chars, 13 text deltas |
| 1 EN | ✅ | English response correct |
| 1 mixed ZH+EN | ✅ | Bilingual response correct |
| KV HIT | ✅ | Requests 2-5: prefill=0ms |
| KV MISS | ✅ | Fresh session: prefill=4950ms |
| Consecutive requests | ✅ | 5 requests on same session |
| Voice A/B | ⚠️ SKIPPED | Requires different reference audio (single voice tested) |

## Server Health

- No crashes, no errors, no warnings
- Session lifecycle: created→active→disconnected, clean shutdown
- WebSocket protocol: session.init → session.created → input.append (×N) → response.done → session.closed
- PID file stable: `/tmp/f6_phase3_n8_server.pid` → 789709
- Health check: `{"engine":"comni","status":"ok"}`

## Test Scripts

| Script | Path |
|--------|------|
| 5-request smoke | `/tmp/f6_phase3_n8_smoke/ws_smoke_test.py` |
| Enhanced (KV MISS + TTS) | `/tmp/f6_phase3_n8_smoke/ws_smoke_enhanced.py` |
| Results | `/tmp/f6_phase3_n8_smoke/smoke_results.json` |
| Enhanced results | `/tmp/f6_phase3_n8_smoke/smoke_enhanced_results.json` |
| Event log | `/tmp/f6_phase3_n8_smoke/smoke_events.json` |

## Gate Decision

**N8: PASS** — Server async smoke test completes with 7/7 requests across text-only, KV MISS, and TTS-enabled modes. Rejection counters all zero. No server errors. Full C8 Flow/Vocoder instrumentation confirmed working.
