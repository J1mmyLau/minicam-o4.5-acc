# F6 R8: Audio Token Window Contract

**Date:** 2026-07-31
**Source:** `tools/omni/omni.cpp` lines 6683, 6955-6989, 10225-10282

---

## Current Contract

### Talker → TTS Token Buffer

```
Talker generates audio tokens one at a time (autoregressive)
  → Each non-EOS token pushed to tts_token_buffer
  → When buffer.size() >= CHUNK_SIZE (25):
      → Extract first 25 tokens → push to T2W queue
      → Erase first 25 tokens from buffer
      → Record G4 (first T2W submit, one-shot)
  → Buffer accumulates remaining tokens for next chunk
```

### T2W Sliding Window

```
T2W worker dequeues audio token chunk (25 tokens)
  → Appends to internal token_buffer (pre-filled with [4218, 4218, 4218])
  → When buffer.size() >= WINDOW_SIZE (28 = 25 + 3):
      → Feed 28 tokens through: Encoder → Flow Matching → Vocoder
      → Output: WAV audio segment (~1 second)
      → Slide buffer: remove first CHUNK_SIZE (25), keep last PRE_LOOKAHEAD (3)
  → is_final=true: send last_chunk to T2W, clear buffer
```

### Constants

| Constant | Value | Audio Duration | Defined At | Origin |
|----------|-------|---------------|------------|--------|
| CHUNK_SIZE | 25 tokens | ~1.0s (@ 40ms/token) | `omni.cpp:6683, 10231` | Python `TTSStreamingGenerator.chunk_size=25` |
| PRE_LOOKAHEAD | 3 tokens | ~120ms | `omni.cpp:10232` | Python `pre_lookahead=3` |
| WINDOW_SIZE | 28 tokens | ~1.12s | `omni.cpp:10233` | CHUNK_SIZE + PRE_LOOKAHEAD |
| Initial buffer | [4218, 4218, 4218] | 3 padding tokens | `omni.cpp:10236` | TTS audio_bos padding |

## What Would Break If CHUNK_SIZE Changed

### If reduced to, say, 16:

| Component | Impact | Severity |
|-----------|--------|----------|
| **T2W window context** | 19 tokens (16+3) instead of 28 — less context for Flow Matching | **Medium** |
| **Cross-chunk density** | More chunk boundaries per utterance | **Low-Medium** |
| **T2W throughput** | More frequent, smaller T2W invocations | **Low** |
| **Flow matching quality** | Less temporal context may reduce smoothness at boundaries | **Medium** |
| **Vocoder continuity** | Shorter segments may reduce phase continuity | **Low-Medium** |
| **Talker loop** | Unchanged — generates same tokens regardless of CHUNK_SIZE | **None** |
| **First audio token (G3)** | Unchanged — G3 records first token regardless of buffer | **None** |

### If increased to, say, 32:

| Component | Impact | Severity |
|-----------|--------|----------|
| **First chunk latency** | Increased G3→G4 (7 more tokens × ~12.6ms = +88ms) | **High** |
| **T2W window context** | 35 tokens (32+3) — more context, potentially better quality | **Positive** |
| **Streaming latency** | Larger chunks = more buffering = higher latency | **Medium** |

## First Chunk vs Subsequent Chunks

**Contract is identical.** Both use CHUNK_SIZE=25 for the buffer threshold:

```cpp
// No distinction between first and subsequent chunks in TTS buffer logic
while ((int)ctx_omni->tts_token_buffer.size() >= CHUNK_SIZE && ctx_omni->t2w_thread_info) {
    // Same CHUNK_SIZE=25 for all chunks
}
```

The first chunk is special only in that:
1. It starts from an empty buffer (or with padding tokens for T2W)
2. The Talker needs warmup steps before the first audio token
3. G3 is recorded precisely at the first token

## Contract Type

```
CHUNK_SIZE_CONTRACT = ENGINEERING_POLICY
  ├── NOT model-architecture-constrained (T2W handles variable sizes)
  ├── NOT training-fixed (inherited from Python streaming generator)
  ├── NOT interface-enforced (no hard rejection for non-25 values)
  ├── quality-implication: smaller = less T2W context, potentially worse audio
  └── latency-implication: smaller = faster first chunk, more boundary overhead
```

## Recommendation

**Do NOT change CHUNK_SIZE without:**
1. Offline T2W quality evaluation at target chunk sizes (WER, SIM, MOS)
2. Blind listening comparison at chunk boundaries
3. Flow Matching model receptive field analysis
4. First-chunk-only reduction as a safer alternative (hybrid approach, similar to B6b pattern)
