# KV Cache Soak Status

**Date:** 2026-07-26
**Last update:** 11:20 UTC (pre-compact checkpoint — Stage B complete, CANNBot Phase 1 installed)
**Soak started:** 2026-07-26 03:33 UTC
**Current stage:** Stage B COMPLETE ✅ — Gate passed (13/14). Stage M1 mixed-workload NEXT (pending runner telemetry).

---

## Gates Passed Before Soak

- **P1**: Production-grade cache storage (b2e45ce)
- **P2**: 8 boundary condition gates (58c1fd9) — 20/20 PASS

---

## Stage Progress

| Stage | Duration | Type | Status | Started | Completed | Verdict | Evidence |
|-------|----------|------|--------|---------|-----------|---------|----------|
| A | 1h | HIT_PATH | COMPLETE | 03:33 UTC | 04:33 UTC | PASS (hit) / NOT_CONFIRMED (mixed) | stage_a_20260726_033330/ |
| B | 6h | HIT_PATH | **COMPLETE** ✅ | 05:08 UTC (restart) | 11:10 UTC | **PASS** (13/14 gates) / NOT_CONFIRMED (mixed) | stage_b_20260726_050817/ + STAGE_B_GATE_REPORT.md |
| C (HIT) | 24h | HIT_PATH | **CANCELLED** | — | — | Replaced by M1 mixed-workload | — |
| M1 | 1h | MIXED | **COMPLETE** ✅ | 11:29 UTC | 12:30 UTC | **PASS** (12/12 gates, 81 iters, 0 crash) | stage_mixed_20260726_112936/ + STAGE_M1_GATE_REPORT.md |
| M6 | 6h | MIXED | PENDING | — | — | After M1 gate | — |
| C (MIXED) | 24h | MIXED | PENDING | — | — | After M6 gate | — |
| D | 72h | MIXED | PENDING | — | — | After C gate | — |
| E | 168h | MIXED | PENDING | — | — | After D gate | — |

### Stage A (1h) — Final

**Classification** (99 iterations):
- cache HIT: 94 (94.9%)
- cache MISS: 0 (0%)
- TIMEOUT (180s): 5 (5.1%)

**STAGE_A_HIT_PATH_SOAK = PASS** ✅
- 94 consecutive cache HITs, prefill p50=36.8ms, 0 crashes, 0 leaks

**STAGE_A_MIXED_WORKLOAD_GATE = NOT_CONFIRMED** ⚠️

### Stage B (6h) — COMPLETE ✅

- **Run dir**: `p3-soak/stage_b_20260726_050817/`
- **Duration**: 21,669s (6h 1min), target 21,600s
- **Iterations**: 532
- **Cache HIT**: 532 (100%), **MISS**: 0, **TIMEOUT**: 15 (2.8%)
- **Crash**: 0, **CANN error**: 0, **rc0_without_audio**: 0
- **Temp leaks**: 0, **Cache size change**: 0
- **Prefill**: p50=39.1ms, p95=40.0ms, max=43.5ms
- **Prefill drift**: +0.00% (flat)
- **All 15 timeouts**: HARNESS_TIMEOUT_LONG_VALID_OUTPUT (180s budget, not pipeline defect)

**Gate evaluation**: 13 PASS, 0 FAIL, 1 DESIGN_LIMIT (GATE_10: resource metrics not collected), 1 PENDING → now done (GATE_14)
**Full report**: `p3-soak/STAGE_B_GATE_REPORT.md`
**Audit tool**: `scripts/kv-cache-production/audit_stage_b.py`
**Commit**: f136961

**Coverage**: HIT_PATH_ONLY. MISS/rebuild/ON-OFF/prefix variation/restart/corruption NOT tested.

### Stage M1 (1h Mixed) — PENDING

**Plan**: `KV_CACHE_MIXED_WORKLOAD_PLAN.md`
**7 modes**: HIT, MISS, REBUILD, CACHE_OFF, DIFFERENT_PREFIX, RESTART, CORRUPTION
**Prerequisites** (BLOCKING):
1. Runner telemetry: per-iteration RSS/HBM/FD/thread collection
2. Adaptive timeout: p99 historical + safety margin
3. Code audit + bash syntax check
4. Commit

---

## Current State Terminology

| What to write | What NOT to write |
|--------------|-------------------|
| STAGE_B_HIT_PATH_SOAK: PASS (532/532 HIT, 0 crash) | Stage B all-clear / production-ready |
| STAGE_B_MIXED_WORKLOAD: NOT_CONFIRMED | Mixed workload validated |
| STAGE_M1: PENDING (blocked on runner telemetry) | Ready to start |
| KV_CACHE_PRODUCTION: OPT_IN_READY / DEFAULT_OFF | DEFAULT_ON |

## Production Status

```
KV_CACHE_PRODUCTION: OPT_IN_READY / DEFAULT_OFF
```

**Rationale**: P1 storage + P2 boundary gates + Stage A+B hit-path soak all pass.
Mixed workload (miss/rebuild/ON-OFF/prefix/restart/corruption) NOT confirmed.
Minimum 72h mixed-workload soak needed before DEFAULT_ON consideration.
**Do NOT claim DEFAULT_ON.**

---

## CANNBot Phase 1

| Item | Status |
|------|--------|
| Skills discoverable | 17 |
| Core profiling skills | 6 installed |
| Agents | 6 SOTA subagents |
| CLAUDE.md | Restored regular file (NOT symlink) |
| .claude/CLAUDE.md | Plugin symlink retained |

---

## Audit Tool

```
python3 scripts/kv-cache-production/audit_stage_b.py <run_dir>
```

Read-only. No modification of runner files or binary.

---

**最后更新:** 2026-07-26 11:20 UTC (pre-compact checkpoint)
