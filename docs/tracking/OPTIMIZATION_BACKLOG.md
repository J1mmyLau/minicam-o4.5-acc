# Optimization Backlog — CANN-level Profiling

**Profile:** 20260716-131033-full-omni-msprof
**Date:** 2026-07-16
**Updated:** 2026-07-16 (TASK-007 re-ranking)

---

## Priority Ranking (TASK-007)

See `OPTIMIZATION_PRIORITY.md` for full scores and methodology.

| # | Candidate | Layer | Cost | Score |
|---|-----------|-------|------|-------|
| 1 | CAND-002: Sync memcpy → Async | L2 | 2325ms | 8.89 |
| 2 | CAND-003: Memory allocation pooling | L2 | 1170ms | 6.67 |
| 3 | CAND-004: Reduce Cast/Transpose/Contiguous | L2 | 336ms | 2.25 |
| 4 | CAND-001: Reduce SyncStream calls | L2 | 173ms | 7.50 |
| 5 | CAND-005: Fuse element-wise ops | L5 | 126ms | 0.50 |
| 6 | CAND-006: Overlap vision/audio encode | L3 | 4300ms | 0.32 |
| 7 | CAND-007: Token2Wav pipeline | L3 | 110000ms | 1.60 |
| 8 | CAND-008: MatMul shape/layout | L5 | 1834ms | 0.27 |

## First Batch Experiments

| Exp | Candidate | Directory | Status |
|-----|-----------|-----------|--------|
| EXP-001 | CAND-002 | `harness/experiments/EXP-001-sync-memcpy/` | PLANNED |
| EXP-002 | CAND-003 | `harness/experiments/EXP-002-memory-allocation-pooling/` | PLANNED |
| EXP-003 | CAND-004 | `harness/experiments/EXP-003-cast-layout/` | PLANNED |

## AscendC Gate: NOT SATISFIED

See `TASK-007_CONCLUSION.md` §6 for detailed reasoning.

