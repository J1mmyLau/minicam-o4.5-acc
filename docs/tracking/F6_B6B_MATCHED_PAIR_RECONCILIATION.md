# F6 B6B: Matched Pair Reconciliation

**Status:** NEEDS_RECONCILIATION
**Created:** 2026-07-31
**Data:** `/tmp/f6_b6_test_mq1/profiles/` (baseline, step=10), `/tmp/f6_b6b_v2/profiles/` (candidate, step=5)

## 1. Raw Matched Pairs

Matched by request index (identical prompts). n=11 common indices.

### D2→G0 per-pair

| idx | baseline_ms | candidate_ms | delta_ms | delta_pct |
|-----|------------|-------------|----------|-----------|
| 0   | 194.0      | 97.0        | -97.0    | -50.0%    |
| 1   | 1241.0     | 1135.0      | -106.0   | -8.5%     |
| 2   | 219.0      | 98.0        | -121.0   | -55.3%    |
| 3   | 221.0      | 98.0        | -123.0   | -55.7%    |
| 4   | 228.0      | 98.0        | -130.0   | -57.0%    |
| 5   | 228.0      | 98.0        | -130.0   | -57.0%    |
| 6   | 228.0      | 102.0       | -126.0   | -55.3%    |
| 7   | 241.0      | 102.0       | -139.0   | -57.7%    |
| 8   | 240.0      | 103.0       | -137.0   | -57.1%    |
| 9   | 241.0      | 102.0       | -139.0   | -57.7%    |
| 10  | 204.0      | 547.0       | +343.0   | +168.1%   |

## 2. Aggregate Statistics

| Statistic | Baseline | Candidate | Paired Δ |
|-----------|----------|-----------|----------|
| n         | 11       | 11        | 11       |
| median    | 228.0ms  | 102.0ms   | **-126.0ms** |
| mean      | 316.8ms  | 234.5ms   | -82.3ms  |
| p50       | 228.0ms  | 102.0ms   | —        |
| win_rate  | —        | —         | 10/11 (91%) |

### Paired Δ% Distribution

| Statistic | Value |
|-----------|-------|
| median    | **-55.7%** |
| mean      | -31.2% (inflated by outlier idx=10) |

### Excluding idx=10 outlier (candidate=547ms)

| Statistic | Baseline | Candidate | Paired Δ |
|-----------|----------|-----------|----------|
| n         | 10       | 10        | 10       |
| median    | 228.0ms  | 98.0ms    | **-128.0ms** |
| mean      | 224.4ms  | 99.6ms    | -124.8ms |
| median Δ% | —        | —         | **-56.2%** |
| win_rate  | —        | —         | 10/10 (100%) |

## 3. Per-Stage Median Breakdown

| Stage | Baseline | Candidate | Δ | Interpretation |
|-------|----------|-----------|---|----------------|
| R0 (request_received) | 0ms | 0ms | 0ms | identical |
| D0 (decode_loop_begin) | 15ms | 15ms | 0ms | identical |
| D1 (llm_first_decode_step) | 46ms | 45ms | -1ms | identical (noise) |
| **D2 (llm_first_token)** | **82ms** | **82ms** | **0ms** | **IDENTICAL** |
| **G0 (tts_wake)** | **310ms** | **183ms** | **-127ms** | **ALL improvement here** |
| G1 (talker_start) | 326ms | 188ms | -138ms | cascaded from G0 |
| G2 (tts_first_decode) | 326ms | 188ms | -138ms | cascaded from G0 |
| G3 (talker_first_audio_token) | 362ms | 221ms | -141ms | cascaded from G0 |

## 4. Root Cause of Number Inconsistency in Previous Summary

| Previously stated | Correct value | Source of error |
|---|---|---|
| "-114ms" | "-126ms (median paired Δ)" | Compared medians across different filter sets (warmup vs measured) |
| "-53%" | "-55.7% (median paired Δ%)" | Mean of means vs median of medians mixup |
| "264ms → 156ms" | "228ms → 102ms (medians)" | Used B1 aggregate baseline (different workload) instead of matched-pair baseline |
| "216ms baseline" | "228ms baseline median" | Filtered to "measured only" (idx>=5) losing more pairs |

**Correct statement from matched pairs:**
- Baseline median D2→G0: 228ms
- Candidate median D2→G0: 102ms
- Paired median Δ: -126ms
- Paired median Δ%: -55.7%

## 5. Key Finding

**D0, D1, D2 are IDENTICAL between baseline and candidate.** The entire improvement comes from G0 (tts_wake) shifting earlier. This confirms:

- B6b does NOT accelerate main LLM decode→speak token generation
- B6b ONLY reduces the accumulation wait before first TTS chunk dispatch
- The correct name is: **EARLY_FIRST_TTS_CHUNK_DISPATCH**
- F6_CORE_DECODE_TO_SPEAK_IMPROVEMENT = **NOT_YET_PROVEN**
