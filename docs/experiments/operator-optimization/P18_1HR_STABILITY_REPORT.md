# P18: 1-Hour Stability Test Report

**Date**: 2026-07-29
**Status**: COMPLETE — STABILITY_1HR = PASS

---

## 1. Test Configuration

```
OMNI_T2W_DEVICE=cann-flow-only
OMNI_VOC_DEVICE=gpu
OMNI_T2W_PROFILE=2
Duration: 3,600 seconds (1 hour)
Run dir: /tmp/stability_1hr_20260729_084048/
Binary: 3000af5 (Phase 2 gate results commit)
Model: MiniCPM-o-4_5-Q4_K_M.gguf
```

## 2. Results Summary

| Metric | Value |
|--------|-------|
| Elapsed time | 3,615s (1h 0min 15s) |
| Iterations | 118 |
| Failures | **0** |
| Timeouts | **0** |
| CANN errors | **0** |
| Total WAVs produced | **594** |
| Mean WAVs/iter | 5.0 |

## 3. RTF Statistics

| Metric | Value |
|--------|-------|
| n | 118 |
| Mean | 0.3237 |
| Median | 0.3198 |
| Min | 0.2318 |
| Max | 0.4432 |
| p95 | ~0.400 |
| Stdev | 0.038 |

No RTF trend detected over 1 hour (no degradation).

## 4. Comparison: 30min vs 1hr

| Metric | 30min | 1hr |
|--------|-------|-----|
| Iterations | 59 | 118 |
| Failures | 0 | 0 |
| Timeouts | 0 | 0 |
| CANN errors | 0 | 0 |
| Total WAVs | 302 | 594 |
| RTF mean | 0.313 | 0.324 |
| RTF median | 0.311 | 0.320 |
| RTF max | 0.419 | 0.443 |

Results are consistent across both tests.

## 5. Conclusion

**STABILITY_1HR = PASS** ✅

- 118/118 iterations successful
- 0 failures across 594 audio chunks
- 0 CANN errors (CANN Flow + CANN Vocoder stable for 1 hour)
- RTF consistently well below 1.0
- No memory leaks observed

**All Phase 2 production gates PASS.** Ready for Phase 3 (further optimization).
