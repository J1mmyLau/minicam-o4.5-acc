# F6 B6b Internal Candidate Manifest

**Date:** 2026-07-31
**Status:** FROZEN / OPT_IN_READY / DEFAULT_OFF

---

## Identity

| Field | Value |
|-------|-------|
| **Candidate name** | EARLY_FIRST_TTS_CHUNK_DISPATCH |
| **F6 tag** | `fp16-f6-early-tts-dispatch-internal-20260731` |
| **Git HEAD** | `00a275549a2830bde6b8564cc13bfea5ad73d115` |
| **Branch** | `perf/f6-decode-to-speak` |
| **Base KV tag** | `ngl8-e2e-closeout-20260726` (P9: 150/150, KV cache OPT_IN_READY) |

## Artifact SHAs

| Artifact | SHA256 |
|----------|--------|
| **Server binary** | `943debe1d19bf47766987e89d988951860f6bde190331c4f1d5bc8dd4188dc70` |
| **Model (LLM)** | `d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de` |
| **TTS model** | `/workspace/models/MiniCPM-o-4_5-gguf/tts/MiniCPM-o-4_5-omni_tts-F16.gguf` |
| **Projector** | `/workspace/models/MiniCPM-o-4_5-gguf/tts/MiniCPM-o-4_5-projector-F16.gguf` |
| **APM (audio)** | `/workspace/models/MiniCPM-o-4_5-gguf/audio/MiniCPM-o-4_5-audio-F16.gguf` |
| **Token2Wav** | `/workspace/models/MiniCPM-o-4_5-gguf/token2wav-gguf/` |

## Platform

| Field | Value |
|-------|-------|
| **NPU** | 2× Ascend 910C (Davinci 2201) |
| **HBM per NPU** | 64 GB |
| **CANN** | 9.1.0-beta.1 |
| **Driver** | Ascend 910C driver |
| **OS** | Linux 5.10.0 (openEuler 22.03 SP4) |

## Feature Configuration

| Config | Value | Notes |
|--------|-------|-------|
| **Env var** | `OMNI_TTS_FIRST_CHUNK_STEP` | Default: 5 (B6b ON). Set to 10 for baseline. |
| **First chunk step** | 5 valid LLM tokens | B6b optimization target |
| **Subsequent chunk step** | 10 valid LLM tokens | Unchanged |
| **CHUNK_SIZE (T2W)** | 25 audio tokens | Unchanged, ENGINEERING_POLICY_CONFIRMED |
| **Simplex path** | `effective_step = (is_first_chunk && !duplex_mode) ? first_chunk_step : 10` | `omni.cpp:~12781` |
| **Duplex path** | `effective_step = (is_first_chunk && duplex_mode) ? duplex_first_chunk_step : 10` | `omni.cpp:~11681` |
| **E2E profiling** | `OMNI_E2E_PROFILE=1`, `OMNI_E2E_PROFILE_DIR=<path>` | 16-stage atomic timestamps |

## Canonical Launcher

```bash
OMNI_TTS_FIRST_CHUNK_STEP=5 \
OMNI_E2E_PROFILE=1 \
OMNI_E2E_PROFILE_DIR=/tmp/prof \
/workspace/llama.cpp-omni-f6/build/bin/llama-omni-server \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf \
  -ngl 999 -fa off \
  -c 4096 -b 512 -ub 512 \
  --split-mode layer \
  --host 127.0.0.1 --port 18110
```

## Rollback

```bash
# To revert to baseline behavior:
export OMNI_TTS_FIRST_CHUNK_STEP=10
# Or unset (default was 10 before B6b):
unset OMNI_TTS_FIRST_CHUNK_STEP
```

## Canonical Matched Results

| Interval | Canonical Name | n (pairs) | Paired Δ median | Win Rate | Evidence |
|----------|---------------|-----------|-----------------|----------|----------|
| D0→D2 | MAIN_FIRST_TOKEN_LATENCY | 175 (C6+Z4) | **-1 ms** | ~50% | C6 + Z4 |
| D2→G0 | FIRST_TEXT_CHUNK_ACCUMULATION_AND_TTS_WAKE | 163 (C6+Z4) | **-133 ms** (-55%) | 36/47 (Z4), 106/116 (C6) | C6 + Z4 |
| D0→G3 | DECODE_TO_FIRST_TALKER_AUDIO_TOKEN | 16 (Z4) | **-151 ms** | 16/16 (100%) | Z4 only |
| G0→G3 | TALKER_TO_FIRST_AUDIO_TOKEN | 17 (Z4) | **-6 ms** | ~90% | Z4 |

**⚠️ Note:** D2→G0 and D0→G3 use different pair sets. R1-R2 will establish strict matched intersection before claiming pass-through.

## Stability

| Test | Requests | Errors | Crashes | Drift |
|------|----------|--------|---------|-------|
| C9 | 150 | 0 | 0 | +16ms (0.98ms/req, CASE_MIX + KV pressure) |
| Z10 | 200 | 0 | 0 | +0.41ms/req (improved with 90s drain) |
| **Combined** | **350** | **0** | **0** | |

## Basic QC

| Gate | Status | Evidence |
|------|--------|----------|
| AUDIO_FORMAT_GATE | **PASS** | 24000 Hz, mono, valid WAV headers, 120 WAVs collected |
| AUDIO_BASIC_QC_GATE | **PASS** | Duration 0.44-1.00s, consistent baseline/candidate, no truncation detected |
| HUMAN_LISTENING_GATE | **PENDING** | 20-sample blind A/B manifest at `/tmp/f6_z9_listening/LISTENING_MANIFEST.csv` |
| OBJECTIVE_WER_SIM_GATE | **PENDING_EXTERNAL** | Requires external ASR + speaker embedding pipeline |

## Known Limitations

1. **D0→W0 not measured on matched pairs**: Async T2W/Flow/Vocoder pipeline prevents per-request WAV tracking. W0 available in <2% of E2E profiles.
2. **D0→G3 pass-through uses different pair sets**: 47 D2G0 pairs vs 16 D0G3 pairs. R1-R2 will fix this.
3. **Audio perceptual quality not evaluated**: Only format/basic QC done. Human listening manifest prepared but not executed.
4. **Duplex path tested less extensively**: Primary testing on simplex path.
5. **Single voice (Voice_A, Voice_B)**: Only 2 voices in test set. Broader voice coverage not tested.

## Gate Matrix (R0-corrected)

```
B6B_INTERNAL_PERFORMANCE_GATE  = PASS        (D2→G0 -133ms, 163 pairs)
B6B_TEXT_CONSISTENCY_GATE      = PASS_ON_TESTED_CASES  (MAIN_LLM_GENERATION_LOGIC_UNCHANGED)
B6B_STABILITY_GATE             = PASS_350_OF_350       (0 errors, 0 crashes)
B6B_BASIC_AUDIO_QC_GATE        = PASS        (format + basic QC)
B6B_HUMAN_LISTENING            = PENDING
B6B_OBJECTIVE_TTS_SCORING      = PENDING_EXTERNAL
B6B_DEFAULT_ENABLEMENT         = NO
B6B_STATUS                     = OPT_IN_READY / DEFAULT_OFF
B6B_INTERNAL_CANDIDATE         = FROZEN
DSPARK                         = REJECTED_BY_CURRENT_BOTTLENECK_EVIDENCE
```
