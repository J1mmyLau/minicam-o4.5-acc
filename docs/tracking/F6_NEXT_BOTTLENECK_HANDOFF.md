# F6 Z11: Next Bottleneck Handoff

**Date:** 2026-07-31
**Source:** D0 audit (`F6_D0_G3G4_SEMANTICS.md`), `tools/omni/omni.cpp`

## NEXT_BOTTLENECK = TALKER_AUDIO_TOKEN_ACCUMULATION

### Event Semantics

```
G3 (talker_first_audio_token)
  → TTS talker generates audio tokens in autoregressive loop
  → Each non-EOS token is pushed to tts_token_buffer
  → When buffer.size() >= CHUNK_SIZE (25), T2W submit fires
  → G4 (t2w_submit)
```

| Property | Value |
|----------|-------|
| **Start event** | G3: first audio token sampled by TTS talker |
| **End event** | G4: 25-audio-token batch submitted to T2W queue |
| **What happens** | Talker generates 24 more audio tokens (each ~12.6ms compute) |
| **Current nominal latency** | ~302ms (24 steps × ~12.6ms, zero EOS between) |
| **Measured in C9** | G3→G4 covered in 3/121 profiles only (async worker gap) |

### CHUNK_SIZE = 25: Engineering Analysis

```cpp
// tools/omni/omni.cpp:6683
const int CHUNK_SIZE = 25;  // 与 Python TTSStreamingGenerator.chunk_size=25 对齐
```

| Aspect | Evidence |
|--------|----------|
| **Origin** | Inherited from Python `TTSStreamingGenerator.chunk_size=25` |
| **Audio duration** | 25 tokens = 1 second of audio (@ 40ms/token) |
| **Overlap** | PRE_LOOKAHEAD = 3 tokens (~120ms) for cross-chunk smoothing |
| **T2W model input** | 28 tokens (25 + 3 lookahead) processed by flow matching model |
| **Constraint type** | **ENGINEERING_POLICY** — not a hard model architecture requirement |

**Likely reducible.** The flow matching model receives 28 tokens in a sliding window. Reducing CHUNK_SIZE would:
- Reduce first chunk latency: every token reduction saves ~12.6ms
- Reduce T2W input context from 28 to n+3 tokens
- Potentially degrade audio quality at chunk boundaries (less context for smooth flow)

### Current Pipeline State (with B6b)

```
D0 → D1 → D2 ──── G0 → G1 → G2 → G3 ───────── G4 → Q0 → W0 → W1
 15    46    82     183   188   188   221         221+302 = 523    ?    ?   ms (candidate)
                   [B6b -139ms zone]              [next bottleneck ~302ms]
```

### Optimization Candidates (DEFERRED, not active)

| Candidate | Expected saving | Risk | Effort |
|-----------|----------------|------|--------|
| CHUNK_SIZE=20 (reduce 5 tokens) | ~63ms | Medium — less T2W context, potential boundary artifacts | Medium |
| CHUNK_SIZE=16 (reduce 9 tokens) | ~113ms | High — significant quality risk | Medium |
| FIRST_CHUNK_SIZE=20 (hybrid) | ~63ms first chunk only | Low — first chunk only, same pattern as B6b | Low |
| T2W pre-ready (parallelize model load with token accumulation) | ~50-100ms | Low (if implemented correctly) | High |
| Buffer pre-allocation | ~1-2ms | None | Low |
| Lock-free T2W queue | ~0.5-1ms | Correctness risk | Medium |

### Future Experiment Gates (when user unblocks D2-D5)

1. **Offline replay**: Record audio token sequences, replay through T2W with varied CHUNK_SIZE
2. **Quality regression**: Compare WAV output for CHUNK_SIZE ∈ {25, 20, 16, 12}
3. **Perceptual study**: Blind listening test at reduced chunk sizes
4. **T2W model compatibility**: Verify flow matching model accepts variable token counts

### Current Status

```
AUDIO_ACCUMULATION_OPTIMIZATION = DEFERRED_BY_USER_SCOPE
CHUNK_SIZE_25 = ENGINEERING_POLICY_CONFIRMED
NEXT_STEP = FREEZE_B6B_FIRST
```

### Safety Constraints

- Do NOT modify CHUNK_SIZE without T2W model verification
- Do NOT change Talker token semantics
- Do NOT train DSpark for this bottleneck
- Do NOT default smaller windows without audio quality gate
- Channel B6b benefit first (139ms D2→G0 already delivered), then assess remaining G3→G4 opportunity
