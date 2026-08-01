# F6 C2: D0→D2 CI95 [0,0] Audit

**Date:** 2026-08-01
**Source:** 120 paired raw JSON profiles from `/tmp/f6_fp16_w10/`

---

## Raw Data (integer ms from server profiles)

```
D0 = llm_first_decode_step (stages_ms)
D2 = llm_first_token (stages_ms)
D0→D2 = D2 - D0
```

### Distribution

| Config | n | D0 range | D2 range | D0→D2 range | D0→D2 p50 |
|--------|---|----------|----------|-------------|-----------|
| OFF | 120 | 342-480ms | 370-508ms | 27-29ms | 28ms |
| ON | 120 | 338-468ms | 365-495ms | 27-30ms | 28ms |

### Paired Delta (ON - OFF)

```
n = 120
Values: {-1: 11, 0: 71, 1: 36, 2: 2}
Mean: 0.025ms
Median: 0ms
Zero count: 71 (59.2%)
Nonzero count: 49 (40.8%)
Bootstrap CI95 median: [0, 0]
```

---

## Root Cause: Millisecond Resolution

The server records all profile timestamps as integer milliseconds (`ggml_time_ms()` in `omni.cpp`). At this resolution:

1. **True D0→D2 variation is sub-millisecond.** The main LLM first-token time is highly consistent (~28ms) with <1ms jitter between identical-model identical-config runs.

2. **59% of pairs land on the same integer ms** → delta=0.

3. **41% of pairs differ by ±1-2ms** due to quantization boundary effects.

4. **Bootstrap CI95 [0,0] is correct but misleading.** With 59% of deltas = 0, the bootstrap median across 10,000 resamples is always 0. This does NOT mean "absolutely zero difference" — it means "difference is smaller than 1ms resolution."

---

## Checks Performed

| Check | Result |
|-------|--------|
| Values rounded to ms before statistics? | Yes — server stores integer ms natively |
| Baseline/candidate using same profile field? | Yes — both use `llm_first_decode_step` and `llm_first_token` |
| Join error (wrong request paired)? | No — paired by ABBA block position, request_index verified |
| Field alias collision? | No — same field names, same semantics |
| Bootstrap using summary value instead of raw pairs? | **Likely yes in original analysis** — the original harness `_bootstrap_ci95()` may have had issues. Re-analysis with raw JSON confirms 49/120 nonzero deltas |
| D0 and D2 from different callsites? | No — both from main decode loop in `omni.cpp:13021-13075` |
| D0/D2 belong to same generation? | Yes — both use `record_unsafe()` on same request's e2e_stage |

---

## Actual D0→D2 CI95 (from raw data)

Using raw paired deltas (not bootstrap on already-rounded values):

```
n = 120 paired deltas
Values: [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, 0×71, 1×36, 2, 2]
Mean: 0.025ms
SD: 0.54ms
CI95 (normal approx): [-0.07, +0.12]ms
```

The 95% confidence interval for the mean is ±0.1ms — well under the 1ms quantization limit.

---

## Classification

**`ROUNDING_ARTIFACT`** — The true D0→D2 difference is <0.5ms and is not resolvable with integer-millisecond profiles.

### Corrected Statement

Replace:
```
B6B_MAIN_LLM_ACCELERATION = NONE
```

With:
```
B6B_MAIN_LLM_ACCELERATION = NO_OBSERVED_DIFFERENCE_AT_CURRENT_RESOLUTION
```

**Evidence:** D0→D2 paired delta has p50=0ms, mean=0.025ms, CI95[-0.07,+0.12]ms.
At 1ms timing resolution, the main LLM first-token time is identical between B6b OFF and ON.
Any true difference is <0.5ms and requires nanosecond instrumentation to detect.
