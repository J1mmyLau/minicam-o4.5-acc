# F6 B6B REJECTED CANDIDATE — EARLY_FIRST_TTS_CHUNK_DISPATCH

**Date:** 2026-08-01
**Status:** REJECTED (no significant E2E gain in FP16+CANN)
**Tag:** `fp16-f6-early-tts-dispatch-internal-20260731` @ `00a2755` (PRESERVED)

---

## Hypothesis

> Reducing the first TTS text chunk accumulation threshold from 10 to 5 LLM tokens
> will reduce the end-to-end first-audio latency by advancing the TTS wake point
> in the decode timeline.

## Implementation

| Component | Change |
|-----------|--------|
| **File** | `tools/omni/omni.cpp` |
| **Env var** | `OMNI_TTS_FIRST_CHUNK_STEP` (default 5 for B6b ON, 10 for OFF) |
| **Mechanism** | `effective_step = (is_first_chunk && !duplex_mode) ? first_chunk_step : 10` |
| **Scope** | Simplex TTS path only; duplex path unchanged |
| **CHUNK_SIZE** | 25 (FROZEN — not modified) |

## Valid Experiment

| Parameter | Value |
|-----------|-------|
| **Model** | FP16 (`MiniCPM-o-4_5-F16.gguf`, SHA256 `d1e69845...`) |
| **Binary** | HEAD `3bf77b0`, SHA256 `42c97f40...` |
| **Platform** | 2× Ascend 910C, CANN 9.1.0-beta.1 |
| **Flow backend** | CANN (`OMNI_T2W_DEVICE=cann-flow-only`) |
| **Vocoder backend** | GPU (`OMNI_VOC_DEVICE=gpu`) |
| **Design** | Sequential ABBA, 60 blocks, 120 matched pairs |
| **Errors** | 0 crashes, 0 CANN errors, 100% W0 presence |

## Canonical Statistics

| Metric | n | OFF Median | ON Median | Paired Δ Median | CI95 | Win Rate |
|--------|---|-----------|----------|-----------------|------|----------|
| D0→D2 (main LLM) | 120 | 28ms | 28ms | **0ms** | [0, 0] | 20% |
| D2→G0 (TTS wake) | 120 | 0ms | 0ms | **0ms** | [0, 0] | 27% |
| D0→W0 (server first WAV) | 120 | 922ms | 927ms | **-17.5ms** | [-44, +10.5] | 52.5% |
| Client→first WAV | 120 | 10424ms | 10422ms | **-2.3ms** | [-8.5, +2.7] | 53.3% |
| Flow+VPN total | 120 | 269ms | 266ms | **0ms** | [-7, +2.5] | 49% |

## Engineering Threshold Analysis

| Threshold | Value | Server D0→W0 Met? | Client Met? |
|-----------|-------|-------------------|-------------|
| Absolute margin | 10ms / 5ms | ~ (median -17.5ms) | ✗ (median -2.3ms) |
| Relative margin | 2% / 1% | ✗ (-17.5 < 18.4ms) | ✗ (-2.3 < 104ms) |
| CI95 entirely negative | — | ✗ (upper +10.5ms) | ✗ (upper +2.7ms) |
| Win rate ≥ 95% | — | ✗ (52.5%) | ✗ (53.3%) |

**Classification: `REJECT_NO_MEANINGFUL_GAIN`**

## Why Rejected

1. **Client-observed benefit is ~2.3ms median** — well below any reasonable engineering threshold (5ms absolute, 104ms relative). This is imperceptible to users.

2. **Server D0→W0 CI95 crosses zero** — the -17.5ms median improvement is not statistically distinguishable from noise given the 338ms standard deviation.

3. **Win rates ~50%** — B6b wins in only about half of matched pairs, meaning workload variance dominates the signal. A feature that helps half the time and has no effect the other half does not provide reliable benefit.

4. **D2→G0 is effectively 0ms in FP16+CANN** — the TTS wake already occurs at the same time as the first LLM token. There is no scheduling gap for B6b to close.

5. **Main LLM latency unchanged** (D0→D2 Δ=0ms, CI95 [0,0]) — B6b does not affect core decode performance. The optimization purely targets the TTS scheduling window, which is already minimal with CANN-accelerated T2W.

## Historical Invalid Runs

| Run | Model | T2W Backend | D2→G0 Δ | Validity |
|-----|-------|-------------|---------|----------|
| Q4_K_M diagnostic | Q4_K_M | CPU (fallback) | -133ms (artifact) | INVALID_FOR_FP16_GATE |
| FP16+CANN (this) | FP16 | CANN NPU | 0ms | CANONICAL |

**Historical causal attribution: `UNPROVEN_MULTI_FACTOR_CONFOUNDING`**

The early ~133ms Q4 result cannot be attributed to any single factor. Multiple variables changed simultaneously:
- Q4_K_M → FP16 quantization
- CPU T2W fallback → CANN T2W
- Non-canonical args → canonical args
- Pre-fix harness → corrected harness

The Q4 result is `INVALID_FOR_FINAL_FP16_CONCLUSION`. No causal claim about CPU T2W being the sole cause is warranted without a controlled 2×2 factorial experiment. Such an experiment is not recommended — the FP16+CANN negative result is definitive regardless of the Q4 artifact's cause.

## Feature Status

```
B6B_TRUE_E2E_FP16_GATE       = REJECT_NO_MEANINGFUL_GAIN
B6B_FEATURE_STATUS           = EXPERIMENTAL_KNOB / DEFAULT_OFF
B6B_PRODUCTION_RECOMMENDATION = DO_NOT_ENABLE
B6B_MAIN_LLM_ACCELERATION    = NONE
```

## Revisit Condition

B6b may be worth re-evaluating if:

1. A new T2W backend significantly increases the G0→t2w_dequeue interval
2. A fixed-output benchmark workload is adopted (narrower CIs)
3. A different model architecture creates a measurable D2→G0 scheduling gap
4. CPU-bound T2W deployment scenarios are targeted (B6b may help there)

None of these conditions currently exist for the FP16+CANN production candidate.

## Preservation

- **Implementation**: Preserved in `tools/omni/omni.cpp` (do not delete)
- **Tag**: `fp16-f6-early-tts-dispatch-internal-20260731` @ `00a2755` preserved
- **Data**: `/tmp/f6_fp16_w10/` preserved (120 pairs)
- **Q4 diagnostic**: `/tmp/f6_w10_ab/` preserved (96 profiles, `INVALID_RUN_MANIFEST.md`)
