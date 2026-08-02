# F6 Phase 3 — N9 183 write_after_finalize Reconciliation (R6)

**Date:** 2026-08-02
**HEAD:** `aabd12e`

## Executive Summary

**N9 gate: FAILED — cross-request contamination confirmed**

The 183 `write_after_finalize` detections were all correctly REJECTED (accepted=0). However, the N9 sync profiles reveal a MORE SERIOUS problem: 19/20 profiles have `stale_write_count > 0` and `cross_request_write_count > 0`, totaling 298 stale and 298 cross-request write detections. This proves per-request stage attribution is BROKEN under rapid A→B transitions.

## Counter Breakdown

### TalkerStepBuffer (audio profile — N6 guard)

| Counter | Value | Meaning |
|---------|-------|---------|
| write_after_finalize_detected | **183** | 183 talker step writes attempted after finalize() |
| write_after_finalize_accepted | **0** | All 183 correctly rejected by N6 finalize gate ✓ |
| late_write_rejected | **0** | No late-write detection |
| invalid_generation_write | **0** | No invalid generation writes |
| Affected request count | **1** (request index 3 of 20) | |
| Affected steps lost | **183** | Talker step data lost for 1 request |

### Per-Stage Recording (sync profile — generation guard)

| Counter | Value | Status |
|---------|-------|--------|
| stale_write_count total | **298** across 19/20 profiles | ❌ FAIL |
| cross_request_write_count total | **298** across 19/20 profiles | ❌ FAIL |
| Files with stale=0 | **1/20** (e2e_0000.json only) | |
| Growth pattern | **Monotonic**: 1→3→4→4→8→10→...→34 | Accumulation across requests |

### Monotonic Stale Write Growth

```
Request  0: stale=0  ← clean (first request)
Request  1: stale=1
Request  2: stale=3
Request  3: stale=4  ← 183 write_after_finalize also in this request
Request  4: stale=4
Request  5: stale=8
Request  6: stale=10
Request  7: stale=11
Request  8: stale=13
Request  9: stale=14
Request 10: stale=16
Request 11: stale=18
Request 12: stale=19
Request 13: stale=20
Request 14: stale=21
Request 15: stale=22
Request 16: stale=23
Request 17: stale=28
Request 18: stale=29
Request 19: stale=34
```

**The monotonic growth proves accumulation**: each request inherits stale writes from previous requests, indicating generation IDs are not properly isolated between requests.

## N9 Gate Assessment

| Criterion | Required | Actual | Pass? |
|-----------|----------|--------|-------|
| write_after_finalize_accepted | = 0 | = 0 | ✅ |
| partial_record | = 0 | **> 0** (298 stale writes) | ❌ |
| cross-request contamination | = 0 | **> 0** (298 cross writes) | ❌ |
| critical_stage_rejected | = 0 | UNKNOWN (need per-stage breakdown) | ⚠️ |

### Affected Stages

The stale/cross writes affect the per-stage timestamps in sync profiles. With 19/20 profiles affected, the following critical stages are potentially contaminated:
- F0 (flow_start), F1 (flow_end)
- V0 (vocoder_start), V1 (vocoder_end)
- Q0 (t2w_submit), Q1 (t2w_dequeue), Q2 (t2w_preprocess_end)

The Flow=9547ms anomaly (R4) and the 100% sync/audio mismatch in C9 both trace back to this same root cause: **per-request generation IDs are not properly isolated under rapid request transitions.**

## Classification

| Classification | Finding |
|---------------|---------|
| PROFILE_FINALIZE_TOO_EARLY | **YES** — finalize happens before async T2W worker completes |
| CROSS_REQUEST_CONTAMINATION | **CONFIRMED** — 298 stale + 298 cross-request writes in 19/20 profiles |
| N6_GUARD_WORKING | **YES** — all 183 write_after_finalize correctly rejected |
| CRITICAL_STAGES_AFFECTED | **LIKELY** — per-stage recording uses same generation guard |

## Root Cause

The generation ID used for per-stage recording is not properly scoped to each request lifecycle under rapid A→B transitions. When request B starts before request A's T2W worker completes:
1. Request B's generation ID is set
2. Request A's T2W worker still holds request A's generation ID
3. Stage writes from request A's worker are compared against request B's generation ID → marked stale
4. Stage writes from request B's main thread may use request A's generation → marked cross

## N9 Gate Decision

**N9 = FAILED** — cross-request contamination confirmed (298 stale + 298 cross-request).

The N6 finalize gate (183 write_after_finalize, accepted=0) is working correctly for the TalkerStepBuffer. But the per-stage recording (sync profile) has a MORE FUNDAMENTAL generation isolation bug that makes all fine-grained latency data from multi-request scenarios UNTRUSTWORTHY.

## Required Fixes (R7)

1. Profile finalization must wait for T2W worker completion before allowing next request
2. Generation IDs must be strictly per-request and never reused
3. Profile handle must be protected from overwrite until T2W worker is done
4. Add lifecycle state machine: ACTIVE → T2W_SUBMITTED → T2W_COMPLETE → FINALIZED
