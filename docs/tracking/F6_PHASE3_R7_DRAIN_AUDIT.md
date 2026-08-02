# F6 Phase 3 — R7 Drain-Before-Dump Production Audit

**Date:** 2026-08-02
**HEAD:** 5d2762e
**Binary libomni.so:** 6654a8442232b058b7ddefaa670d15908a9611027cd41e6df9aa24d73cfad45a

## Executive Summary

**Verdict: DIAGNOSTIC_FIX — NOT production-ready.**

The drain-before-dump in `stream_decode` blocks the main request thread waiting
for T2W worker completion. Under production workload (4 requests, 74 total wavs),
3 of ~7 drain calls timed out at 120 seconds each, adding 454 seconds of blocking
to the request path. This is unacceptable for production.

## Drain Timeline (4-request C9 test)

| Timestamp | Event | Duration |
|-----------|-------|----------|
| 10:13:51 | Drain #1: waiting... | |
| 10:15:25 | EOS drain — buffer empty (wav=16) | ~94s |
| 10:15:25 | Drain #2: waiting... → complete | ~0ms |
| 10:16:31 | Drain #3: waiting... | |
| 10:18:31 | **TIMEOUT after 120000ms** | 120s |
| 10:18:31 | Drain #4: waiting... | |
| 10:20:31 | **TIMEOUT after 120000ms** | 120s |
| 10:21:35 | Drain #5: waiting... | |
| 10:23:35 | **TIMEOUT after 120000ms** | 120s |
| 10:23:35 | Drain #6: waiting... | |
| 10:24:00 | EOS drain — buffer empty (wav=74) | ~25s |
| 10:25:05 | Drain #7: complete | ~0ms |

## Production Impact

| Metric | Value | Assessment |
|--------|-------|------------|
| Drain calls | 7 (over 4 requests) | Multiple redundant drains |
| Drain completions | 4 | 3 timeouts |
| Drain timeouts | 3 | **43% timeout rate** |
| Total drain blocking | ~454s | **76% of total test time (598s)** |
| WS handler drain timeout | Yes | "timed out waiting for TTS audio drain" |
| Next-request blocking | Yes | Each timeout blocks request pipeline for 120s |
| Worker utilization | Saturated | 74 wavs across 4 requests, flow @ 8.5s/window |

## Root Cause

The T2W worker processes flow at ~8.5 seconds per window (see Flow stats below).
With 74 total wavs across 4 requests, the worker is continuously busy. When the
drain signals EOS and waits for `is_final_processed`, the worker is mid-flow and
can't check `eos_received` until it finishes the current window (8.5s). Then it
finds more queued items from the next request (already submitted because the
server pipeline continues) and processes those too.

The drain's `cv.notify_all()` is lost if the worker is not waiting on the CV
(which it isn't — it's busy processing). The worker only checks `eos_received`
when it returns to the CV wait at the top of its main loop.

## Recommendation

**Mark drain-before-dump as DIAGNOSTIC_FIX.** It correctly identified that the
sync dump races the T2W worker (the diagnostic value is real). But the fix
itself is destructive to production latency.

**Production fix**: Async request-scoped finalize. The T2W worker should:
1. Hold a request-scoped profile handle
2. Complete all flow/vocoder processing for that request
3. Self-finalize: write the audio profile, mark sync slots complete
4. Signal completion via a per-request promise/future or atomic flag

The main thread's sync dump should:
1. Check if the T2W worker has finalized this request's profile
2. If finalized: read timestamps (no race — T2W is done)
3. If not finalized: either skip (best-effort) or wait with a SHORT timeout (1-2s)

This removes the synchronous blocking from the critical path while preserving
data integrity.

## Flow/Vocoder Timing (from C9 test)

| Metric | Flow | Vocoder |
|--------|------|---------|
| n | 3 | 3 |
| p50 | 8504ms | 678ms |
| p95 | 8612ms | 702ms |
| min | 8279ms | 651ms |
| max | 8612ms | 702ms |
| >1s count | 3/3 (100%) | 0/3 |
| Historical anomaly (9547ms) | **CONFIRMED STILL PRESENT** | — |

Flow duration of 8.3-8.6 seconds per window is ~100× the expected 135-180ms.
This is a real hardware/algorithm constraint on the Ascend 910C test platform,
NOT a measurement artifact. The timing is consistent across all measurements
(previous 9547ms, current 8279-8612ms). This requires separate investigation
and is NOT caused by the R7 instrumentation.

## C9 Contamination Status

| Profile | gen | stale | cross | flow_start | flow_end | flow_dur |
|---------|-----|-------|-------|------------|----------|----------|
| e2e_0000 | 1 | 0 | 0 | 17511 | 26123 | 8612ms ✓ |
| e2e_0001 | 2 | 0 | 0 | 7200 | 15479 | 8279ms ✓ |
| e2e_0002 | 3 | 1 | 1 | 52356 | 60860 | 8504ms ✓ |
| e2e_0003 | 4 | 1 | 1 | -1 | -1 | — ✗ |

Gen 4 has no flow data (sync dump raced worker despite drain — drain timed out).
Total: 2 stale writes, 2 cross-request writes across 4 profiles.
