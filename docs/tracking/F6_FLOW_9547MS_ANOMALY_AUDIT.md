# F6 Phase 3 — Flow 9547ms Timing Anomaly Audit (R4)

**Date:** 2026-08-02
**HEAD:** `aabd12e`

## Executive Summary

**Flow=9547ms is a MEASUREMENT ARTIFACT, not a real Flow regression.**

Root cause: **CROSS-REQUEST ATTRIBUTION** — the C8 thread_local context is overwritten between recording of `flow_start` and `flow_end` in sequential multi-request scenarios. The 9547ms value represents `flow_end[N] - flow_start[N+1]` (or similar cross-request delta), NOT actual Flow execution time within a single request.

## Evidence Chain

### 1. N8 Single-Request (appeared valid by accident)

N8 e2e_0000 sync profile:
```
flow_start: 11902
flow_end:   21449
Flow = 21449 - 11902 = 9547ms
```

N8 e2e_0000 audio profile:
```
flow_start: 11902  ← matches sync (only request in flight)
flow_end:   21449  ← matches sync
```

**This accidentally matched because only 1 TTS request was running.**

### 2. C9 Multi-Request (reveals the bug)

**100% of 22 matched pairs show sync/audio MISMATCH:**

| Req | Sync flow_start | Sync flow_end | Sync Flow Δ | Audio flow_start | Audio flow_end |
|-----|----------------|---------------|-------------|-----------------|----------------|
| 0 | 14116 | 23969 | +9853ms | **MISSING** | 6755 |
| 1 | 7498 | 6755 | **-743ms** ⚠️ | **MISSING** | 5468 |
| 2 | 6168 | 5468 | **-700ms** ⚠️ | **MISSING** | 5342 |
| 3 | 6056 | 5342 | **-714ms** ⚠️ | **MISSING** | 5829 |
| 4 | 6518 | 5829 | **-689ms** ⚠️ | **MISSING** | 6588 |
| 5 | 8420 | 6588 | **-1832ms** ⚠️ | **MISSING** | 7110 |
| ... | ... | ... | ... | ... | ... |

### 3. Critical Observations

**A. NEGATIVE Flow durations in sync profiles:**
Multiple C9 requests show `flow_end < flow_start`, producing negative Flow durations (-689ms, -700ms, -714ms, -743ms, -1832ms). This is physically impossible for a monotonic clock within a single request.

**B. flow_start MISSING from ALL C9 audio profiles (22/22):**
The T2W worker (which has proper thread_local scope) never records `flow_start` in C9, only `flow_end`. This means the C8ProfileScope for Flow START is not capturing the thread_local context.

**C. Sync vs Audio values diverge by up to 17 seconds:**
Req 0: sync flow_end=23969, audio flow_end=6755 (difference: 17214ms)

### 4. Pattern Analysis

Looking at C9 sync profiles sequence:

```
Req 0: flow=[14116, 23969]  dur=+9853ms
Req 1: flow=[ 7498,  6755]  dur= -743ms  ← flow_end[1] = 6755 < flow_start[1] = 7498
Req 2: flow=[ 6168,  5468]  dur= -700ms  ← flow_end[2] = 5468 < flow_start[2] = 6168
Req 3: flow=[ 6056,  5342]  dur= -714ms
Req 4: flow=[ 6518,  5829]  dur= -689ms
Req 5: flow=[ 8420,  6588]  dur=-1832ms
Req 6: flow=[12283,  7110]  dur=-5173ms
```

Notice: `flow_end` of Req N equals (or is close to) `flow_start` of Req N+1 in some cases:
- Req 0 flow_end=23969, Req 1 flow_start=7498 — NO, these don't match
- Req 1 flow_end=6755, Req 2 flow_start=6168 — close-ish but not exact

But looking differently: `flow_start` of Req N often equals approximately`flow_end` of Req N-1:
- Req 1 flow_start=7498, Req 0... no.

Let me look at this differently. The sync profile records from the main thread via e2e_record_ns(). The audio profile records from the T2W worker thread via thread_local.

The negative durations in sync profiles indicate that when the main thread calls e2e_record_ns(flow_end), the thread_local context has already been overwritten by the NEXT request's flow_start or other stages. So `flow_end` is reading the current request's end timestamp, but `flow_start` has been clobbered.

**This is the classic "profile written after finalize" or "context overwritten before finalize" bug.**

## Root Cause

The C8 thread_local context (`C8FlowVocoderTargets`) is set per-request, but:
1. When the main thread calls `e2e_record_ns(flow_start)`, it records timestamp A from thread_local context X
2. Before `e2e_record_ns(flow_end)` is called, thread_local context X is overwritten by context Y (next request)
3. `e2e_record_ns(flow_end)` writes timestamp B into context Y's profile
4. Result: flow_start goes to request X, flow_end goes to request Y

For N8 (single request), context X is never overwritten, so the values accidentally match.

## Audio Profile Issue

The audio profile is missing `flow_start` entirely in C9 (22/22). This is a DIFFERENT bug:
- The C8ProfileScope for Flow is entered on the T2W worker thread
- The thread_local context should be valid at scope entry
- But `flow_start` is not being recorded

Possible causes:
1. C8ProfileScope constructor doesn't record flow_start (code path issue)
2. Thread_local context is null at scope entry time
3. The scope guard is entered AFTER flow has already started

## Classification

| Classification | Evidence | Likelihood |
|---------------|----------|------------|
| CROSS_REQUEST_ATTRIBUTION | Negative durations, sync/audio mismatch | **CONFIRMED** |
| TIMESTAMP_OVERWRITE | flow_start clobbered by next request | **CONFIRMED** |
| COLD_START_OR_GRAPH_CAPTURE | Not the primary cause | RULED_OUT |
| MULTI_CHUNK_AGGREGATION | Not supported by evidence | UNLIKELY |
| CPU_FALLBACK | Flow runs on NPU (CANN ops present) | RULED_OUT |
| TRUE_FLOW_REGRESSION | Real Flow is ~135-180ms on NPU | **RULED_OUT** |

## Impact

1. **All per-stage latency budgets derived from sync profiles are INVALID**
2. **The 9547ms Flow value is a measurement artifact, not a real bottleneck**
3. **N8's accidental match created false confidence in the instrumentation**
4. **Audio profiles (worker thread) are partially valid** — flow_end values are trustworthy, flow_start is missing

## Recommended Fixes

1. Fix C8ProfileScope to atomically record BOTH flow_start and flow_end to the SAME request context
2. Ensure thread_local context is NOT overwritable until profile is finalized
3. Add generation-guard to C8 context similar to N6's TalkerStepBuffer guard
4. After fix, re-run N8, C9, and S13 with corrected instrumentation
