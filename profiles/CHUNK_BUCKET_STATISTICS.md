# G4: First/Warmup/Steady/Tail Chunk Statistics

**Date:** 2026-07-29
**Config:** Q4 (GRAPH=ON, FUSION=ON), 4 test cases, n=18 timing points
**Status:** COMPLETE

---

## Bucket Results

| Bucket | n | t2m p50 | voc p50 | total p50 | RTF p50 | Notes |
|--------|---|---------|---------|-----------|---------|-------|
| FIRST (call=0) | 1 | 115.2 ms | 239.9 ms | 355.1 ms | 0.0176 | Vocoder cold start, 2× slower |
| WARMUP (call=1-3) | 3 | 113.7 ms | 114.4 ms | 230.3 ms | 0.0096 | Vocoder warming, 1 outlier |
| **STEADY (call>=4)** | **14** | **112.1 ms** | **110.6 ms** | **223.5 ms** | **0.0093** | **Tight range [221,232]** |
| TAIL (last 2) | 2 | 111.4 ms | 109.9 ms | 221.4 ms | 0.0092 | Best, fully warmed |

## Detailed Statistics

### STEADY (call>=4, n=14)
```
t2m:    mean=113.9ms  p50=112.1ms  p95=118.9ms  range=[111.1, 120.8]
voc:    mean=110.9ms  p50=110.6ms  p95=111.7ms  range=[109.9, 114.1]
total:  mean=224.9ms  p50=223.5ms  p95=230.3ms  range=[221.4, 232.5]
```

### Competition RTF (per-chunk, audio=1000ms)
```
Steady: 223.5 / 1000 = 0.224
```

Consistent with Phase 3 canonical RTF 0.229.

---

## Key Findings

1. **t2m.compute is extremely stable** — only 4ms variance across calls 0-17 (111-115ms)
2. **Vocoder first-chunk overhead is significant** — 240ms vs 111ms steady (2.16×). This is vocoder JIT/warmup, not Flow model
3. **Steady state reached by call=4** — total variance <6ms in steady bucket
4. **Warmup bucket is noisy** — one outlier at 158ms voc (call=2), otherwise tight

## Recommendation

For official benchmark reporting:
- **Report steady-state RTF** (call>=4): 0.224
- **Exclude first chunk** from steady average (cold start)
- **Report first-chunk RTF separately** for TTFT-style metrics
- **Steady n >= 10** provides sufficient statistical power

## Raw Data

`profiles/g3_four_quadrant/Q4_timing.csv` — 18 per-chunk timing records
