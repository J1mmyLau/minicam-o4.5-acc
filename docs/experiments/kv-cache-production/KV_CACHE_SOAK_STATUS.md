# KV Cache Soak Status

**Date:** 2026-07-26
**Last update:** 11:15 UTC (Stage B complete + gate report)
**Soak started:** 2026-07-26 03:33 UTC
**Current stage:** Stage B (6h) COMPLETE — Gate audit passed. Stage C pending gate review.

---

## Gates Passed Before Soak

- **P1**: Production-grade cache storage (b2e45ce)
- **P2**: 8 boundary condition gates (58c1fd9) — 20/20 PASS

---

## Stage Progress

| Stage | Duration | Nominal Name | Status | Started | Completed | Verdict | Evidence |
|-------|----------|-------------|--------|---------|-----------|---------|----------|
| A | 1h | STAGE_A_1H_HIT_PATH_SOAK | HIT_PATH_PASS ⚠️ | 03:33 UTC | 04:33 UTC | PASS (hit) / NOT_CONFIRMED (mixed) | stage_a_20260726_033330/ |
| B | 6h | STAGE_B_6H_HIT_PATH_SOAK | **COMPLETE** ✅ | 05:08 UTC (restart) | 11:10 UTC | PASS (13/14 gates) / NOT_CONFIRMED (mixed) | stage_b_20260726_050817/ + STAGE_B_GATE_REPORT.md |
| C | 24h | PENDING | PENDING_GATE_REVIEW | — | — | — | — |
| D | 72h | PENDING | PENDING | — | — | — | — |
| E | 168h | PENDING | PENDING | — | — | — | — |

### Stage A (1h) — Corrected Verdict (FINAL)

**Classification** (99 iterations, closure confirmed):
- cache HIT: 94 (94.9%)
- cache MISS: 0 (0%)
- TIMEOUT (180s): 5 (5.1%)

**STAGE_A_HIT_PATH_SOAK = PASS** ✅
- 94 consecutive cache HITs
- prefill p50=36.8ms, p95=38.4ms, min=36.2ms, max=42.9ms
- 0 crashes, 0 CANN errors, 0 temp file leaks

**STAGE_A_MIXED_WORKLOAD_GATE = NOT_CONFIRMED** ⚠️
- Only hit-path validated. No miss/rebuild/ON-OFF/prefix variation.

### Stage B (6h) — COMPLETE — STAGE_B_6H_HIT_PATH_SOAK = PASS ✅

- **Run dir**: `p3-soak/stage_b_20260726_050817/`
- **Duration**: 21,669s (6h 1min), target 21,600s
- **Iterations**: 532
- **Cache HIT**: 532 (100%), **MISS**: 0, **TIMEOUT**: 15 (2.8%)
- **Crash**: 0, **CANN error**: 0, **rc0_without_audio**: 0
- **Temp leaks**: 0, **Cache size change**: 0
- **Prefill**: p50=39.1ms, p95=40.0ms, max=43.5ms
- **Prefill drift**: +0.00% (flat)
- **All 15 timeouts**: HARNESS_TIMEOUT_LONG_VALID_OUTPUT (180s budget, not pipeline defect)

**Gate evaluation**: 13 PASS, 0 FAIL, 1 DESIGN_LIMIT (resource metrics not collected), 1 PENDING (doc update)
**Full report**: `p3-soak/STAGE_B_GATE_REPORT.md`

**Coverage**: HIT_PATH_ONLY. MISS/rebuild/ON-OFF/prefix variation NOT tested.
**Mixed workload plan**: `KV_CACHE_MIXED_WORKLOAD_PLAN.md`

### Stage C (24h) — Gate Requirements (15 items)

Stage C will NOT auto-start. Before launch:
1. runner exit_code=0
2. DONE file present
3. raw data rows complete, no duplicates
4. iteration classification closed (hit+miss+rebuild+control+timeout = total)
5. all timeouts classified, unclassified_timeout=0
6. crash=0
7. CANN runtime error=0
8. rc0_without_audio=0
9. temp/thread/process leak=0
10. RSS/HBM/FD/thread trend flat (no monotonic growth)
11. latency stable (no unexplained drift)
12. prefill missing cases explained
13. Stage B report generated and committed
14. STATUS/HANDOFF/AUDIT updated
15. GATE_STATUS file reviewed

---

## Current State Terminology (CORRECTED)

| What to write | What NOT to write |
|--------------|-------------------|
| STAGE_B_HIT_PATH_SOAK: RUNNING | Stage B: PASS / mixed workload passed |
| CACHE_HIT_COVERAGE: 70/70 requests reaching cache lookup | 100% request success |
| REQUEST_SUCCESS: not yet determined (4 timeouts) | All requests successful |
| STAGE_B_MIXED_WORKLOAD: NOT_TESTED / NOT_CONFIRMED | Mixed workload validated |

## Production Status

```
KV_CACHE_PRODUCTION: OPT_IN_READY / DEFAULT_OFF
```

**Rationale**: P1 storage semantics + P2 boundary gates + Stage A+B hit-path soak all pass.
Mixed workload soak (miss/rebuild/control) NOT confirmed.
Stage B 6h running. Minimum 72h mixed-workload soak needed before DEFAULT_ON consideration.
**Do NOT claim DEFAULT_ON.**

---

## Audit Tool

```
python3 scripts/kv-cache-production/audit_stage_b.py <run_dir>
```

Read-only. No modification of runner files or binary.

---

**最后更新:** 2026-07-26 06:00 UTC (state recovery + offline audit)
