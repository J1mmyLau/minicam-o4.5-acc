# F6 B6B TRUE_E2E Gate — Engineering Threshold Analysis

**Date:** 2026-08-01
**Data:** 120 FP16+CANN strict matched pairs
**Source:** `/tmp/f6_fp16_w10/F6_B6B_FP16_CANONICAL_120_PAIRS.csv`

---

## Engineering Thresholds

Since no project-defined performance contract specifies first-audio latency margins,
conservative internal engineering thresholds are applied:

| Threshold | Value | Rationale |
|-----------|-------|-----------|
| `SERVER_D0_TO_W0_MARGIN_MS` | **10ms** | Minimum server-side improvement worth retaining (1.1% of 922ms baseline) |
| `CLIENT_FIRST_AUDIO_MARGIN_MS` | **5ms** | Minimum client-perceptible improvement worth retaining (0.05% of 10.4s baseline) |
| `RELATIVE_GAIN_MARGIN` | **2%** | Minimum relative improvement |
| **Status** | `INTERNAL_ENGINEERING_THRESHOLD` | Not from external performance contract |

---

## Classification Framework

| Class | Definition |
|-------|-----------|
| `PASS_MEANINGFUL_GAIN` | CI95 entirely below zero AND median Δ exceeds threshold |
| `REJECT_NO_MEANINGFUL_GAIN` | CI95 entirely within [-threshold, +threshold] |
| `REJECT_BELOW_ENGINEERING_THRESHOLD` | Benefit direction correct but magnitude below retention threshold |
| `INCONCLUSIVE_WIDE_CI` | CI95 covers both meaningful benefit AND zero/positive |

---

## D0→W0 Analysis

```
Baseline (OFF):  median=922ms, mean=1043ms
Candidate (ON):  median=927ms, mean=947ms
Paired Δ:        median=-17.5ms, mean=-96.1ms
CI95 (bootstrap): [-44.0, +10.5]ms
Win rate:        52.5%
Stdev:           338ms
CV:              3.5
```

| Criterion | Required | Actual | Met? |
|-----------|----------|--------|------|
| Median Δ negative | < 0ms | -17.5ms | ✓ |
| CI95 entirely below zero | upper < 0 | +10.5ms | ✗ |
| Median Δ exceeds margin | < -10ms | -17.5ms | ✓ |
| Relative gain exceeds 2% | > 2% of 922ms = 18.4ms | — | ✗ (median -17.5ms < 18.4ms) |

**Classification: `INCONCLUSIVE_WIDE_CI`**

The CI95 extends to -44ms (which would be meaningful) but also to +10.5ms (crossing zero).
The data cannot rule out a meaningful benefit, but also cannot confirm one.
The wide CI (span 54.5ms) relative to the median effect (-17.5ms) indicates workload noise dominates.

---

## Client First Audio Analysis

```
Baseline (OFF):  median=10424ms, mean=11340ms
Candidate (ON):  median=10422ms, mean=11162ms
Paired Δ:        median=-2.3ms, mean=-179ms
CI95 (bootstrap): [-8.5, +2.7]ms
Win rate:        53.3%
Stdev:           2636ms
CV:              14.8
```

| Criterion | Required | Actual | Met? |
|-----------|----------|--------|------|
| Median Δ negative | < 0ms | -2.3ms | ✓ |
| CI95 entirely below zero | upper < 0 | +2.7ms | ✗ |
| Median Δ exceeds margin | < -5ms | -2.3ms | ✗ |
| Relative gain exceeds 1% | > 1% of 10424ms = 104ms | — | ✗ |

**Classification: `REJECT_BELOW_ENGINEERING_THRESHOLD`**

The median client benefit (-2.3ms) is below the 5ms absolute threshold and well below
the 1% relative threshold (104ms). The CI95 [-8.5, +2.7] upper bound crosses zero.

---

## Combined Gate Decision

**B6B_TRUE_E2E_FP16_GATE = `REJECT_NO_MEANINGFUL_GAIN`**

Rationale:
1. **D0→W0**: CI95 crosses zero → INCONCLUSIVE (noise-dominated)
2. **Client first audio**: median -2.3ms below 5ms threshold → BELOW_THRESHOLD
3. **Win rates**: 52.5% and 53.3% → essentially random
4. **CV ratios**: 3.5 and 14.8 → signal buried in noise
5. **Neither metric** independently passes its threshold

Combined classification uses the stricter of the two individual classifications.
Since client audio is BELOW_THRESHOLD and server is INCONCLUSIVE:
→ **REJECT_NO_MEANINGFUL_GAIN**

This means: the measured effect is too small to be distinguished from zero
given the workload variance, and the median client benefit (2.3ms) is below
any reasonable engineering retention threshold.

---

## TOST Equivalence Check

For completeness, a Two One-Sided Test (TOST) approach:

**Null hypothesis (inferiority):** B6b Δ ≥ +MARGIN (B6b is worse or same)
**Null hypothesis (non-superiority):** B6b Δ ≤ -MARGIN (B6b is meaningfully better)

For D0→W0 with MARGIN=10ms:
- The CI95 [-44, +10.5] includes values both below -10ms and above +10ms
- Cannot reject either null → **INCONCLUSIVE**

For Client with MARGIN=5ms:
- The CI95 [-8.5, +2.7] does not include values below -5ms (excluding the tail)
- Cannot establish superiority → **FAILS non-inferiority at 5ms**

---

## What Would Be Required for PASS

To achieve `PASS_MEANINGFUL_GAIN`, B6b would need:

1. **D0→W0**: CI95 entirely negative AND median ≤ -18.4ms (2% relative)
2. **Client first audio**: CI95 entirely negative AND median ≤ -5ms

With the current workload variance (σ=338ms server, σ=2636ms client),
the sample size required to achieve these CIs would be:

```
n = (Z * σ / desired_width)^2
Server: (1.96 * 338 / 10)^2 ≈ 4,400 pairs
Client: (1.96 * 2636 / 5)^2 ≈ 1,070,000 pairs
```

This is infeasible with random text generation workload.
A fixed-output workload would be required for narrower CIs.

---

## Conclusion

> B6b does NOT demonstrate meaningful end-to-end first-audio improvement
> in the FP16+CANN configuration. The median client-observed benefit is
> approximately 2.3ms, well below any reasonable engineering threshold.
> The D0→W0 CI95 crosses zero, indicating the measured -17.5ms server
> improvement is not statistically distinguishable from noise.
