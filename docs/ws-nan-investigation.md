# WS Multimodal NaN Logits — Investigation Report

**Date:** 2026-08-10
**Status:** ROOT CAUSE TRACED, FIX DEFERRED (WAIT_OFFICIAL_UNIFIED_EVAL_BRANCH)
**Branch:** `fix/ws-multimodal-nan` (8ed2dab)

## Summary

WebSocket multimodal paths produce NaN logits whenever audio or video content parts are present.
NaN originates in the **audio mel spectrogram preprocessing**, BEFORE the Whisper encoder forward pass.
The LLM and Whisper encoder are both clean — they receive NaN input and propagate it faithfully.

## NaN Propagation Chain

```
whisper_input_mel     nan=160/2400   (6.67%, 2 full frames of 80 mel bins each)
                                         valid values = -1.5 (correct for silent audio)
whisper_embed_output  nan=12288/12288 (100%, 3 tokens × 4096 dims)
audio_embed_memcpy    nan=12288/12288 (100%)
audio_only_prefill    nan=12288/12288 (100%)
logits_ith            nan=151748/151748 (100% vocab)
→ text output = "?" (token 30) for all tokens
```

## Root Cause Location

`tools/omni/audition.cpp:log_mel_spectrogram_worker_thread()` (L1839-1901)

The mel spectrogram computation produces 160 NaN values (2 full frames) out of 2400 total (30 frames × 80 mel bins).

### Key observation

- All valid mel values are exactly **-1.5**: `(log10(1e-10) + 4.0) / 4.0` — correct for silent input
- Exactly 2 of 30 frames are entirely NaN
- The NaN guard at L1890 (`sum = log10(std::max(sum, 1e-10))`) should prevent NaN...
  - Unless `sum` itself is NaN (NaN > 1e-10 is false → log10(1e-10) = -10 is correct)
  - The NaN must come from the FFT magnitude or mel filterbank computation producing NaN
  - `NaN * filter + 0 * filter + ... = NaN` → then `std::max(NaN, 1e-10)` is NaN (NaN comparisons always false)

## Hypotheses for Mel NaN

1. **FFT workspace buffer alias**: Recursive Cooley-Tukey FFT uses `in` array as workspace
   (even/odd split). For N=400 (WHISPER_N_FFT), `fft_in` size=800 is exactly enough, but
   edge cases in recursion depth might exceed bounds.

2. **Uninitialized memory in FFT output**: `fft_out` vector is value-initialized (zeroed),
   but the recursive FFT might leave some positions uninitialized for certain N values.

3. **Mel filterbank NaN**: If `filters.data` contains NaN entries for certain frequency bins,
   the dot product `sum += fft_out[k] * filters.data[j * n_fft + k]` would accumulate NaN.

4. **Thread race condition**: `log_mel_spectrogram_worker_thread` runs multi-threaded (n_threads=4).
   Each thread has its own `fft_in`/`fft_out`, but the output writes to shared `mel.data` at
   `mel.data[j * mel.n_len + i]` which is thread-safe (each thread owns distinct frames `i`).

## Scope

| Input | Output | Vision | Audio Encode | Status |
|-------|--------|--------|-------------|--------|
| Text-only | CLEAN | N/A | N/A | ✅ |
| Image-only | CLEAN | ✅ | N/A | ✅ |
| Audio | ALL `?` | N/A | NaN mel → NaN embed | ❌ |
| Video (with audio) | ALL `?` | ✅ | NaN mel → NaN embed | ❌ |
| Video (no audio) | ALL `?` | ✅ | ⚠️ EMPTY → NaN? | ❌ |

**Key signal:** Video WITHOUT audio track also triggers NaN → video processing may inject
empty/zero-length audio that triggers the same mel NaN path.

## Instrumentation

8 `nan_diag_check()` boundaries, gated behind `OMNI_NAN_DIAG=1`:

| # | File | Boundary | After |
|---|------|----------|-------|
| 1 | audition.cpp:1512 | whisper_input_mel | mel data memcpy |
| 2 | audition.cpp:1584 | whisper_embed_output | Whisper encoder tensor_get |
| 3 | vision.cpp:2522 | vision_embed_output | Vision encoder tensor_get |
| 4 | omni.cpp:13993 | audio_embed_memcpy | audio_embed memcpy into omni_embeds |
| 5 | omni.cpp:6939 | vision_audio_prefill | before prefill_with_emb (vision+audio) |
| 6 | omni.cpp:6969 | audio_only_prefill | before prefill_with_emb (audio-only) |
| 7 | omni.cpp:1620 | prefill_embeddings | after llama_get_embeddings |
| 8 | omni.cpp:2521 | logits_ith | after llama_get_logits_ith |

## Repro

```bash
# Build
cd /workspace/llama.cpp-omni-session-fix
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON
cmake --build . --target llama-omni-server -j$(nproc)

# Run server
OMNI_NAN_DIAG=1 build/bin/llama-omni-server \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf \
  --host 127.0.0.1 --port 18094 -ngl 999 --device CANN0 \
  --ctx-size 4096 --batch-size 512 --ubatch-size 512 \
  --split-mode layer -t 4 &

# Run repro
python3 scripts/f6_nan_repro_matrix.py

# Check server stderr for [nan_diag] lines
```

## Decision

**DO NOT FIX NOW.** This bug may be specific to the current non-unified evaluation path.
The official unified evaluation branch arriving tomorrow (2026-08-11) may use different:
audio preprocessing, Prompt Bundle format, input organization, or media format.

If NaN reproduces on the official unified eval branch → true P0 correctness bug.
If NaN does NOT reproduce → artifact of current non-unified path → CLOSE.
