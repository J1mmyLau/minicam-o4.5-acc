# F6 Thread Exhaustion — Final Status (DRAFT)
Date: 2026-08-06
Status: IN_PROGRESS (Sections 5-7 pending)

## 1. THREAD_LEAK_ROOT_CAUSE

**DEFINITIVE: libgomp (GNU OpenMP) creates per-worker thread teams that persist forever.**

When `llama.cpp` is built with `GGML_OPENMP=ON` (which it is), the `ggml_graph_compute` function uses:

```c
#pragma omp parallel num_threads(n_threads)
```

On this Kunpeng 920 system (640 cores), `common_cpu_get_num_math()` returns `640/2 = 320`. So `n_threads = 320` by default.

When an httplib worker thread first enters this parallel region, libgomp creates a **team of 319 worker threads** (320 − 1 calling thread) associated with that worker via pthread TLS. These teams are:
- Per-worker (NOT shared across workers)
- Persistent (libgomp keeps them for reuse on subsequent parallel regions)
- Never destroyed during process lifetime

When the next WebSocket session is dispatched to a **different** httplib worker (round-robin from pool of 639), that worker creates its own 319-thread team.

**Thread count derivation:**
```
hardware_concurrency() = 640
common_cpu_get_num_math() = 640 / 2 = 320
cpuparams.n_threads = 320 (default, no -t flag)
OpenMP team = n_threads - 1 = 319 new threads per new worker
```

**Evidence:** 5-stage diagnostic (+319/session, 0 exited), strace cascade (319 persistent clones from httplib worker), stack traces (all leaked threads in libgomp idle loop at `omp_get_num_procs+0x47c`).

## 2. THREAD_FIX_COMMIT

**N/A — source code is FROZEN at bdd4550.**

Fix is applied via runtime flag: `-t 4` (or `-t N`).

With `-t 4`: `cpuparams.n_threads = 4`, each new worker creates 3 threads (4−1).
With `-t 1`: `cpuparams.n_threads = 1`, single-threaded, 0 additional threads.

**Reduction: 319→3 per new worker (−99.1%).**

`OMP_NUM_THREADS` environment variable does NOT override explicit `num_threads(N)` in `#pragma omp parallel` clauses, so the `-t` flag is the only non-source modification available.

## 3. THREAD_FIX_EFFECTIVENESS

**Section 5 Verification (IN PROGRESS):**
- Server: `-t 4`, Q4_K_M model
- 7/25 sessions complete
- Pattern: First 3 workers each created +3 threads (total +9). Sessions 4-7 reused existing workers (Δ=0).
- Threads: 653 (stable since S04)
- Thread growth: 9/644 = 1.4% after 7 sessions
- DRAIN_TIMEOUT: 0
- Cgroup pids: 2213/10000 (77.9% headroom)

**Predicted ceiling with -t 4:**
- Worst case: 639 workers × 3 threads = 1917 additional threads
- With baseline ~650: max ~2567 threads
- Well within pids.max=10000 (74.3% headroom)
- Actual reuse pattern suggests ceiling is much lower (~200-500 threads in practice)

## 4. LONG_RUNNING_STABILITY

**PENDING** — Section 5b (60min stability test after 25 sessions).

Previous finding: Server survived 3h before thread exhaustion crash with default `-t` (319 threads/session). With `-t 4`, >1000 sessions would be needed to reach pids.max. 60 minutes = ~30-50 sessions should show near-zero net growth.

## 5. OFFICIAL_RTF

**PENDING** — Section 7 (F16 model RTF measurement).

- F16 model: Confirmed at `/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf` (16GB)
- Official benchmark harness: `benchmark_client.py` at `/workspace/llama.cpp-omni-official-eval/competition/`
- WS adapter: `WebSocketAdapterV2` at `/workspace/llama.cpp-omni-session-fix/submission/adapters/ws_adapter.py`
- Integration wrapper: `/tmp/run_official_rtf.py`
- Measurement: concurrency=1, die 0 only, `-t 4` flag

**Previous measurements (Q4_K_M, WS protocol, no official harness):**
- RTF ~6.45-7.60 (LLM-dominated, default -t 320 threads)
- Official baseline: 1.087 (F16)

**Expected F16 RTF:** F16 model is ~3.5× larger than Q4_K_M. With `-t 4` (reduced OpenMP parallelism), LLM decode will be slower than with default 320 threads. RTF likely > 1.0.

## 6. FIX_BRANCH_RELEASE_CANDIDATE

**TBD** — depends on Sections 5-7 completion.

Binary: SHA256 `2bfb2e5028c4f0cf5b8a9e17b22c2cd071505db9e0baa9afc456c00bae84ceb4`
Source: FROZEN at bdd4550
Branch: `fix/tts-thread-lifecycle` (created for this work)

## 7. OFFICIAL_COMPETITION_READY

**TBD** — requires all 8 sections complete.

Remaining:
- [ ] Section 5: 25-session verification (IN PROGRESS: 7/25)
- [ ] Section 5b: 60min stability test
- [ ] Section 6: WS adapter integration test
- [ ] Section 7: Official RTF on F16
- [ ] Section 8: Final status output (THIS FILE)

## Artifacts

| Artifact | Path |
|----------|------|
| Root cause analysis | `demo_runs/.../ROOT_CAUSE_DEFINITIVE.md` |
| 5-stage snapshots | `demo_runs/.../thread_snapshots/` |
| Strace cascade | `/tmp/strace_session5.log` |
| Verification data | `demo_runs/.../verification_t4/` |
| WS adapter | `submission/adapters/ws_adapter.py` |
| RTF wrapper | `/tmp/run_official_rtf.py` |
| Runbook | `demo_runs/.../RUNBOOK_SECTIONS_5_8.md` |
