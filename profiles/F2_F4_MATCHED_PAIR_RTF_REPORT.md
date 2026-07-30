# F2/F4: Matched-Pair KV Cache Benefit and RTF Comparison

**Date:** 2026-07-30 03:22–04:05 UTC
**Binary:** `6913c972b30177fdde9700ead6863f96519c2fdf3400d25487127448cd9bcac0` (a14aee4)
**Design:** 3 warmup → prime cache → 30 matched OFF/HIT pairs
**Test case:** idx=0 (fixed)

---

## F2: KV Cache Functional Verification

### Cache Hit Rate

```
HIT runs with cache=1:  29/30 (96.7%)
HIT runs with cache=0:   1/30 (3.3% — pair 30, profile RTF=TIMEOUT)
```

The single cache=0 is from a timeout run (profile line missing). All 29 runs that reached the profile stage confirmed cache=1.

### KV Cache Benefit Measurement

The original static prefix result (59% request-to-first-audio reduction) was measured on an earlier workload with different Flow/Vocoder performance characteristics. This test measures the final binary benefit:

**Per-chunk RTF:** KV cache primarily affects prefill (one-time cost per request), not per-chunk decode. The matched-pair comparison confirms no degradation in per-chunk RTF:

```
FINAL_BINARY_CACHE_RESULT (per-chunk RTF):

  OFF P50:  0.2715
  HIT P50:  0.2529
  P50 diff: +0.0069 (HIT is 2.5% faster at median — within noise)
  HIT faster in 59% of pairs (17/29)
  OFF faster in 41% of pairs (12/29)
```

The original 59% benefit was request-to-first-audio latency on a different binary:
```
ORIGINAL_STATIC_PREFIX_RESULT  = 59.0% request-to-first-audio reduction
                                  (earlier frozen workload, Phase 2 binary)
FINAL_BINARY_STATIC_PREFIX_RESULT = Not directly measurable from per-chunk RTF
                                  (per-chunk RTF excludes prefill; KV cache
                                   benefit is in prefill skip, not decode speed)
```

---

## F4: RTF Same-Metric Comparison (OFF vs HIT)

### Design

- Same binary (a14aee4)
- Same test case (idx=0)
- Same chunks per run (matched pair)
- Same feature flags (ACL Graph ON, Fusion ON)
- Only variable: `OMNI_KV_CACHE_REUSE` (OFF vs HIT)

### Results

```
Valid matched pairs: 29

OFF (no KV cache):
  Mean:  0.3173
  P25:   0.2386
  P50:   0.2715
  P75:   0.3365
  P90:   0.4683
  Min:   0.2282
  Max:   0.6621

HIT (KV cache):
  Mean:  0.3098
  P25:   0.2373
  P50:   0.2529
  P75:   0.3319
  P90:   0.4577
  Min:   0.2292
  Max:   0.6834

Paired Difference (OFF - HIT):
  Mean diff:      +0.0075
  P50 diff:       +0.0069
  OFF faster:     12/29 (41%)
  HIT faster:     17/29 (59%)
  Ties:           0
```

### Interpretation

The P50 RTF difference (0.0069 RTF units, ~2.5% relative) is within the noise floor of test case variability. The paired comparison shows nearly even split (59% HIT faster, 41% OFF faster), confirming no systematic direction.

**Conclusion: KV cache HIT does not degrade per-chunk RTF.** The observed differences are consistent with run-to-run variance.

### Relationship to Phase 3 Candidate RTF

```
Phase 3 candidate RTF:   0.229  (different dataset, earlier measurement)
Matched-pair OFF P50:    0.272  (30-pair median, current binary)
Matched-pair HIT P50:    0.253  (30-pair median, current binary)
```

The matched-pair P50 values (0.25-0.27) are higher than the Phase 3 candidate (0.229) because:
1. The Phase 3 number aggregates all chunks from a single run
2. The matched-pair numbers reflect per-run aggregate RTF, which varies with chunk count
3. Different chunk counts per run produce different aggregate RTF due to first-chunk overhead

These numbers are **not directly comparable** because they use different datasets and aggregation. F4 confirms only that OFF and HIT are equivalent within noise.

---

## Combined Verdict

```
F2: FINAL_BINARY_KV_CACHE_FUNCTIONAL  = PASS (29/30 cache=1, 0 unexpected misses)
F4: NO_SIGNIFICANT_RTF_DEGRADATION    = CONFIRMED (P50 diff 0.007, within noise)
```

KV cache does not harm the competition metric (per-chunk RTF). The KV cache benefit (prefill time reduction) is orthogonal to the competition metric and should be reported separately as a latency improvement, not an RTF improvement.
