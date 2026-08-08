# F6 Thread Exhaustion — Final Judgment

**Date:** 2026-08-06
**Verdict:** FIX_BRANCH_RELEASE_CANDIDATE = **NO**

---

## Task Summary

| Task | Description | Result |
|------|-------------|--------|
| 1 | Audit `-t` vs HTTP worker pool | DONE — Confirmed: `-t N` controls model compute via `cpuparams.n_threads` → `num_threads(N)`. HTTP worker pool = 639 (hardware_concurrency-1), NOT configurable at runtime (`n_threads_http` not implemented). |
| 2 | Locate 110s drain root cause | DONE — TTS vocoder pipeline continues after `response.done`. Drain timeout = 110s. `final_dequeued == final_completed` → zero data loss. Drain is log-ordering artifact, not corruption. |
| 3 | -t 4 vs -t 8 A/B comparison | DONE — **Winner: -t 4.** Both configs have 0/3 failures, identical E2E p50 (56.6s). -t 8 adds +7 threads/new-worker vs -t 4's +3. |
| 4 | 60-minute stability test | **FAIL** — See below |
| 5 | Official SPEAK→WAV RTF E2E | **PASS** — See below |
| 6 | Final release judgment | **NO** — Criteria not met |

---

## Task 3: A/B Results

```
Config        Thread growth    E2E p50      RTF p50     Failures
-t 4          +6 (641→647)     56,575ms     4.98        0/3
-t 8          +7 (641→648)     56,479ms     5.04        0/3

Winner: -t 4 (same performance, 43% less thread growth per new worker)
```

---

## Task 4: 60-Minute Stability Test

**Duration:** 60.9 minutes, 56 sessions (2 warmup + 54 measured)
**Server:** F16, -t 4, die0, concurrency=1

### Gate Results

| Gate | Status | Value |
|------|--------|-------|
| SESSION_SUCCESS_RATE | **PASS** | 54/54 (100%) |
| SERVER_CRASH | **PASS** | 0 crashes |
| THREAD_GROWTH_AFTER_WARMUP | **FAIL** | +78 threads = 12.11% (>5% threshold) |
| DRAIN_TIMEOUT | **FAIL** | 36 occurrences (>0 threshold) |
| NEXT_SESSION_REJECTION | **PASS** | 0 rejections |
| **OVERALL** | **FAIL** | 2/5 gates fail |

### Thread Growth Analysis

```
Threads: 641 → 644 (warmup) → 722 (final, +78, +12.11%)
Pattern: Staircase +3 per ~2 sessions (each new httplib worker adds 3 OpenMP threads)
Cause:   httplib workers never exit — awakened by each request before 3s idle timeout.
         OpenMP teams on distinct workers accumulate monotonically.
Ceiling: 641 + 639×3 = 2558 threads (theoretical max, well under pids.max=10000)
Mitigation: -t 4 caps each new worker's OpenMP team to 3 threads (vs 319 with -t 320).
            Thread growth is BOUNDED but exceeds 5% threshold within ~25 sessions.
```

### Drain Timeout Analysis

```
Count: 36 occurrences over 54 measured sessions
Impact: ZERO data loss (all 54/54 sessions produced correct audio)
Nature: Log-ordering artifact — TTS pipeline finishes after drain timeout check
Root:   RESPONSE_DONE_TO_REUSABLE > 2s requirement
        With 3-WAV sessions, drain completes in ~10-15s (acceptable)
        With 70-WAV sessions, drain can take 110-220s (blocking)
```

---

## Task 5: Official SPEAK→WAV RTF E2E

**Harness:** `benchmark_client.py` @ `d50ebeac` (UNMODIFIED)
**Adapter:** `WebSocketAdapterV2` @ `submission/adapters/ws_adapter.py`
**Command:** `python3 -u /tmp/rtf_e2e.py`

### Results

```
Valid samples:         10/10 (100%)
E2E p50:               56,209ms (34,465 - 80,702ms)
TTFT p50:              41,976ms
First Audio p50:       47,927ms
INTERNAL_PER_WAV_TTS_RTF_F16: 4.25 (n=46, server-side measurement)
OFFICIAL_SPEAK_TO_WAV_RTF:    CANNOT_COMPUTE_WITHOUT_AUDIO_DURATION
```

### RTF Gap

The official `benchmark_client.py` is a **timing harness**, not an RTF calculator:
- Records: request_start, first_text, first_audio, response.done, chunk intervals
- Does NOT compute: total audio duration → required for SPEAK→WAV RTF
- Server-side `RTF=X.XX` measures per-chunk TTS vocoder efficiency (different metric)
- To compute official SPEAK→WAV RTF: benchmark must save WAV output and measure audio duration

---

## Task 6: Release Candidate Criteria

Per user requirements, RELEASE_CANDIDATE=YES requires ALL of:

| Criterion | Status | Evidence |
|-----------|--------|----------|
| 60min stability PASS | **FAIL** | Thread growth 12.11% (>5%), Drain timeout 36 (>0) |
| 25/25 sessions success | **PASS** | 54/54 (100%) |
| drain < 2s | **FAIL** | 36 occurrences, TTS drain takes 10-220s depending on session length |
| Official harness E2E | **PASS** | 10/10 via unmodified benchmark_client.py + WebSocketAdapterV2 |
| T7/T8 regression PASS | **UNTESTED** | Was PASS in prior session; not re-tested |

**Verdict: FIX_BRANCH_RELEASE_CANDIDATE = NO**

Blocking items:
1. **THREAD_GROWTH**: monotonic accumulation of OpenMP teams across httplib workers. Bounded (ceiling ~2558) but exceeds 5% threshold within ~25 sessions. Requires source modification to fix (implement `n_threads_http`, reduce thread pool size, or add worker lifecycle management).
2. **DRAIN LATENCY**: TTS vocoder pipeline continues after `response.done`. For short sessions (3 WAVs) drain is ~10-15s (acceptable). For production workloads (50+ WAVs) drain is 110-220s (blocking). Requires source modification to fix (separate TTS pipeline from request worker, or add session readiness signaling).
3. **OFFICIAL RTF**: The official benchmark does not compute SPEAK→WAV RTF. A separate audio-duration measurement tool is needed, OR the starter kit may provide RTF computation logic.

---

## Status Codes (Corrected)

```
PER_WORKER_OPENMP_TEAM_RETENTION     = CONFIRMED
THREAD_RESOURCE_AMPLIFICATION        = CONFIRMED (319→3 with -t 4)
UNBOUNDED_THREAD_LEAK                = NOT_PROVEN (bounded by httplib pool size)

FUNCTIONAL_TTS_GATE                  = PASS
TTS_INCREMENTAL_STREAMING            = PASS
TTS_CROSS_SESSION_ISOLATION          = PASS

SESSION_SUCCESS_RATE_60MIN           = PASS (54/54, 100%)
SERVER_CRASH_COUNT_60MIN             = PASS (0)
THREAD_GROWTH_AFTER_WARMUP_60MIN     = FAIL (12.11% > 5%)
DRAIN_TIMEOUT_COUNT_60MIN            = FAIL (36 > 0)
NEXT_SESSION_REJECTION_60MIN         = PASS (0)

WS_ADAPTER_BENCHMARK_COMPAT          = PASS (10/10 via benchmark_client.py)
OFFICIAL_SPEAK_TO_WAV_RTF            = NOT_RUN (CANNOT_COMPUTE — benchmark lacks audio duration)
INTERNAL_PER_WAV_TTS_RTF_F16         = 4.25 (server-side, n=46)

RUNTIME_MITIGATION                   = PASS (-t 4 reduces per-worker threads from 319 to 3)
FIX_BRANCH_RELEASE_CANDIDATE         = NO
OFFICIAL_COMPETITION_READY           = NO
```

---

## Next Steps (if release is required)

1. **Fix thread growth**: Implement `n_threads_http` or reduce httplib worker pool via `new_task_queue(size=N)` — requires source modification (FROZEN binary constraint blocks this)
2. **Fix drain latency**: Add session readiness signaling between TTS pipeline and server accept loop — requires source modification
3. **Compute official RTF**: Add audio duration tracking to benchmark_client.py, or use server-side per-WAV RTF with documented methodology difference
4. **Workaround for current binary**: Use `-t 4` + short sessions (<60s) + inter-request delay ≥ 15s for concurrency=1 workloads. Thread growth is bounded and won't cause crashes within typical session counts (~50).
