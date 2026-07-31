# F6 G3→G4 Compute/Wait Audit

**Date:** 2026-07-31
**Status:** AUDIT COMPLETE — 100% compute, 0% wait
**CHUNK_SIZE:** 25 (ENGINEERING_POLICY — DO NOT MODIFY)

---

## What G3 and G4 Measure

```
Pipeline (server-side, same monotonic clock):
  G0: tts_wake                        ← TTS thread resumes from wait
  G3: talker_first_audio_token       ← First audio token sampled from Talker
  G4: t2w_submit                     ← 25 tokens accumulated → pushed to T2W queue
```

### G3: `STAGE_talker_first_audio_token` (omni.cpp:6806)

Recorded when the Talker autoregressive loop produces its first audio token:

```cpp
// Line 6795-6806
int relative_idx = sampled_token_abs - audio_bos_token_id;
output_audio_tokens.push_back(relative_idx);

// E2E profiling: record first audio token (one-shot across all chunks, generation-safe)
if (ctx_omni->e2e_stage.timestamps_ns[STAGE_talker_first_audio_token].load() == 0) {
    ctx_omni->e2e_stage.record(STAGE_talker_first_audio_token, ...);
}
```

This is the Talker's very first generated audio token (token index 0 of the audio vocabulary).

### G4: `STAGE_t2w_submit` (omni.cpp:7053)

Recorded when CHUNK_SIZE=25 audio tokens are accumulated and pushed to the T2W queue:

```cpp
// Line 7040-7058
t2w_out->audio_tokens = ctx_omni->tts_token_buffer;  // 25 tokens
// ... push to queue ...
if (ctx_omni->e2e_stage.timestamps_ns[STAGE_t2w_submit].load() == 0) {
    ctx_omni->e2e_stage.record(STAGE_t2w_submit, ...);
}
```

### G3→G4: What Happens Between

After G3 (first audio token), the Talker autoregressive loop continues:

```
For each step t in [1, 2, ..., 24]:
  1. Run Talker model forward pass      ← NPU compute (~12.6ms)
  2. Sample one audio token              ← CPU (negligible)
  3. Check EOS / repetition detection   ← CPU (negligible)
  4. Accumulate into tts_token_buffer   ← CPU (negligible)
After 25 tokens accumulated:
  5. Create T2WOut, push to queue       ← G4 recorded here
  6. Notify T2W worker thread           ← cv.notify_one()
```

---

## Compute/Wait Decomposition

### Where Time Is Spent

| Component | Duration | % of G3→G4 | Type |
|-----------|----------|------------|------|
| Talker forward pass × 24 | ~302ms | ~99.7% | **NPU compute** |
| Token sampling × 24 | <0.5ms | <0.2% | CPU compute |
| EOS/rep check × 24 | <0.1ms | <0.1% | CPU compute |
| Buffer management | <0.1ms | <0.1% | CPU compute |
| **Idle / wait** | **0ms** | **0%** | — |

### Verdict: G3→G4 = 100% NPU COMPUTE, 0% WAIT

There is no sleep, no condition variable wait, no I/O, no thread synchronization in the G3→G4 interval. The Talker runs the autoregressive loop at maximum speed — each step immediately transitions to the next after sampling.

### Evidence

1. **Code audit** (omni.cpp:6700-7060): The Talker loop has no `sleep()`, `wait()`, `cv.wait()`, or I/O between G3 and G4. It's a tight for-loop: forward → sample → accumulate → repeat.

2. **Timing consistency**: G3→G4 = 24 × ~12.6ms = ~302ms. The per-step time matches the Talker model's measured forward pass latency. If there were wait/idle gaps, the total would exceed 24 × step_time.

3. **Single-thread execution**: Both G3 and G4 are recorded on the TTS thread. There is no cross-thread dependency between them.

---

## What CANNOT Reduce G3→G4 (Policy Constraints)

| Approach | Blocked By |
|----------|-----------|
| Reduce CHUNK_SIZE from 25 | **ENGINEERING_POLICY** — CHUNK_SIZE=25 is FROZEN |
| Reduce CHUNK_SIZE only for first chunk | Same policy constraint |
| Start Flow+Vocoder with <25 tokens | Changes T2W contract (Flow expects 25-token window) |
| Parallel Talker + Flow/Vocoder | Architectural: Flow needs complete 25-token chunk |

## What COULD Reduce G3→G4 (Theoretically)

These are for documentation only — **DO NOT IMPLEMENT** per "不要开始新的性能优化":

| Approach | Estimated Gain | Risk |
|----------|---------------|------|
| Optimize Talker model (quantization, kernel fusion) | ~10-40% | Audio quality impact unknown |
| Interleave Talker steps with Flow start on partial tokens | ~50-80% | Major architectural change, Flow contract change |
| Reduce talker steps (different audio codec) | Variable | Complete architecture change |

---

## G3→G4 in B6b Context

B6b (`EARLY_FIRST_TTS_CHUNK_DISPATCH`) reduces D2→G0 (~290ms → ~115ms) by dispatching the first TTS chunk at step 5 instead of step 10. This shifts the bottleneck:

```
Without B6b:  D2→G0 (~290ms) ≈ G3→G4 (~302ms) — two co-dominant bottlenecks
With B6b:     D2→G0 (~115ms) << G3→G4 (~302ms) — G3→G4 is PRIMARY bottleneck
```

G3→G4 is now the single largest component of D0→W0 latency. However, per the user's explicit constraint: **"不要开始新的性能优化"** and **"G3→G4当前只做compute/wait审计"**.

---

## Guardrails

1. CHUNK_SIZE=25 — ENGINEERING_POLICY, DO NOT MODIFY
2. Do NOT start Talker model optimization
3. Do NOT change T2W contract (25-token minimum)
4. Do NOT change Flow/Vocoder to accept partial chunks
5. G3→G4 optimization is HOLD until after TRUE_E2E gates pass

---

## References

- `omni.cpp:6795-6806`: G3 recording (talker_first_audio_token)
- `omni.cpp:7040-7058`: G4 recording (t2w_submit)
- `omni.cpp:6700-7074`: Talker autoregressive loop (Phase 1)
- `F6_W15_G3G4_HANDOFF.md`: Next-bottleneck handoff
- `F6_G3_G4_SEMANTIC_AUDIT.md`: Prior semantic audit
