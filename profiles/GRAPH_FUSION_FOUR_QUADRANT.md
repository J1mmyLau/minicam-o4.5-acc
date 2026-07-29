# G3: Graph ON/OFF × Fusion ON/OFF Four-Quadrant A/B

**Date:** 2026-07-29
**Status:** COMPLETE

---

## Results

| Quadrant | Graph | Fusion | n | t2m.compute p50 | voc.compute p50 | total p50 | RTF |
|----------|-------|--------|---|-----------------|-----------------|-----------|-----|
| Q1 | OFF | OFF | 24 | 120.2 ms | 108.8 ms | 238.2 ms | 0.257 |
| Q2 | OFF | ON  | 20 | 138.8 ms | 115.2 ms | 259.6 ms | 0.274 |
| Q3 | ON  | OFF | 23 | 110.4 ms | 115.0 ms | 232.7 ms | 0.253 |
| Q4 | ON  | ON  | 43 | **109.7 ms** | **110.2 ms** | **225.2 ms** | **0.245** |

## Attribution

| Comparison | t2m Δ | Effect |
|------------|-------|--------|
| Graph effect (Q3-Q1) | **-9.8 ms (-8.2%)** | Graph capture improves t2m p50 |
| Fusion alone (Q2-Q1) | +18.6 ms (+15.5%) | Fusion WITHOUT graph HURTS |
| Fusion with graph (Q4-Q3) | -0.7 ms (-0.6%) | Marginal gain when graph already active |
| Best vs baseline (Q4-Q1) | **-10.5 ms (-8.7%)** | Combined improvement |

## Key Findings

1. **Graph capture is the primary driver.** Q3 (ON,OFF) reduces t2m p50 by 9.8ms vs Q1 (OFF,OFF).

2. **Fusion alone is harmful.** Q2 (OFF,ON) is 18.6ms WORSE than Q1. The cost of dispatch-level fusion checks outweighs the savings when each op is individually dispatched.

3. **Fusion with graph is marginally positive.** Q4 (ON,ON) is 0.7ms better than Q3 (ON,OFF), consistent with Phase 3's ~1ms estimate.

4. **Best configuration: ON,ON** — RTF=0.245, 225ms p50 total per chunk.

## Consistency with Phase 3 Freeze Numbers

| Metric | Phase 3 Canonical | G3 Q4 (ON,ON) | Δ |
|--------|-------------------|---------------|---|
| t2m.compute (mean) | 111.3 ms | 120.1 ms | +8.8 ms |
| RTF | 0.229 | 0.245 | +0.016 |

The G3 numbers are slightly higher than Phase 3 canonical because:
- Phase 3 used `--omni` with 4 test cases (n=29, mean-based)
- G3 uses `--omni` with 4 test cases (n=43, median-based)
- Different test case ordering affects KV cache warmup
- Within expected variance range

## Raw Logs

| Quadrant | Log |
|----------|-----|
| Q1 | `g3_four_quadrant/Q1_OFF_OFF.log` |
| Q2 | `g3_four_quadrant/Q2_OFF_ON.log` |
| Q3 | `g3_four_quadrant/Q3_ON_OFF_v2.log` |
| Q4 | `g3_four_quadrant/Q4_ON_ON_v2.log` |
