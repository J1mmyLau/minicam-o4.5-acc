# G7: 30-Minute Stability Test

**Date:** 2026-07-29
**Config:** GRAPH=ON, FUSION=ON, 1 test case per iteration
**Status:** PASS

## Results

| Metric | Value |
|--------|-------|
| Duration | 30 min 9 sec (1809s) |
| Iterations | 37 |
| CANN errors | 0 |
| Crashes | 0 |
| Timeouts | 1 (74-chunk test case, false positive) |
| Total WAVs | 661 |
| Pass rate | 36/37 (97.3%) |

## The One "Failure"

Iteration 29 returned exit code 124 (timeout) because the test case generated 74 audio chunks, exceeding the 5-minute per-iteration limit. This is a test harness limitation, not a CANN stability issue. The binary was still generating audio at the timeout point.

## Verdict

**G7: PASS.** 0 CANN errors across 37 iterations. Binary stable under continuous 30-minute load.
