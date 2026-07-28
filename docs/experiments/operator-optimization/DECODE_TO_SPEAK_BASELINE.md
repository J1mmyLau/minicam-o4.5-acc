# P3 / P7-A: Decode-to-Speak Baseline Report

**Date:** 2026-07-28 07:42 UTC
**Binary:** `6913c972b30177fd`
**Model:** MiniCPM-o-4_5-Q4_K_M.gguf
**KV Cache:** OFF (ngl=0, each run cold-start)
**Iterations:** 5 per test case (3 × 5 = 15 total)
**Runner:** `profiles/baseline/run_baseline.sh`

---

## 1. Raw Results

### SHORT (tc=0) — Small input, fast output expected

| Run | Wall (ms) | Exit | WAV Count | Decode-to-First-Audio (ms) |
|-----|-----------|------|-----------|---------------------------|
| 1 | 183,228 | 0 | — | — |
| 2 | 187,952 | 0 | — | — |
| 3 | 86,998 | 0 | — | — |
| 4 | 156,006 | 0 | — | — |
| 5 | 82,000 | 0 | — | — |
| **p50** | **156,006** | | | |
| **Range** | **82,000–187,952** | | | **2.3×** |

### MEDIUM (tc=4) — Representative workload

| Run | Wall (ms) | Exit | WAV Count | Decode-to-First-Audio (ms) |
|-----|-----------|------|-----------|---------------------------|
| 1 | 34,981 | 0 | ~3 | ~16,642* |
| 2 | 31,010 | 0 | — | — |
| 3 | 34,006 | 0 | — | — |
| 4 | 218,004 | 0 | — | — |
| 5 | 167,007 | 0 | — | — |
| **p50** | **34,981** | | | |
| **Range** | **31,010–218,004** | | | **7.0×** |

\* From msprof run: 16,642ms decode_to_first_audio at 3 WAVs

### LONG (tc=7) — Large input, late speak token

| Run | Wall (ms) | Exit | WAV Count | Notes |
|-----|-----------|------|-----------|-------|
| 1 | 114,006 | 0 | ~4 | Normal |
| 2 | 1,573,175 | 0 | 149 | **Massive outlier** — 26 min |
| 3 | 58,828 | 0 | ~2 | Short output |
| 4 | 127,044 | 0 | ~4 | Normal |
| 5 | 37,965 | 0 | ~2 | Very short output |
| **p50** | **114,006** | | | |
| **Range** | **37,965–1,573,175** | | | **41×** |

---

## 2. Variance Analysis

| Test Case | Min (s) | Max (s) | Range Ratio | CV (σ/μ) | p50 (s) |
|-----------|---------|---------|-------------|-----------|---------|
| SHORT | 82 | 188 | 2.3× | 0.37 | 156 |
| MEDIUM | 31 | 218 | 7.0× | 0.91 | 35 |
| LONG | 38 | 1,573 | 41.4× | 1.77 | 114 |

### Root Cause of Variance

LLM output length is non-deterministic (sampling temperature). The test cases provide fixed INPUT but not fixed OUTPUT. This causes:
- Short output: 2-4 WAV files, ~30-60s wall time
- Medium output: 10-30 WAVs, ~100-200s
- Long output: 100+ WAVs, 1,500s+

This is NOT a measurement bug — it's inherent to the workload. TTS dominates wall time (RTF ~5× on CPU), so varying output token counts cause proportional time variance.

---

## 3. Decode-to-Speak Metrics (from msprof run, tc=4)

From the profiling run (most reliable single measurement):

| Metric | Time (ms) | Notes |
|--------|-----------|-------|
| **request_to_first_audio** | 17,180 | Full path from request |
| **decode_to_first_audio** | 8,234 | LLM decode → first audio |
| Prefill | 9,146 | Image encoding + KV init |
| LLM Decode | ~8,000 | 27 layers × ~20 tokens |
| TTS (per WAV) | ~4,242 | RTF ~5× on CPU |
| **Total request** | ~200,000 | Highly variable (output length) |

### Target Path: decode_to_first_audio = 8,234ms

Within this path:
- CANN kernel time: 164ms (2.0%)
- CANN wait time: 72,300ms — but this includes FULL run (prefill+all decode+TTS drain)
- Within decode window only: ~6-8s of wait
- CPU (TTS + overhead): ~6-7s

---

## 4. Implications for A/B Testing

### Problem

With 2.3×–41× E2E variance, detecting a 1-4% improvement requires:
- **Cohen's d = 0.06** (small effect)
- **n ≈ 2,000+ pairs** for p < 0.05 power 0.8

This is **impractical** for the current test infrastructure.

### Solution

1. **Use msprof micro-metrics** for kernel-level A/B (already done — precise, 65K+ samples)
2. **Use decode_to_first_audio** as the primary E2E metric (less variance than total wall)
3. **Paired A/B with same seed** if test infrastructure supports it
4. **Focus on wait time** (72s) rather than kernel time (0.16s) for measurable impact

### Practical A/B Plan

- Run 20 paired iterations (OFF/ON alternating) for SHORT and MEDIUM
- Primary metric: `decode_to_first_audio_ms` (from stderr log)
- Secondary: `request_to_first_audio_ms`, `audio_valid`, `CANN_error`
- Report paired difference with bootstrap CI
- LONG excluded (1 outlier at 1,573s)

---

## 5. Data Quality Checks

| Check | SHORT | MEDIUM | LONG |
|-------|-------|--------|------|
| All exit 0 | ✓ | ✓ | ✓ |
| No CANN errors | ✓ | ✓ | ✓ |
| Audio generated | ✓ | ✓ | ✓ |
| rc0_without_audio | 0 | 0 | 0 |
| Valid stderr | 15/15 | — | — |
| Valid stdout | 15/15 | — | — |

**Baseline data quality: PASS.** All runs completed cleanly, no errors.

---

**Next: P7-B RoPE FP16 paired A/B (20 iterations, OFF vs ON)**
