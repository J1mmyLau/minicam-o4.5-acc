# F5: Terminology Audit — Forbidden and Permitted Language

**Date:** 2026-07-30

---

## Audit Results

### Previously Used (Forbidden)

| Phrase | Where Used | Why Forbidden | Replacement |
|--------|-----------|---------------|-------------|
| "ALL_PRODUCTION_GATES_CLOSED" | STATUS.md, HANDOFF.md, G13 | G5 is BLOCKED, official benchmarks pending | INTERNAL_INTEGRATION_GATES_COMPLETE |
| "13/14 PASS" | STATUS.md, HANDOFF.md | Arithmetic inconsistency (13+1+1=15≠14) | 12/14 confirmed PASS, 1 BLOCKED, 1 DEFERRED |
| "PRODUCTION_READY" | Implicit in gate language | Official accuracy validation not done | INTERNAL_INTEGRATION_CANDIDATE |
| "OFFICIAL_SUBMISSION_PASS" | Not explicitly used | Would be misleading | OFFICIAL_BENCHMARK_BLOCKED_EXTERNAL |
| "OFFICIAL_SCORE" | Not explicitly used | Would be misleading | INTERNAL_RTF |
| "PRESERVED_EXACTLY_59_PERCENT" | Not explicitly used | Not verified on final binary | FINAL_BINARY_CACHE_RESULT (pending F2) |
| "MISSION COMPLETE" | Session summary | Implies finality; benchmarks pending | INTERNAL_INTEGRATION_GATES_COMPLETE |

### Current Permitted Language

```
INTERNAL_PERFORMANCE_GATE       = PASS
INTERNAL_DEMO_GATE              = PASS
INTERNAL_STABILITY_GATE         = PASS
CLEAN_REPRODUCTION_GATE         = PASS
KV_CACHE_FUNCTIONAL_GATE        = PASS
MULTI_PREFIX_AND_CORRUPTION     = PASS
T2W_LIFECYCLE                   = PASS

INTERNAL_FINAL_INTEGRATION_CANDIDATE = YES
KV_CACHE_OPT_IN_READY               = YES
KV_CACHE_DEFAULT_OFF                 = YES

OFFICIAL_BENCHMARK_GATE              = BLOCKED_EXTERNAL
OFFICIAL_SUBMISSION_PASS             = NO
IM2COL_OPTIMIZATION                  = DEFERRED
```

---

## RTF Number Attribution (F4 preamble)

Five RTF numbers exist in the project. Each must be labeled with its dataset and scope:

| RTF | Label | Dataset | Chunk Class | N | Source |
|-----|-------|---------|-------------|---|--------|
| 0.245 | 4-Quadrant A/B best | Single run, Q4(ON,ON) | All chunks | 1 run | G3 |
| 0.224 | Steady-state bucket | Single run, call≥4 | Steady only | 1 run | G4 |
| 0.229 | Phase 3 candidate | Internal measurement | All chunks | Phase 3 freeze | Phase 3 |
| 0.236 | Clean build reproduction | Fresh build, same config | All chunks | 1 run | G12 |
| TBD | Final binary matched-pair | 30 matched OFF/HIT pairs | All chunks | 60 runs | F2/F4 (running) |

**None of these is an official competition score.** The official score must be measured using the competition harness.

---

## KV Cache Benefit Attribution (F2 preamble)

The original "59% static prefix benefit" was measured on an earlier frozen workload with different Flow/Vocoder performance. The final binary measurement (F2, in progress) must be reported independently:

```
ORIGINAL_STATIC_PREFIX_RESULT  = 59.0% request-to-first-audio reduction
                                  (earlier frozen workload, different binary)

FINAL_BINARY_STATIC_PREFIX_RESULT = TBD%
                                  (30 matched OFF/HIT pairs, current binary a14aee4)
```

The final result may differ from 59% because the end-to-end latency composition has changed (Flow: 155→111ms, Vocoder: ~119ms). Reduced prefill time becomes a smaller fraction of total latency.

---

## Files Requiring Correction

| File | Status |
|------|--------|
| `STATUS.md` | ✅ CORRECTED |
| `HANDOFF.md` | ⏭️ PENDING |
| `G13_SUBMISSION_PACKAGE.md` | ⏭️ PENDING (F7) |
| `G11_T2W_LIFECYCLE_REPORT.md` | ✅ Updated via F1 |
| `P4_FINAL_INTEGRATED_PERFORMANCE_REVIEW.md` | ⚠️ Contains "no regression" claim without matched CI |
