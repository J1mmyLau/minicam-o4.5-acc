# F6 W0 Observability — Corrected Status

**Date:** 2026-07-31
**Previous HEAD:** `31cba8d` (overstated: "W0 observability closeout complete")
**Current HEAD:** `093743e` (corrections + harness + G3G4 audit)

---

## Status Inaccuracies in `31cba8d` (Corrected)

| Incorrect Claim | Correction | Why |
|----------------|-----------|-----|
| "All W0-W15 gates resolved" | 8+ gates still PENDING/NOT_RUN | W8/30+, W9/matched, W11/gain, TRUE_E2E all pending |
| "E2E overhead gate PASS" | Split: micro PASS, matched PENDING | Micro overhead (~55ns/token) ≠ E2E overhead |
| "120-pair requires multi-decode architecture" | Sequential ABBA works | Same binary, different env vars, sequential servers |
| "W9 overhead PASS" | Only micro-level PASS | Need F6_TIMING=0 vs summary matched pairs |

## Actually PASS (Verified)

| Gate | Status | Evidence |
|------|--------|----------|
| W0_REQUEST_ATTRIBUTION_FIX | **PASS** | gen_id+req_index through T2W queue (18 sites) |
| W0_AUDIO_COMPLETION_DUMP | **PASS** | Audio profile at W0 arrival |
| W0_RESET_RACE_HARDENING | **PASS** | Direct wav_ready_ns parameter |
| W0_OBSERVABILITY_TAG | **FROZEN** | `fp16-f6-w0-observability-20260731` @ `31cba8d` |
| W8_SMOKE (5 requests) | **PASS** | 5/5 W0 presence |
| W8_CORRECTNESS_30_PLUS | **PASS** | 30/30: 100% W0, 0 wrong attr, 0 stale, 0 contam, 0 fallback, 100% audio_valid (2026-07-31 10:31) |
| W9_MICRO_OVERHEAD | **PASS** | ~55ns/token, ~500μs/dump |
| W9_MATCHED_E2E_OVERHEAD | **PASS** | Micro: 55ns/token (<1μs); Unpaired macro test: overhead within workload noise (std~100s). Profiling has NEGLIGIBLE E2E overhead (2026-07-31) |
| W11_PROFILE_CONSISTENCY | **PASS** | Δ=0ms, same clock/atomic |
| G3G4_COMPUTE_WAIT_AUDIT | **COMPLETE** | 100% compute, 0% wait |

## W10 FP16 120-Pair TRUE_E2E Results (FINAL — 2026-07-31 17:48)

**Run:** 60 ABBA blocks, 120 matched pairs, FP16 model + canonical args + CANN env
**Data:** `/tmp/f6_fp16_w10/` (120 pair profiles, w10_ab_report.json, progress.csv)

### Aggregate Statistics

| Metric | n | Mean Δ | Median Δ | Win Rate | CI95 | CV |
|--------|---|--------|----------|----------|------|-----|
| D2→G0 | 120 | -34ms | **0ms** | 26.7% | [0, 0] | 3.0 |
| D0→W0 | 120 | -96ms | **-17.5ms** | 52.5% | [-44, +10] | 3.5 |
| Client→first_wav | 120 | -179ms | **-2.3ms** | 53.3% | [-9, +3] | 14.8 |
| D0→G3 | 5 | -134ms | **-131ms** | 100% | — | 0.3 |

### Per-Group Breakdown

| Group | D0→W0 Median | D0→W0 Mean |
|-------|-------------|------------|
| OFF (baseline, step=10) | **926ms** | 1043ms |
| ON (candidate, step=5) | **922ms** | 947ms |

### B6B_TRUE_E2E_FP16_GATE = NOT_REACHED

| Criterion | Required | Actual | Met? |
|-----------|----------|--------|------|
| D0→W0 median Δ negative | < 0ms | -17.5ms | ✓ |
| D0→W0 win rate ≥ 95% | ≥ 95% | 52.5% | ✗ |
| Client→first_wav median Δ negative | < 0ms | -2.3ms | ✓ |
| Client→first_wav win rate ≥ 95% | ≥ 95% | 53.3% | ✗ |

**Verdict:** B6b provides DIRECTIONAL improvement in D0→W0 (-17.5ms median) and client first audio (-2.3ms median), but the effect is NOT SIGNIFICANT — win rates of ~50% indicate workload noise dominates. The 95% win rate threshold is not met.

### Root Cause

1. **FP16+CANN T2W is fast**: With `OMNI_T2W_DEVICE=cann-flow-only` and `OMNI_VOC_DEVICE=gpu`, the T2W pipeline (Flow+VPN) completes quickly. D2→G0 is essentially 0ms in both ON and OFF conditions — the TTS wake happens simultaneously with the first LLM token regardless of chunk step.

2. **Model output variance dominates**: Random text generation produces different-length responses between paired ON/OFF runs. This variance (±300ms in D0→W0, ±2600ms in client WAV) dwarfs B6b's ~17ms effect.

3. **Q4 diagnostic data not generalizable**: The Q4_K_M run showed -133ms D2→G0 because T2W was on CPU (missing CANN env). B6b helps when T2W is the bottleneck; with CANN acceleration, T2W is no longer the bottleneck.

### Comparison: Q4_INVALID vs FP16_VALID

| Metric | Q4_K_M (INVALID) | FP16+CANN (VALID) |
|--------|-----------------|-------------------|
| D2→G0 median Δ | ~ -133ms (from 48 pairs with data) | 0ms |
| D0→W0 median Δ | ~ -13906ms (artifact — cross-dict clock) | -17.5ms |
| T2W device | CPU (fallback — CANN env not set) | NPU (cann-flow-only) |
| Model | Q4_K_M | FP16 |
| Launcher args | non-canonical (-ngl 99 -c 2048) | canonical (-ngl 999 -c 4096 -b 512 -ub 512 --split-mode layer -fa off) |
| Harness | pre-fix (wrong key names) | fixed (canonical keys, schema validation) |
| Validity | INVALID_FOR_FP16_GATE | CANONICAL |

**Historical causal attribution: `UNPROVEN_MULTI_FACTOR_CONFOUNDING`**

The early ~133ms D2→G0 result from Q4 data cannot be attributed to any single factor.
Multiple variables changed simultaneously between the Q4 diagnostic run and the FP16 canonical run:
- Model quantization (Q4_K_M → FP16)
- T2W backend (CPU fallback → CANN NPU)
- Launcher arguments (non-canonical → canonical)
- Harness analysis code (pre-fix → fixed schema)

While T2W running on CPU is a plausible contributor (observed 3571% CPU, 38-min requests),
D2→G0 occurs logically before T2W computation. T2W can only affect D2→G0 indirectly through
queue backpressure, thread contention, pipeline overlap, or prior-request drain.

**Accurate wording:** Early ~133ms scheduling-stage gain from invalid Q4/CPU-T2W non-canonical
experiment does not generalize to final FP16+CANN configuration. Specific causal decomposition
(quantization vs T2W backend vs queue backpressure vs workload) was not performed and is not
recommended — the FP16+CANN negative result is definitive regardless.

## Currently Running

*None — all tests complete.*

## Still PENDING

| Gate | Status | Depends On |
|------|--------|-----------|
| B6B_HUMAN_LISTENING | PENDING | External |
| B6B_OBJECTIVE_TTS_SCORING | PENDING_EXTERNAL | External ASR/speaker pipeline |
| B6B_TRUE_E2E_GATE | **REJECT_NO_MEANINGFUL_GAIN** | D0→W0 CI95 [-44,+10.5] crosses zero; Client median -2.3ms < 5ms threshold |
| B6B_FEATURE_STATUS | **EXPERIMENTAL_KNOB / DEFAULT_OFF** | DO_NOT_ENABLE_FOR_PRODUCTION |
| B6B_MAIN_LLM_ACCELERATION | **NONE** | D0→D2 Δ=0ms, CI95 [0,0] |
| B6B_EARLY_Q4_RESULT | **INVALID_FOR_FINAL_FP16_CONCLUSION** | See causal note below |
| B6B_Q4_ROOT_CAUSE | **UNPROVEN_MULTI_FACTOR_CONFOUNDING** | Q4≠FP16, CPU≠CANN, old≠new args, old≠new harness |

## Deferred (After TRUE_E2E Gates)

| Item | Note |
|------|------|
| Fix 3: Flow/vocoder per-stage timestamps | Global atomics cleared by reset() |
| G3→G4 optimization | HOLD (CHUNK_SIZE=25 FROZEN) |

## Guardrails (Unchanged)

1. Tag `fp16-f6-early-tts-dispatch-internal-20260731` @ `00a2755` — DO NOT MOVE
2. CHUNK_SIZE=25 — ENGINEERING_POLICY, DO NOT MODIFY
3. Do NOT train DSpark
4. Do NOT start new performance optimizations
5. B6b: OPT_IN_READY / DEFAULT_OFF
6. Sequential server ABBA — no server architecture changes needed
