# Thread Exhaustion Root Cause Analysis
**Date:** 2026-08-06
**Binary:** 2bfb2e5028c4f0cf5b8a9e17b22c2cd071505db9e0baa9afc456c00bae84ceb4
**Server PID:** 377377

## Executive Summary

**THREAD_COUNT_MONOTONIC_GROWTH: CONFIRMED**
**CRASH_MECHANISM: CGROUP_PID_EXHAUSTION**
**PER-SESSION LEAK: 300-800 threads**

Each TTS session leaks threads that are never reclaimed. The cgroup pids.max=10000 limit is hit after ~12-25 sessions, triggering "libgomp: Thread creation failed: Resource temporarily unavailable" and server crash.

## Evidence

### Thread Count Time Series

| Timestamp | Threads | Δ | Cgroup PIDs | Note |
|-----------|---------|---|-------------|------|
| 02:14:33Z | 1,598 | — | 2,528 | Baseline (~7h after restart, few sessions) |
| 02:16:40Z | 1,917 | +319 | 2,842 | After 1 short session (说：你好。4 audio chunks) |
| 02:22:12Z | 3,524 | +1,607 | 4,453 | After 2 more sessions (天气+量子计算) |

### Per-Session Leak Rate
- Short session (4 audio chunks): ~319 threads leaked
- Medium sessions (~14-25 audio chunks): ~800 threads leaked each
- Leak rate correlates with TTS audio volume (more chunks = more threads leaked)

### System Limits
- `ulimit -u`: unlimited (soft and hard)
- `/proc/sys/kernel/threads-max`: 16,493,433
- `/proc/sys/kernel/pid_max`: 4,194,304
- **cgroup `pids.max`: 10,000** ← THIS IS THE BINDING CONSTRAINT
- **cgroup `pids.current`: 4,453** (after 3 sessions from baseline)

### Thread Characteristics
- ALL 3,524 threads named "llama-omni-serv" (no distinct naming patterns)
- No OMP_NUM_THREADS set in environment
- Consistent with OpenMP thread pool creation for TTS processing
- Threads are NOT joined/reaped after session completion

### Crash Prediction
- Threads remaining before cgroup limit: 10,000 - 4,453 = 5,547
- At ~800 threads/session: ~7 more medium sessions
- At ~300 threads/session: ~18 more short sessions
- Historical crash at 19:12 (after ~24 sessions: T3×10 + T6×5 + T7×3 + T8×6) matches this model

### DRAIN_TIMEOUT Correlation
- Pre-crash log: 35 DRAIN_TIMEOUT entries (across all test sessions)
- Post-restart log: 4 DRAIN_TIMEOUT entries (RTF tests only)
- All DRAIN_TIMEOUT entries show `final_dequeued == final_completed` — drain completes correctly, just slower than the timeout interval
- Hypothesis: Thread contention from leaked threads slows T2W drain, triggering timeout messages

## Root Cause Classification

| Attribute | Finding |
|-----------|---------|
| THREAD_COUNT_MONOTONIC_GROWTH | YES — confirmed via 3 time series measurements |
| HOST_PID_EXHAUSTION | NO — ulimit unlimited, threads-max=16M |
| CGROUP_PID_EXHAUSTION | YES — pids.max=10000, current=4453, ~7 sessions to crash |
| CGROUP_PID_EXHAUSTION | YES — binding constraint |
| THREAD_LEAK_LOCATION | TTS pipeline (OpenMP threads for Flow+Vocoder processing) |
| LEAK_MECHANISM | Threads created but not joined/reaped after session completion |

## Verdict

**LONG_RUNNING_STABILITY=FAIL**
**THREAD_EXHAUSTION=CONFIRMED**
**ROOT_CAUSE=TTS_PIPELINE_THREAD_LEAK**
**CRASH_TRIGGER=CGROUP_PID_EXHAUSTION**

## Mitigation
- Short-term: Server restart every ~10 sessions (before cgroup limit)
- Long-term: Fix thread lifecycle in TTS pipeline (join/reap threads after session completion)
- Alternative: Increase cgroup pids.max (temporary relief, doesn't fix the leak)
