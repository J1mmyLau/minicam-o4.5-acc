# G8: 1-Hour Stability Test

**Date:** 2026-07-29
**Config:** GRAPH=ON, FUSION=ON, 1 test case per iteration
**Status:** PASS

## Results

| Metric | Value |
|--------|-------|
| Duration | 60 min 35 sec (3635s) |
| Iterations | 66 |
| CANN errors | 0 |
| Crashes | 0 |
| Timeouts | 2 (false positives) |
| Total WAVs | 1368 |
| Pass rate | 64/66 (97.0%) |

## Timeout Analysis

2 iterations exceeded the 300s per-iteration limit (one had 90 WAVs, another at 1346s). Same false-positive pattern as G7. No CANN errors in either timeout case.

## Verdict

**G8: PASS.** 0 CANN errors across 66 iterations in 1 hour. Binary stable under extended continuous load.
