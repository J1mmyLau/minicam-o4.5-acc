# Thread Exhaustion — Definitive Root Cause Analysis

Date: 2026-08-06
Investigation: Section 2 (5-stage thread snapshot) + Section 3 (stack trace analysis)

## Executive Summary

**ROOT CAUSE: libgomp (GNU OpenMP) thread pool accumulation per httplib worker thread.**

Each WebSocket session is processed by a different `httplib::ThreadPool` worker thread. When that worker first encounters a `#pragma omp parallel` region inside `llama_decode` → `ggml_graph_compute`, libgomp creates a new thread team of **319 worker threads** (320 total − 1 calling thread). These teams are NOT shared across worker threads and persist for the process lifetime — they are never destroyed.

**319 = `std::thread::hardware_concurrency() / 2 − 1` = `640 / 2 − 1`**

The thread count is determined by `common_cpu_get_num_math()` → `hardware_concurrency() / 2` → `cpuparams.n_threads = 320`. The ggml thread pool (or OpenMP parallel region) creates `n_threads − 1 = 319` worker threads.

## Evidence Chain

### 1. Per-Session Thread Growth (5-stage diagnostic)

| Stage | Baseline Threads | Δ Threads | Audio Chunks | Wall Time | Description |
|-------|-----------------|-----------|-------------|-----------|-------------|
| S0    | 641             | —         | —           | —         | Fresh startup, no sessions |
| S1    | 960             | **+319**  | 3           | 63.2s     | Short TTS ("你好，今天天气不错。") |
| S2    | 1279            | **+319**  | 71          | 934.7s    | Medium TTS ("人工智能的发展历程...") |
| S3    | 1598            | **+319**  | 72          | 921.9s    | Long TTS ("量子计算的基本原理...") |
| S4    | 1917            | **+319**  | 3           | 53.5s     | Short TTS ("你好，今天天气不错。") |
| S5*   | 2236            | **+319**  | —           | —         | Extra short session (strace run) |

**EXITED threads: 0 for all stages.** Threads accumulate monotonically.

**Thread growth is PER-SESSION, not per-chunk.** S1 (3 chunks) and S2 (71 chunks) both produce exactly +319 threads.

### 2. Stack Trace Identification

**Cascade origin (TID 857445):**
```
#0  futex (idle wait)
#1  pthread_cond_wait              ← libc
#2  httplib::ThreadPool::ThreadPool(...)::{lambda()#1}::_M_run()  ← MAIN BINARY (0x47640)
#3  libstdc++ thread internals
#4  libc clone/start_thread
```
This is an **httplib ThreadPool worker thread** created at server startup. It processes the WebSocket upgrade request and triggers `handle_ws_backend()`.

**Leaked threads (e.g., TID 982078–982083):**
```
#0  syscall (futex wait)
#1  0x1e4c0  libgomp.so  ← omp_get_num_procs+0x47c (internal thread pool idle loop)
#2  0x1ba10  libgomp.so  ← omp_fulfill_event+0x6cc (internal thread pool management)
#3  libc start_thread
#4  libc clone
```
These are **libgomp OpenMP worker threads** in the idle/sleep state, waiting for work in libgomp's internal thread pool.

### 3. Thread Creation Cascade (strace analysis)

| Wave | Parent TID | Clones | Surviving | Fate |
|------|-----------|--------|-----------|------|
| 1    | 857445 (httplib worker) | 327 | **319** | PERSISTENT: OpenMP team for worker 857445 |
| 2    | 984385 (child of wave 1) | 319 | 0 | TEMPORARY: nested parallel region, exited |
| 3    | 984388 (child of wave 1) | 319 | 0 | TEMPORARY: nested parallel region, exited |
| 4    | 984386 (child of wave 1) | 218 | 0 | TEMPORARY: nested parallel region, exited |

**Only Wave 1's 319 threads persist.** Waves 2-4 are temporary nested-parallel-region threads that exit after their region completes.

### 4. Thread Count Derivation

```
nproc = 640 (Kunpeng 920, dual-die, 2 threads/core)

common_cpu_get_num_math():
    hardware_concurrency = 640
    return 640 / 2 = 320  (n_threads <= 4 ? n_threads : n_threads / 2)

cpuparams.n_threads = 320  (default, no -t flag specified)

OpenMP parallel region: num_threads(320)
    → 1 calling thread + 319 new worker threads
    → libgomp creates 319 threads, persists in thread pool
```

### 5. Why Threads Accumulate Instead of Being Reused

libgomp maintains thread teams **per calling-thread context** using `pthread` thread-local storage (TLS). Each `#pragma omp parallel` region's team is associated with the thread that enters it.

**httplib::ThreadPool has 639 base worker threads** (created at startup via `CPPHTTPLIB_THREAD_POOL_COUNT = max(8, hardware_concurrency() - 1) = 639`).

Each WebSocket session is dispatched to a **different** worker from the pool (FIFO scheduling). When that worker enters its first OpenMP parallel region, libgomp creates a **new** team of 319 threads for that worker. Since workers are never reused for subsequent sessions (there are 639 workers and only ~10 sessions), each session creates a new team.

**Expected saturation:** After 639 sessions (all workers used once), thread creation should stop (639 × 319 + baseline ≈ 204,000 threads). But the cgroup pids.max=10000 limits total threads to ~10,000, meaning the server crashes after ~30 sessions.

## Crash Mechanism

```
Session 1: +319 threads → pids.current = 641 + 319 = 960
Session 2: +319 threads → pids.current = 960 + 319 = 1279
...
Session N: +319 threads → pids.current → pids.max (10000)
Session N+1: pthread_create fails → server crashes (CGROUP_PID_EXHAUSTION)
```

**~30 sessions to exhaust pids.max=10000** (shared with teammate process).

## Component Attribution

| Component | Thread Creation | Persistent? | Count per Session |
|-----------|----------------|-------------|-------------------|
| **libgomp (OpenMP)** | `#pragma omp parallel num_threads(320)` | **YES — 319 threads** | 319 |
| libgomp nested | `#pragma omp parallel` in nested context | NO — exits after region | 319+319+218 (temporary) |
| httplib ThreadPool | `httplib::ThreadPool(n_threads_http)` | YES — at startup only | 639 (baseline) |
| common_log | `common_log::resume()` | YES — at startup only | 1 (baseline) |
| CANN runtime | `ggml_backend_cann_init()` | YES — at startup only | varies |
| Server main | `main()` | YES — at startup only | 1 |

## Verification

- [x] 5 sessions, each +319 threads, 0 exited
- [x] strace captures 1183 clone() calls, 319 survive
- [x] Cascade origin: httplib::ThreadPool worker TID 857445
- [x] Leaked threads: all in libgomp idle loop (futex wait)
- [x] Thread count matches `cpuparams.n_threads - 1 = 319`
- [x] `GGML_OPENMP:BOOL=ON` in CMake build config
- [x] `libgomp.so.1.0.0` loaded in process maps
- [x] No `OMP_NUM_THREADS` environment variable set
- [x] No `-t` / `--threads` flag on server command line

## Proposed Fix (for Section 5)

**Source code is FROZEN at bdd4550.** Fix options that don't modify source:

### Option A: Environment Variable (non-invasive)
```bash
export OMP_NUM_THREADS=4  # Limit OpenMP threads
export GOMP_SPINCOUNT=0   # Disable spin-waiting
```
**Risk**: May degrade TTS performance. Needs measurement.

### Option B: Server command-line flag
Add `-t 4` to the server startup to limit `cpuparams.n_threads`:
```bash
./build/bin/llama-omni-server ... -t 4
```
**Risk**: May degrade LLM inference throughput. Needs measurement.

### Option C: `GOMP_CPU_AFFINITY` pinning
Pin OpenMP threads to die 0 cores to enable reuse:
```bash
export GOMP_CPU_AFFINITY=0-319
```
**Risk**: May conflict with CANN runtime placement.

### Option D: Pre-warm all thread pool workers (source modification required)
Modify server startup to iterate all httplib workers and execute a dummy parallel region, so all OpenMP teams are created at startup.
**Risk**: Very high initial thread count (639 × 319 ≈ 200k threads). Not feasible with pids.max=10000.

### Option E: Force single worker reuse (source modification required)
Modify WebSocket handler to always use the same worker thread, or implement a thread-pool of 1 for WebSocket requests.
**Risk**: Blocks concurrent sessions.

**Recommended approach**: Option A (`OMP_NUM_THREADS=4`) for immediate mitigation + source-code fix (not in scope of frozen binary) to limit libgomp team creation or destroy teams after use.

## Impact Assessment

| Metric | Value |
|--------|-------|
| Threads leaked per session | 319 |
| Sessions to crash (solo) | ~30 |
| Sessions to crash (with teammate) | ~15 (shared pids.max) |
| Memory per thread | ~140 KB (VmStk=140) |
| Memory leaked per session | ~44.7 MB |
| Memory at crash (~9500 threads) | ~1.33 GB VmStk |
| DRAIN_TIMEOUT correlation | Frequency increases with thread count |

## Next Steps

1. **Section 5**: Implement fix and verify with 25+ sessions + 60min stability
2. **Section 7**: Run official RTF on F16 (requires fix for stability)
3. **Section 8**: Final status output

---
**Author:** CC autonomous investigation
**Evidence:** `thread_snapshots/` (S0-S4 metadata, deltas), `strace_session5.log`, `server_fresh.log`
**Binary:** SHA256 `2bfb2e5028c4f0cf5b8a9e17b22c2cd071505db9e0baa9afc456c00bae84ceb4`
**Source:** FROZEN at bdd4550, branch `fix/tts-thread-lifecycle`
