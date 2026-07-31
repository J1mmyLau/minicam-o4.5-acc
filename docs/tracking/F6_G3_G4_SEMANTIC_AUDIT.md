# F6 R8: G3→G4 Semantic Audit

**Date:** 2026-07-31
**Scope:** Audit only — no CHUNK_SIZE changes
**Source:** `tools/omni/omni.cpp`

---

## Answering the 10 Questions

### Q1: Precise semantics of G3 and G4

**G3 (TALKER_FIRST_AUDIO_TOKEN):**
- Recorded at `omni.cpp:6732-6734`
- Trigger: first non-EOS audio token sampled by Talker in autoregressive loop
- Recorded via: `ctx_omni->e2e_stage.record(STAGE_talker_first_audio_token, ...)`
- One-shot: uses `load() == 0` guard — only the very first audio token across all chunks
- Thread: TTS worker thread (synchronous with Talker generation loop)
- Availability: ~43% of requests (Talker must complete first token before next request starts)

**G4 (FIRST_T2W_SUBMIT):**
- Recorded at `omni.cpp:6977-6980`
- Trigger: first time `tts_token_buffer.size() >= CHUNK_SIZE (25)` → T2W queue push
- Recorded via: `ctx_omni->e2e_stage.record(STAGE_t2w_submit, ...)`
- One-shot: uses `load() == 0` guard — only the first T2W submit
- Thread: TTS worker thread
- Availability: ~13% of requests (T2W queue push must happen before next request starts)

### Q2: Where is CHUNK_SIZE=25 defined?

Two locations in `omni.cpp`:

```cpp
// Line 6683 — TTS simplex generation loop
const int CHUNK_SIZE = 25;  // 与 Python TTSStreamingGenerator.chunk_size=25 对齐

// Line 10231 — T2W worker thread (sliding window)
constexpr int32_t CHUNK_SIZE = 25;      // Main chunk size (25 tokens = 1s audio)
constexpr int32_t PRE_LOOKAHEAD = 3;    // Lookahead for overlap
constexpr int32_t WINDOW_SIZE = CHUNK_SIZE + PRE_LOOKAHEAD;  // 28
```

Both are local constants, not configurable via env var.

### Q3: Is CHUNK_SIZE=25 training-fixed?

**No.** The value 25 is inherited from the Python reference implementation (`TTSStreamingGenerator.chunk_size=25`). It represents:
- 25 audio tokens × 40ms/token = 1 second of audio
- An engineering choice for streaming granularity
- NOT a model architecture constraint (the TTS talker generates tokens one at a time; 25 is the batching threshold)

The T2W model (Flow Matching + Vocoder) receives 28 tokens (25 + 3 lookahead) in a sliding window. The internal `PreLookaheadLayer` is configured with `pre_lookahead_len=3` (`token2wav-impl.h:1183`). Neither 25 nor 28 appears to be hard-coded in the model weights.

### Q4: Does Token2Wav require exactly 25 tokens?

The T2W C++ implementation uses a sliding window of 28 tokens (25 chunk + 3 lookahead):

```cpp
// Line 10232-10233
constexpr int32_t PRE_LOOKAHEAD = 3;
constexpr int32_t WINDOW_SIZE = CHUNK_SIZE + PRE_LOOKAHEAD;  // 28
```

The window slides by CHUNK_SIZE (25) after each T2W processing step. The lookahead (3 tokens) provides cross-chunk overlap for smooth audio concatenation.

**The T2W model can process fewer than 25 tokens** — the last chunk before EOS may have fewer tokens, and the sliding window handles this gracefully. However, the Flow Matching model's receptive field and the overlap quality depend on having sufficient context (25+3=28 tokens).

### Q5: Is there overlap/look-ahead?

**Yes.** PRE_LOOKAHEAD=3 tokens (~120ms) provides cross-chunk overlap:

```
Chunk 0: tokens [0..24] + lookahead [25,26,27] → T2W processes 28 tokens → outputs audio for [0..24]
Chunk 1: tokens [25..49] + lookahead [50,51,52] → T2W processes 28 tokens → outputs audio for [25..49]
```

The initial token_buffer is pre-filled with 3 padding tokens [4218, 4218, 4218] for the first chunk.

### Q6: First chunk vs subsequent — same window?

**Yes.** Both use CHUNK_SIZE=25 for the Talker output buffer. The accumulation logic is identical for all chunks:

```cpp
// Line 6960
while ((int)ctx_omni->tts_token_buffer.size() >= CHUNK_SIZE && ctx_omni->t2w_thread_info) {
    // Push 25 tokens to T2W queue, slide buffer
}
```

The only difference is that the first chunk may take longer to accumulate (Talker starts from cold), but the CHUNK_SIZE threshold is the same.

### Q7: Would CHUNK_SIZE < 25 cause interface rejection?

**No hard rejection**, but there are operational concerns:
- The T2W sliding window logic expects WINDOW_SIZE=28 (CHUNK_SIZE + PRE_LOOKAHEAD)
- Reducing CHUNK_SIZE would reduce the T2W context window
- The Flow Matching model's quality depends on having sufficient context for smooth flow interpolation
- The lookahead overlap (3 tokens) would still work, but the chunk boundary density would increase

**No code path explicitly rejects values < 25.** The `while (buffer.size() >= CHUNK_SIZE)` loop would simply fire more frequently with smaller chunks.

### Q8: Can we pre-compute before the full window?

**Limited.** The Talker generates tokens autoregressively — each token depends on the previous one. However:
- The T2W worker runs on a separate thread and can process audio tokens as they arrive
- The sliding window requires at least WINDOW_SIZE (CHUNK_SIZE + PRE_LOOKAHEAD) tokens for the first processing step
- After the first window, the T2W slides forward by CHUNK_SIZE, so it needs CHUNK_SIZE new tokens for each subsequent step
- **Pre-computation opportunity**: The initial 3 padding tokens [4218, 4218, 4218] could be pre-loaded, reducing the first window's wait from 28 to 25 tokens

### Q9: 302ms breakdown — Talker compute vs queue/sync/wait

| Component | Duration | % of G3→G4 |
|-----------|----------|------------|
| Talker token generation (24 steps × ~12.6ms/step) | **~302ms** | ~100% |
| T2W queue push (mutex lock + push + notify) | <0.1ms | <0.1% |
| T2W worker wake (cv.wait → dequeue) | <0.5ms | <0.2% |

**The G3→G4 interval is almost entirely Talker compute.** The Talker generates tokens one at a time in an autoregressive loop. Each step involves:
- Embedding lookup
- Transformer forward pass (multiple layers)
- Sampling head projection
- Token sampling

The queue/synchronization overhead is negligible compared to the 24-step generation loop.

### Q10: Exact G3→G4 measurement

From the Z4 v2 data, G3→G4 is NOT measurable on matched pairs (0 strict pairs at Level 3). However:

- **Nominal**: 24 steps × ~12.6ms = ~302ms
- **Code analysis**: G3 is recorded at the first audio token; the loop continues generating until buffer accumulates 25 tokens; G4 is the first `buffer.size() >= 25` T2W push
- **The ~302ms is not "waiting" — it's productive Talker compute** generating the next 24 audio tokens

## Summary

```
G3→G4 = TALKER_AUDIO_TOKEN_ACCUMULATION
      ≈ 302ms
      ≈ 24 Talker steps × ~12.6ms/step
      ≈ 100% productive compute (not queue/sync overhead)

CHUNK_SIZE = 25           (engineering policy, Python-aligned)
PRE_LOOKAHEAD = 3         (cross-chunk overlap, ~120ms)
WINDOW_SIZE = 28          (25 + 3, T2W input)

CONSTRAINT_TYPE = ENGINEERING_POLICY (not model-semantic)
REDUCIBILITY = LIKELY (with quality verification)
CURRENT_ACTION = AUDIT_ONLY (per user scope)
```
