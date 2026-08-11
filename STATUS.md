# Dual-CANN Flow/Vocoder Pipeline — STATUS

**Branch:** `perf/vocoder-cann-pipeline`
**Base commit:** `051e993` (frozen F16 candidate)
**Date:** 2026-08-11
**Binary SHA:** `ce1312e7f9e3c5e0afae0479c41ae8fbacf61c51df412296a8922a38cf5ee9d7`

## Final Decision

**DUAL_CANN_PIPELINE_PROMOTION = YES**

Config D (pipeline CANN+CANN) aggregate LOCAL_SPEAK_RTF = 0.4260 vs
Config A (pipeline CANN+CPU) aggregate LOCAL_SPEAK_RTF = 0.4883.
E2E speedup = 1.146× (−14.6%). Exceeds 5% threshold.

## Phase Summary

| Phase | Status | Summary |
|-------|--------|---------|
| Phase 0 (Worktree) | DONE | Worktree from 051e993, binary built (662b4b0) |
| Phase 1 (No-Code Feasibility) | PASS | Dual-CANN pipeline works with zero code changes |
| Phase 2 (Correctness) | PASS | 726 windows: non-silent, 0 Inf |
| Phase 3 (Overlap Proof) | CONFIRMED | 20/725 pairs overlap (2.8%); Flow dominates critical path |
| Phase 4 (Performance Model) | COMPLETE | c_flow=0.18, critical path=156ms |
| **Phase 5 (E2E Gate)** | **PASS** | **30+30: D 0.4260 vs A 0.4883 → 1.146× (−14.6%), PROMOTED** |

## Final Paired E2E A/B (30+30 sessions)

| Config | OVERLAP | Flow | Vocoder |
|--------|---------|------|---------|
| **A (FROZEN)** | 1 | CANN | CPU (8 threads) |
| **D (CANDIDATE)** | 1 | CANN | CANN |

| Config | N valid | Aggregate RTF | Per-session p50 | Per-session p90 |
|--------|---------|---------------|-----------------|-----------------|
| A | 30/30 | **0.4883** | 0.4664 | 0.6278 |
| D | 30/30 | **0.4260** | 0.3740 | 1.4069 |

```
ACTUAL_E2E_SPEEDUP = 1.146× (−14.6%)
DUAL_CANN_PIPELINE_PROMOTION = YES
```

## Pipeline Diag (Config D, 726 windows)

| Metric | Value |
|--------|-------|
| Flow CANN | mean=155.9ms p50=156.7ms |
| Vocoder CANN | mean=113.4ms p50=112.6ms |
| Effective critical path | mean=156.0ms |
| Serial equivalent | mean=269.3ms |
| Pipeline speedup vs serial | 1.73× |
| Overlap ratio | 2.8% (20/725) |
| Contention c_flow | 0.181 |

## Why D Wins

Flow dominates the critical path. Vocoder CPU (432ms) → Vocoder CANN (113ms) shrinks critical path from 432ms to 156ms. Overlap is low (Flow is bottleneck) but the gain comes from replacing slow CPU vocoder with fast CANN vocoder.

## State

```
051e993                  = FROZEN_BASELINE
perf/vocoder-cann-pipeline = EXPERIMENT_COMPLETE (dual-CANN PROMOTED)
perf/vocoder-cann         = EXPERIMENT_COMPLETE (serial REJECTED)
```
