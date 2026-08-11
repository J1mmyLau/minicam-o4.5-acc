# F6 FP16 TRUE_E2E Run Manifest — Final

**Date:** 2026-07-31 17:48 UTC
**Status:** COMPLETE (120 pairs, 0 errors)

---

## Experiment Identity

| Field | Value |
|-------|-------|
| **Experiment name** | F6_B6B_FP16_TRUE_E2E_120_PAIR_AB |
| **Source branch** | `perf/f6-decode-to-speak` |
| **Source HEAD** | `3bf77b0d46e81a223771a3c6210c5479a1bdc403` |
| **Commit chain** | `c1979df` → `23a2f96` → `43f8b01` → `dfd56d2` → `2660ca5` → `3bf77b0` |
| **Base freeze tag** | `fp16-f6-early-tts-dispatch-internal-20260731` @ `00a2755` (NOT MOVED) |
| **W0 observability tag** | `fp16-f6-w0-observability-20260731` @ `31cba8d` |

## Binary Identity

| Artifact | SHA256 |
|----------|--------|
| **Server binary** | `42c97f40c0738366e076f6e3352f8f4931e2e8898e29f1a688ad571e794398a3` |
| **Built from** | HEAD `3bf77b0` |

## Model Identity

| Artifact | Path | SHA256 |
|----------|------|--------|
| **LLM (FP16)** | `/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf` | `d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de` |
| **TTS (FP16)** | `/workspace/models/MiniCPM-o-4_5-gguf/tts/MiniCPM-o-4_5-omni_tts-F16.gguf` | (see manifest) |
| **Projector** | `/workspace/models/MiniCPM-o-4_5-gguf/tts/MiniCPM-o-4_5-projector-F16.gguf` | (see manifest) |
| **Token2Wav** | `/workspace/models/MiniCPM-o-4_5-gguf/token2wav-gguf/` | encoder, flow_matching, flow_extra, hifigan2, prompt_cache |

## Platform

| Field | Value |
|-------|-------|
| **NPU** | 2× Ascend 910C (Davinci 2201) |
| **HBM per NPU** | 64 GB |
| **CANN** | 9.1.0-beta.1 (`/usr/local/Ascend/cann-9.1.0-beta.1`) |
| **Driver** | Ascend 910C driver (npu-smi available) |
| **OS** | Linux 5.10.0 (openEuler 22.03 SP4) |

## Canonical Launcher

```bash
OMNI_T2W_DEVICE=cann-flow-only \
OMNI_VOC_DEVICE=gpu \
OMNI_TTS_FIRST_CHUNK_STEP=<5 or 10> \
OMNI_E2E_PROFILE=1 \
OMNI_E2E_PROFILE_DIR=<block_dir>/<label>_profiles \
./build/bin/llama-omni-server \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf \
  --host 127.0.0.1 --port 8080 \
  -ngl 999 \
  -c 4096 -b 512 -ub 512 \
  --split-mode layer -fa off \
  -n 128
```

## Feature Configuration

| Config | OFF (Baseline) | ON (Candidate) |
|--------|---------------|----------------|
| `OMNI_TTS_FIRST_CHUNK_STEP` | 10 | 5 |
| `CHUNK_SIZE` (T2W window) | 25 | 25 (FROZEN) |
| Flash Attention (`-fa`) | off | off |
| NPU split | layer | layer |

## Backend Status

| Component | Backend | Verified |
|-----------|---------|----------|
| Flow | CANN (NPU) | `OMNI_T2W_DEVICE=cann-flow-only` ✓ |
| Vocoder | GPU (NPU) | `OMNI_VOC_DEVICE=gpu` ✓ |
| T2W dequeue | CANN | async_stages_ms present ✓ |

## Experiment Design

| Parameter | Value |
|-----------|-------|
| **Design** | Sequential ABBA (A=OFF, B=ON, B=ON, A=OFF) |
| **Blocks** | 60 ABBA blocks |
| **Total pairs** | 120 matched pairs |
| **Total requests** | 240 (120 OFF + 120 ON) |
| **Ordering** | A1→B1→B2→A2 per block |
| **Same binary** | ✓ (sequential server restart, env var change only) |
| **Same model** | ✓ (FP16, single path) |
| **Same machine** | ✓ (single NPU server at a time) |

## Run Quality

| Metric | Value |
|--------|-------|
| **Server starts** | 240/240 (100%) |
| **W0 presence** | 240/240 (100%) |
| **Audio valid** | 240/240 (100%) |
| **CANN errors** | 0 |
| **Crashes** | 0 |
| **Stale writes** | 0 |
| **Cross-request contamination** | 0 |
| **Harness errors** | 0 |
| **Runtime** | ~84 minutes (16:24 → 17:48 UTC) |
| **Pace** | ~84s per ABBA block |

## Data Location

| Artifact | Path |
|----------|------|
| **Raw profiles** | `/tmp/f6_fp16_w10/abba_block_XXXX/` (60 dirs × 4 labels) |
| **Progress CSV** | `/tmp/f6_fp16_w10/progress.csv` |
| **Full report** | `/tmp/f6_fp16_w10/w10_ab_report.json` |
| **Canonical CSV** | `/tmp/f6_fp16_w10/F6_B6B_FP16_CANONICAL_120_PAIRS.csv` |
| **Run log** | `/tmp/f6_fp16_w10_run.log` |

## Profile Fields Available

### stages_ms (request-scoped, main thread)
```
decode_loop_begin (always 0)
llm_first_decode_step (D0)
llm_first_token (D2)
request_received (always 0)
tts_wake (G0)
```

### async_stages_ms (T2W thread)
```
t2w_dequeue
flow_start
flow_end
vocoder_start
vocoder_end
wav_ready (W0)
```

### NOT AVAILABLE (missing from FP16 profiles)
```
talker_start
talker_first_audio_token (G3)
talker_token_28
t2w_submit (G4)
```

**Impact:** G3→G4 bottleneck analysis requires additional instrumentation (P9).

## Audit

| Check | Result |
|-------|--------|
| Single binary throughout | ✓ (SHA256 unchanged) |
| Single model throughout | ✓ (SHA256 unchanged) |
| Single launcher contract | ✓ |
| CANN env present all requests | ✓ |
| No merged data from different configs | ✓ |
