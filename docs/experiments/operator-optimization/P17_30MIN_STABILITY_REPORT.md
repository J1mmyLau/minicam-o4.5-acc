# P17: 30-Minute Stability Test Report

**Date**: 2026-07-29
**Status**: COMPLETE — STABILITY_30MIN = PASS

---

## 1. Test Configuration

```
OMNI_T2W_DEVICE=cann-flow-only
OMNI_VOC_DEVICE=gpu
OMNI_T2W_PROFILE=2
Duration: 1,800 seconds (30 minutes)
Run dir: /tmp/stability_30min_20260729_080544/
Binary: 189fc96 (BREAKTHROUGH_CHECKPOINT)
Model: MiniCPM-o-4_5-Q4_K_M.gguf
```

## 2. Results Summary

| Metric | Value |
|--------|-------|
| Elapsed time | 1,802s (30min 2s) |
| Iterations | 59 |
| Failures | 0 |
| Timeouts | 0 |
| CANN errors | 0 |
| Total WAVs produced | 302 |
| Mean WAVs/iter | 5.1 |
| RTF mean | 0.3129 |
| RTF median | 0.3110 |
| RTF stdev | 0.0331 |
| RTF min | 0.2566 |
| RTF max | 0.4194 |
| RTF p95 | 0.3710 |

## 3. Per-Iteration RTF Consistency

```
RTF distribution (n=59):
  0.25-0.29:  ████████████ (12)
  0.29-0.33:  ████████████████████████████████████████ (39)
  0.33-0.37:  ███ (3)
  0.37-0.42:  █████ (5)
```

No RTF trend (no degradation over time). CV = 0.0331/0.3129 = 10.6%.

## 4. T2W-L3: Rapid Successive Requests

| Iter | RC | WAVs | RTF | CANN err |
|------|-----|------|-----|----------|
| 0 | 0 | 3 | 0.378 | 0 |
| 1 | 0 | 5 | 0.314 | 0 |
| 2 | 0 | 3 | 0.369 | 0 |
| 3 | 0 | 6 | 0.325 | 0 |
| 4 | 0 | 14 | 0.275 | 0 |

**5/5 PASS, 0 failures, 0 CANN errors. No cooldown between iterations.**

## 5. Test Case Coverage

Each iteration cycled through 9 test cases (omni_test_case_0000-0008). All 9 cases produced valid audio with 0 CANN errors.

## 6. Known Minor Issue

Concurrent stdout writes from multiple threads can produce garbled log lines (timestamps interleaved with log text). This is cosmetic only — `AUDIO_SUCCESS` is always present in the log, grep just needs to handle the corruption. Not a CANN or T2W issue.

## 7. Conclusion

**STABILITY_30MIN = PASS** ✅

- 0 crashes across 59 requests (302 audio chunks)
- 0 CANN errors across all iterations
- RTF consistently below 0.5 (max 0.419, well below 1.0 realtime)
- No memory leak detected (consistent iteration time)
- Rapid successive requests: 5/5 PASS

**Next gate: STABILITY_1HR (running)**
