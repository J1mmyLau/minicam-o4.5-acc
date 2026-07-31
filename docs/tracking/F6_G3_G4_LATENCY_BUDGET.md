# F6 R8: G3→G4 Latency Budget

**Date:** 2026-07-31
**Source:** Z4 v2 profiles, `omni.cpp` Talker loop analysis

---

## Current Budget (candidate, B6b step=5)

| Interval | Canonical Name | Latency (ms) | % of D0→G4 |
|----------|---------------|-------------|------------|
| D0→D2 | MAIN_FIRST_TOKEN_LATENCY | 72 | 13.7% |
| D2→G0 | FIRST_TEXT_CHUNK_ACCUMULATION_AND_TTS_WAKE | 111 | 21.1% |
| G0→G3 | TALKER_TO_FIRST_AUDIO_TOKEN | 42 | 8.0% |
| G3→G4 | TALKER_AUDIO_TOKEN_ACCUMULATION | **302** | **57.3%** |
| **D0→G4** | DECODE_TO_FIRST_T2W_SUBMIT | **527** | **100%** |

## G3→G4 Breakdown

| Component | Latency (ms) | % of G3→G4 | Notes |
|-----------|-------------|------------|-------|
| Talker autoregressive steps (24 steps) | ~302 | ~100% | 24 steps to generate tokens 2-25 |
| Per-step compute | ~12.6 | 4.2% | Embed + Transformer forward + Sample |
| T2W queue push | <0.1 | <0.1% | mutex lock + push + notify_one |
| Queue/sync idle | ~0 | 0% | Buffer accumulates synchronously in Talker loop |

## What The 302ms Is (And Isn't)

### IS:
- **Productive Talker compute**: 24 autoregressive forward passes generating audio tokens
- **Necessary for audio quality**: Each token is a step in the audio codec sequence
- **Parallelizable in theory**: Talker and T2W run on separate threads; T2W can process previous chunk while Talker generates next

### IS NOT:
- **Idle waiting**: The Talker is actively computing during this interval
- **Queue backlog**: The T2W queue is not the bottleneck (queue push takes <0.1ms)
- **Synchronization overhead**: No significant lock contention in the TTS→T2W path
- **I/O wait**: No disk or network I/O in this path

## Optimization Headroom

| Approach | Potential Saving | Risk | Effort |
|----------|-----------------|------|--------|
| **Reduce CHUNK_SIZE (first chunk only)** | ~63ms (20→15 tokens) to ~113ms (16→9 tokens) | Medium (less T2W context for first chunk) | Low-Medium |
| **Talker step optimization** | ~1-3ms/step via kernel fusion | Low | High (CANN kernel work) |
| **Talker-T2W pipelining** | Overlap last N steps with T2W processing | Low (already threaded) | Medium |
| **Early T2W start** | Start T2W before full 25-token window | Medium (T2W needs minimum context) | Medium |
| **Reduce CHUNK_SIZE (all chunks)** | ~63-113ms per chunk | High (quality risk at every boundary) | Medium |

## Current Position in Pipeline

```
HTTP → Prefill → LLM Decode → Token Classify → TTS Wake → Talker → T2W → Flow → Vocoder → WAV
|______|_______|___________|_______________|_________|________|_____|______|________|_____|
  ~15    ~46      ~1/step     ~2-3ms          ~42ms    ~302ms   ?     ?       ?       ?

                               [B6b saved 133ms here]   [NEXT BOTTLENECK: 302ms, 57.3%]
```

## Recommendation

```
G3_TO_G4_OPTIMIZATION = AUDIT_ONLY
  ├── CHUNK_SIZE = 25 (ENGINEERING_POLICY, not model constraint)
  ├── 302ms = 24 × 12.6ms/step Talker compute (productive, not waste)
  ├── First-chunk-only reduction = SAFEST path (same pattern as B6b)
  ├── Full CHUNK_SIZE reduction = REQUIRES T2W quality verification
  └── ACTION: Document contract, defer optimization to F7
```
