# F6 R9: DSpark Final Record

**Date:** 2026-07-31
**Status:** REJECTED_BY_CURRENT_BOTTLENECK_EVIDENCE

## Current Measurement Facts

| Metric | Value | Interpretation |
|--------|-------|---------------|
| D0→D2 (main LLM first token) | ~72ms | No measurable improvement needed |
| D0→D2 baseline vs candidate Δ | ~-1ms | Within measurement noise |
| D2→G0 (B6b target) | ~111ms (candidate) | B6b -133ms came from scheduling, not compute |
| G3→G4 (next bottleneck) | ~302ms | Audio token accumulation, not decode compute |

## Why DSpark Is Rejected

B6b's -133ms D2→G0 improvement came from **changing the dispatch threshold** (10→5 tokens), not from accelerating per-step LLM decode. The main LLM D0→D2 is ~72ms and unchanged. The next bottleneck (G3→G4, ~302ms) is Talker audio token accumulation — again not LLM decode compute.

**DSpark targets LLM decode step throughput.** Neither the current bottleneck nor B6b's optimization domain involves decode step throughput. Deploying DSpark would add complexity without addressing any measured bottleneck.

## Re-Evaluation Conditions

DSpark feasibility should be re-evaluated ONLY when ALL of:

1. **Decode compute > 40% of first-audio path**: D0→D2 + per-step decode dominates the critical path
2. **Speak-before decode steps p50 ≥ 3**: Multiple decode steps happen before first TTS dispatch
3. **Oracle speculative upper bound ≥ 15%**: Benchmark shows meaningful headroom vs sequential decode
4. **Runtime verify path feasible**: CANN/msprof can distinguish DSpark overhead from decode gain

| Condition | Current Status | Threshold |
|-----------|---------------|-----------|
| Decode compute share | ~72/527 = 13.7% | > 40% |
| Steps before speak | ~5 valid tokens = ~5 steps | p50 ≥ 3 (marginal) |
| Oracle bound | Not measured | ≥ 15% |
| Verify path | Not instrumented | Feasible |

**None of the four conditions are currently met.**

## Recommendation

```
DSPARK_FEASIBILITY = REJECTED_BY_CURRENT_BOTTLENECK_EVIDENCE
RE_EVALUATE_WHEN = G3→G4 optimized AND decode becomes dominant share
DO_NOT_TRAIN = TRUE
DO_NOT_DEPLOY = TRUE
```
