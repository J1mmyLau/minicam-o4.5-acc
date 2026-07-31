# F6 D0: G3→G4 Semantics Audit

**Date:** 2026-07-31
**Source:** `tools/omni/omni.cpp` @ `3023b4d`

## 1. What G3 and G4 Actually Represent

### G3: `talker_first_audio_token` (line 6732-6733)

```cpp
// Inside TTS talker loop: for (int t = 0; t < max_audio_tokens; ++t)
if (ctx_omni->e2e_stage.timestamps_ns[STAGE_talker_first_audio_token].load(...) == 0) {
    ctx_omni->e2e_stage.record(STAGE_talker_first_audio_token, ctx_omni->e2e_stage.tts_thread_generation);
}
```

**Semantics:** First audio token sampled by the TTS talker (TTS decoder). Recorded on step t=0 inside the talker's autoregressive decode loop. This is the first discrete audio codebook token from the TTS model.

### G4: `t2w_submit` (line 6977-6979)

```cpp
while ((int)ctx_omni->tts_token_buffer.size() >= CHUNK_SIZE && ctx_omni->t2w_thread_info) {
    // ... create T2WOut with 25 tokens ...
    ctx_omni->t2w_thread_info->queue.push(t2w_out);
    ctx_omni->t2w_thread_info->cv.notify_one();
    // E2E profiling: record first T2W submit
    if (ctx_omni->e2e_stage.timestamps_ns[STAGE_t2w_submit].load(...) == 0) {
        ctx_omni->e2e_stage.record(STAGE_t2w_submit, ctx_omni->e2e_stage.tts_thread_generation);
    }
    // buffer.erase(begin, begin + CHUNK_SIZE) — slide 25 tokens
}
```

**Semantics:** First batch of 25 audio tokens submitted to the Token-to-Wav (T2W) pipeline. Triggered when `tts_token_buffer.size() >= CHUNK_SIZE (25)`.

**Note:** Only non-EOS tokens count toward the buffer (EOS tokens are handled separately at line 6943-6957). So the actual number of talker steps between G3 and G4 may exceed 24 if EOS tokens are interleaved.

## 2. G3→G4 Interval Decomposition

```
G3 (t=0, 1st audio token) 
  → [token 2 generated] 
  → [token 3 generated] 
  → ... 
  → [token 25 generated — buffer.size() == 25] 
  → G4 (T2W submit)
```

| Component | Count | Per-token cost | Total |
|-----------|-------|---------------|-------|
| Token generation steps | 24 (tokens 2→25) | ~12.6ms | ~302ms |
| EOS token overhead | variable | ~12.6ms each | +N × 12.6ms |
| Queue push + notify | 1 | negligible | ~0ms |

**Nominal G3→G4 latency: ~302ms** (24 tokens × 12.6ms/token, zero EOS).

## 3. CHUNK_SIZE = 25: Semantic Constraint or Engineering Choice?

**Source:** `const int CHUNK_SIZE = 25;  // 与 Python TTSStreamingGenerator.chunk_size=25 对齐` (line 6683)

**Evidence for engineering choice:**
- Python reference implementation uses `chunk_size=25`
- `FIRST_CHUNK_SIZE = 28` (line 7359) — 25 + 3 pre_lookahead (shows chunk size is tunable)
- The T2W model receives 25-token batches, but whether it requires exactly 25 is unverified

**Evidence for semantic constraint:**
- Token-to-wav models typically expect fixed-length audio token sequences
- The 25-token window corresponds to ~1 second of audio at 25Hz
- Pre-lookahead of 3 tokens (= ~120ms overlap) suggests streaming window design

**Actual constraint: needs T2W model architecture investigation (D1).**

## 4. G3→G4 Breakdown from C6 Stability Data

From the 150-request C9 stability test (B6b enabled):
- D2→G0 median: 149ms (C6 KV_HIT: 121ms)
- G3→G4 was not directly measured in C9 (profiles had missing G3/G4 stages due to async workers)
- From B6b reconciliation data (C2): G3 median ~362ms, G4 was not recorded

## 5. Optimization Surface

If CHUNK_SIZE=25 is an engineering choice (not a semantic constraint):

| Optimization | Expected impact | Risk |
|-------------|-----------------|------|
| Reduce CHUNK_SIZE to 20 | -5 tokens × 12.6ms = -63ms | Audio quality (less context for T2W) |
| Reduce CHUNK_SIZE to 16 | -9 tokens × 12.6ms = -113ms | Higher audio quality risk |
| Use FIRST_CHUNK_SIZE=28 pattern for all chunks | +3 tokens pre-lookahead, no latency change | Already implemented for first chunk |

If CHUNK_SIZE=25 is a semantic constraint:
| Optimization | Expected impact | Risk |
|-------------|-----------------|------|
| T2W pre-ready (parallelize TTS token gen with T2W model load) | Up to -100ms | Significant complexity |
| Buffer pre-allocation | -1-2ms (minor) | Low |
| Sync elimination (lock-free queue) | -0.5-1ms (minor) | Correctness |

## 6. Verdict

**G3→G4 = Audio token accumulation wait.** First audio token (G3) → 24 more tokens generated → buffer hits 25 → T2W submit (G4). Nominal ~302ms. Whether CHUNK_SIZE=25 can be reduced depends on T2W model architecture, to be investigated in D1.
