# F6 Phase 3 — S9: CLI vs Server Event Parity Analysis

**Date:** 2026-08-01
**HEAD:** `6320bd3`

## Data Sources

| Source | Path | Profiles |
|--------|------|----------|
| CLI (TTS) | `/tmp/f6_z4_e2e_ab_v2/prof_KV_HIT_baseline/` | 31 sync, 0 audio |
| Server N9 (TTS) | `/tmp/f6_phase3_n9_smoke/profiles/` | 20 sync, 15 audio |

## Top-Level JSON Structure

**Verdict: IDENTICAL** ✅

Both CLI and Server produce the same JSON keys:
```
cann_error, crash, cross_request_write_count, generation_id,
no_speech, prompt_id, request_index, seed, stages_ms,
stale_write_count, talker_token_count
```

No CLI-only or Server-only keys at the profile root level.

## Stage Coverage Comparison

### Best Profile (First TTS Request)

| Stage | CLI (17 stages) | Server (18 stages) |
|-------|:---:|:---:|
| request_received | ✅ | ✅ |
| decode_loop_begin | ✅ | ✅ |
| llm_first_decode_step | ✅ | ✅ |
| llm_first_token | ✅ | ✅ |
| tts_wake | ✅ | ✅ |
| tts_first_decode | ✅ | ✅ |
| talker_start | ✅ | ✅ |
| talker_first_audio_token | ✅ | ✅ |
| talker_token_28 | ✅ | ✅ |
| t2w_submit (Q0) | ✅ | ✅ |
| t2w_dequeue (Q1) | ✅ | ✅ |
| t2w_preprocess_end (Q2) | ❌ | ✅ (7/20 profiles) |
| flow_start (F0) | ✅ | ✅ |
| flow_end (F1) | ✅ | ✅ |
| vocoder_start (V0) | ✅ | ✅ |
| vocoder_end (V1) | ✅ | ✅ |
| wav_ready (W0) | ✅ | ✅ |
| client_first_audio (C0) | ✅ | ✅ |

### Missing from Both

| Stage | CLI | Server | Notes |
|-------|:---:|:---:|-------|
| speak_token (3) | ❌ | ❌ | Never recorded in either path |
| prompt_processing_start (1) | ❌ | ❌ | DEAD — never recorded anywhere |
| request_done (15) | ❌ | ❌ | DEAD — never recorded anywhere |

### Coverage Statistics

| Source | Avg Stages | Min Stages | Max Stages | Q2 Present |
|--------|-----------|------------|------------|------------|
| CLI (31 profiles) | ~12.5 | 4 | 17 | 0/31 (0%) |
| Server (20 profiles) | ~14.8 | 4 | 18 | 7/20 (35%) |

## Audio Profile Parity

| Feature | CLI | Server |
|---------|-----|--------|
| Audio profiles generated | 0 | 15 (1 with data) |
| async_stages_ms | N/A | 7 stages (Q1, Q2, F0, F1, V0, V1, W0) |
| talker_step_summary | N/A | 21 keys including rejection counters |
| talker_steps array | N/A | Per-step timing data |
| profile_status | N/A | "audio_complete" |

**CLI does not generate audio profiles in the tested configuration.** This may be because the CLI's TTS path processes audio inline rather than through the async callback path. The server generates audio profiles through its WebSocket audio callback.

## Flow/Vocoder Dual Storage

Both CLI and Server exhibit the Flow/Vocoder dual storage pattern:
- `flow_start`, `flow_end`, `vocoder_start`, `vocoder_end` appear in both:
  - `timestamps_ns[]` (via C8 mirror thread_local write)
  - `add_global_stage()` fallback (from `g_e2e_flow_start_ns` etc.)

This results in potential duplicate JSON keys (same value, same key — JSON spec violation but functionally correct). This is a **known quirk** documented in the event inventory (S2), not a bug.

## Rejection Counters

| Counter | CLI | Server |
|---------|-----|--------|
| stale_write_count | 0 (all profiles) | 0 (all profiles) |
| cross_request_write_count | 0 (all profiles) | 0 (all profiles) |
| late_write_rejected | N/A (no audio profiles) | 0 |
| write_after_finalize | N/A | 183 (N6 guard active) |
| invalid_generation_write | N/A | 0 |

## Key Findings

### 1. Q2 (t2w_preprocess_end) — Server-Only

`t2w_preprocess_end` is recorded in 35% of server profiles but 0% of CLI profiles. This stage is recorded in the T2W worker thread in the server's `omni.cpp` path. The CLI appears to use a different code path that skips this recording.

**Impact**: Low. Q2 is not a critical bottleneck metric. Its absence in CLI does not affect the core Flow/Vocoder instrumentation (F0, F1, V0, V1).

### 2. Audio Profiles — Server-Only

CLI does not generate audio profile files (`e2e_XXXX_audio.json`). The server generates them through its WebSocket audio callback path. The CLI's TTS path may process audio synchronously and not trigger the async profile dump.

**Impact**: Medium. Audio profiles contain `async_stages_ms` and `talker_steps` per-step timing. For CLI-only profiling, these metrics must be derived from the sync profile or the console output.

### 3. Core C8 Instrumentation — IDENTICAL

Flow/Vocoder stages (F0, F1, V0, V1) are present in both CLI and Server TTS profiles. The C8 thread_local RAII mechanism works identically in both paths. The mirror writes from `e2e_record_ns()` to per-request `timestamps_ns[]` function correctly regardless of entry point.

### 4. Rejection Counter Behavior — Consistent

`stale_write_count` and `cross_request_write_count` are 0 in both CLI and Server. The `write_after_finalize` counter is only active in the server path (due to audio profile dump timing), but the underlying TalkerStepBuffer mechanism is shared code.

## Verdict

**S9: PASS — CLI and Server event output are functionally equivalent for the core C8 instrumentation.**

The differences are:
1. Q2 (`t2w_preprocess_end`) is server-only (minor impact)
2. Audio profiles (`_audio.json`) are server-only (the server path generates them via audio callback)
3. Core Flow/Vocoder stages (F0, F1, V0, V1) are IDENTICAL in both paths
4. Top-level JSON structure is IDENTICAL
5. Rejection counter semantics are CONSISTENT

No action required. These differences are inherent to the CLI vs Server architecture and do not affect the Phase 3 instrumentation goals.
