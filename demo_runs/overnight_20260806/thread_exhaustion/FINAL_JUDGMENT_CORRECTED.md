# F6 Final Status — 2026-08-06 (CORRECTED v2)

---

## 1. Candidate Identity

```
SOURCE_BASE_SHA           = bdd4550  (fix(f6-phase3): freeze candidate)
SOURCE_HEAD_SHA           = b0400d8  (fix/tts-thread-lifecycle)
SESSION_FIX_COMMITS        = 4 commits on top of bdd4550:
  0021584 fix(ws_handler): unified session finalizer for WebSocket /backend path
  17d9542 fix(ws_handler): remove use_tts guard from ws_finalize_context_reusable
  7fbf19a fix(ws_handler): KV cache isolation + T2W drain fast-path for text-only
  b0400d8 fix(server): expose session cleanup helpers for HTTP close endpoint
UNCOMMITTED_SOURCE_CHANGES = demo_runs/ (untracked), docs/fix/ (untracked), submission/ (untracked)
SERVER_BINARY_SHA256       = 2bfb2e5028c4f0cf5b8a9e17b22c2cd071505db9e0baa9afc456c00bae84ceb4
SERVER_BINARY_BUILT        = 2026-08-05 16:04
RUNTIME_ARGS               = -m .../MiniCPM-o-4_5-Q4_K_M.gguf --host 0.0.0.0 --port 8080 -ngl 99 --ctx-size 2048 --batch-size 512 --ubatch-size 512 -t 4
THREADS_ARG                = -t 4
ADAPTER_PATH               = submission/adapters/ws_adapter.py
ADAPTER_COMMIT             = part of uncommitted submission/ directory
DEMO_COMMIT                = b0400d8 (HEAD of fix/tts-thread-lifecycle)

NOTE: Binary built from HEAD (b0400d8), NOT from frozen bdd4550.
      The 4 session-fix commits modify ws_handler.cpp and server-omni.cpp.
      Plateau test server (PID 1451083, -t 4) was killed after 60 min test.
      Running server (PID 1017666, -t 2) is from an earlier session.
```

---

## 2. Thread State (Corrected)

### Mechanism (Confirmed)

```
639 httplib workers
→ worker首次进入OpenMP区域
→ libgomp为该worker保留独立team (pthread TLS)
→ 默认-t 320: 每个worker额外驻留319线程
→ -t 4后: 每个worker额外驻留3线程
→ worker pool有限 → 线程增长有界
```

### Plateau Observation (60 min, NO restart)

```
HTTP_WORKER_COUNT           = 639
WORKERS_WITH_OMP_TEAM       = 24  (estimated from 72线程 / 3 per worker)
WORKER_SATURATION           = 3.8%
THREAD_COUNT_PLATEAU        = NO

FIRST_30MIN_THREAD_SLOPE    = 0.60 threads/min
LAST_30MIN_THREAD_SLOPE     = 1.63 threads/min
GROWTH_PATTERN              = ACCELERATING (2.73× speedup in second half)

PER_WORKER_OMP_TEAM_RETENTION = CONFIRMED
THEORETICAL_SERVER_THREAD_CEILING = 2558
  Prerequisites for ceiling:
  - worker count truly fixed at 639
  - no other request-driven thread sources
  - each worker always retains exactly 3 OpenMP child threads
```

**Correction**: Earlier report claimed "true plateau at ~50% worker saturation." This is WRONG. Per the model, plateau requires NEAR-100% worker saturation (all workers with OpenMP teams). Current 3.8% is far from this bound.

### Cgroup PID Safety

```
PIDS_CURRENT                = 1646
PIDS_MAX                    = 10000
LLAMA_OMNI_SERVER_THREADS   = 739  (PID 1017666, -t 2)

SERVER_OPENMP_BOUND_LT_PIDS_MAX = YES  (2558 < 10000)
SHARED_CGROUP_PID_SAFETY        = NOT_PROVEN

NOTE: 2558 < 10000 only proves this single thread mechanism does not
      approach pids.max alone. Shared cgroup with teammate processes —
      must account for teammate peak + container overhead + safety margin
      before claiming impossibility of PID exhaustion.

Cgroup process breakdown:
  llama-omni-server:     739 threads (PID 1017666, -t 2)
  claude/ai-agent/IDE:  ~400 threads
  node processes:        ~250 threads
  codex/other:           ~150 threads
  Other system:          ~107 threads
  ─────────────────────────────────
  TOTAL:                 1646 / 10000 (16.5%)

Projected at server peak (2558 threads, -t 4):
  1646 - 739 + 2558 = 3465 / 10000 (34.6%)
  
  With teammate model server (estimated 3000 threads):
  3465 + 3000 = 6465 / 10000 (64.7%)
  
  Headroom at projected peak: ~3535 PIDs

TOTAL_PROJECTED_CGROUP_PIDS (with teammate) = ~6465
PID_HEADROOM_AT_PROJECTED_PEAK              = ~3535
```

---

## 3. DRAIN_TIMEOUT (Corrected)

### Forensic Classification (36 occurrences)

```
A. REAL_PENDING_WORK:            0
B. STATE_NOTIFICATION_DELAY:    10  (first-classify race)
C. STALE_GENERATION:             0
D. LOG_FALSE_POSITIVE:          26  (post-worker-stop check)
E. UNKNOWN:                      0

DATA_LOSS:                       0  (final_dequeued == final_completed)
SESSION_REJECTION:               0
ERRORS_IN_DRAINED_SESSIONS:      0
```

### Root Cause

```
Classifier at omni.cpp:6305 checks transient is_final_processed flag
→ flag reset by drain itself (omni.cpp:6172)
→ only re-set by T2W worker thread (omni.cpp:11365, 11746)
→ post-worker-stop: flag always false → spurious DRAIN_TIMEOUT

Drain predicate (omni.cpp:6222) uses durable final_processed_generation
→ drain completes correctly via this path
→ classifier falsely reports timeout based on transient flag
```

### Corrected Status

```
DRAIN_FUNCTIONAL_GATE            = PASS
DRAIN_LOG_CLEANLINESS            = FAIL  (36 occurrences still in log)
DRAIN_TIMEOUT_RELEASE_IMPACT     = NO_OBSERVED
DRAIN_TIMEOUT_DATA_LOSS          = 0
DRAIN_TIMEOUT_SESSION_REJECTION  = 0
DRAIN_TIMEOUT_ROOT_CAUSE         = OBSERVABILITY_RACE + POST_STOP_CHECK
```

**Correction**: Earlier report wrote "DRAIN_CLEANLINESS=PASS." This is inaccurate — 36 DRAIN_TIMEOUT lines still appear in the log. Functional impact is zero, but the log is not clean. Correctly: DRAIN_FUNCTIONAL_GATE=PASS, DRAIN_LOG_CLEANLINESS=FAIL.

---

## 4. RTF (Corrected)

### Official Spec Status

```
METRIC_CONTRACT.md:          ALL PROVISIONAL — pending starter kit
benchmark_client.py:         Timing harness only — no RTF computation
parse_results.py:            Aggregates TTFT/first_audio/E2E — no RTF
OFFICIAL_SPEAK_TO_WAV_RTF:   NOT_PROVEN  (no official definition exists)
OFFICIAL_BASELINE_COMPLIANCE: NOT_PROVEN  (cannot compare without official metric)
```

The official eval repo defines NO SPEAK→WAV RTF metric. The known baseline 1.087 comes from a different measurement context. No p90<1 gate is documented anywhere in the official specification.

### Our Measurement (Correctly Named)

```
WS_SESSION_E2E_RTF_F16_P50   = 6.65
WS_SESSION_E2E_RTF_F16_P90   = 11.41
WS_SESSION_E2E_RTF_F16_P95   = 11.60

Definition:
  RTF = (response.done_ts - session.created_ts) / (total_pcm_bytes / 48000)

What this includes:
  session.init round-trip
  + input.append send
  + LLM prefill (15s measured)
  + LLM text generation (5-10s measured)
  + Talker (text→speech tokens, server-side)
  + TTS/T2W (speech tokens→WAV, server per-WAV RTF=4.28)
  + WS transport overhead
  + session finalizer

What this does NOT measure:
  - Official SPEAK→WAV timing boundary
  - Per-chunk audio generation latency
  - Talker stage in isolation
```

**Correction**: Earlier reports called this "OFFICIAL_SPEAK_TO_WAV_RTF=6.65" and "OFFICIAL_RTF_GATE (p90<1)=FAIL." Both are incorrect — there is no official metric to compare against, and p90<1 is not a documented gate. Correct naming: WS_SESSION_E2E_RTF.

### RTF Bimodality

Two distinct clusters in the 30 sessions:

| Cluster | n | Wall | Audio | RTF | TTFT |
|---------|---|------|-------|-----|------|
| Fast | 17 | ~34s | ~5.2s | 3.6-6.7 | ~20s |
| Slow | 13 | ~56s | ~5.5s | 8.3-11.8 | ~42s |

The fast/slow split correlates with TTFT (20s vs 42s), suggesting server state or queuing effects rather than varying workload.

---

## 5. Phased Performance Analysis

### Methodology

Extracted from WS adapter debug files (30 sessions). Server-side metrics attached to WS events provide `prefill_ms`, `generate_ms`, `wall_clock_ms`, `kv_cache_length`.

### Representative Sessions

#### Fast (p50, wall=34.1s, audio=5.1s, RTF=6.65)
```
Phase                    Duration    % of E2E
─────────────────────────────────────────────
TTFT (first text):       20,524ms    60.2%
LLM text generation:     21,685ms    63.6%
First audio latency:     25,683ms    75.3%
Audio generation (3 WAV): 8,345ms    24.5%
Session finalizer tail:     44ms      0.1%
─────────────────────────────────────────────
TOTAL (session.created→done): 34,128ms

Server-side:
  prefill_ms:  15,178ms
  generate_ms:  5,238→8,195→10,154ms (accumulating)
  per-WAV TTS: RTF≈4.3 (server-side)
```

#### Median (wall=55.9s, audio=5.8s, RTF=9.57)
```
Phase                    Duration    % of E2E
─────────────────────────────────────────────
TTFT (first text):       42,112ms    75.3%
LLM text generation:     44,182ms    79.0%
First audio latency:     47,616ms    85.2%
Audio generation (3 WAV): 8,258ms    14.8%
Session finalizer tail:      0ms      0.0%
─────────────────────────────────────────────
TOTAL (session.created→done): 55,874ms
```

#### Slow (wall=80.6s, audio=17.1s, RTF=4.71)
```
Phase                    Duration    % of E2E
─────────────────────────────────────────────
TTFT (first text):       42,052ms    52.2%
LLM text generation:     50,894ms    63.1%
First audio latency:     48,462ms    60.1%
Audio generation (9 WAV): 32,177ms   39.9%
Session finalizer tail:      0ms      0.0%
─────────────────────────────────────────────
TOTAL (session.created→done): 80,639ms
```

### Bottleneck Attribution

```
MAIN_LLM_PHASE           = DOMINANT  (60-85% of E2E wall time)
  Prefill:  ~15s (constant, model + prompt overhead)
  Generate: ~5-10s (varies with output length)

TTS_AUDIO_PHASE          = SECONDARY  (15-40% of E2E wall time)
  Server per-WAV TTS RTF: 4.28 (server-side measurement)
  Audio gen time scales linearly with audio duration

CAUSE_ATTRIBUTION         = UNPROVEN
  Without profiler or CPU/NPU flame graph evidence, cannot attribute to:
  - Kunpeng 920 hardware
  - CANN/NPU throughput
  - -t 4 CPU pre-processing
  - LLM output length / prompt template
  - Talker stage overhead
  - WS adapter buffering / transport
  - Session finalizer
  - Request template and max output length
```

**Correction**: Earlier report attributed RTF>1 to "Kunpeng 920 hardware limitation." This is unsupported without per-phase profiler evidence. The dominant bottleneck is LLM prefill+generation (~60-85% of E2E), not TTS/NPU.

---

## 6. Official Timing Boundary Mapping

### Field Mapping (PROVISIONAL — pending starter kit)

```
OFFICIAL_STATE          OFFICIAL_HTTP_EVENT    ADAPTER_WS_EVENT         TIMESTAMP_SOURCE
──────────────────────  ────────────────────   ──────────────────────   ────────────────
request_start           POST /v1/stream/decode  session.init send       client time_ns()
first_text_token        SSE data: content       response.output.delta   client recv ts
                                                (kind=text)
first_audio_chunk       SSE data: is_listen     response.output.delta   client recv ts
                                                (kind=audio)
request_end             SSE: [DONE]             response.done           client recv ts
SPEAK generation start  NOT_DEFINED             NOT_CAPTURED            NOT_AVAILABLE
WAV chunk start         NOT_DEFINED             NOT_CAPTURED            NOT_AVAILABLE
WAV chunk end           NOT_DEFINED             NOT_CAPTURED            NOT_AVAILABLE

AUDIO_DURATION_SOURCE   = pcm_bytes / (24000 * 1 * 2)  (from base64 in WS events)
                          NOT validated against official spec
```

### Official Spec Gaps (METRIC_CONTRACT.md)

```
All items marked "待官方确认":
  - Interface protocol (WebSocket / HTTP / gRPC)
  - Input/output JSON schema
  - Timing start/end events
  - Chunk definition
  - Concurrency definition
  - Correctness rules
  - Timeout settings
  - Submission package format
```

### Known Official Baseline

```
SPEAK→WAV primary RTF = 1.087  (source: prior documentation, context unknown)
  Measurement methodology: NOT_DOCUMENTED
  Hardware context:        NOT_DOCUMENTED
  Model configuration:     NOT_DOCUMENTED
  Comparability:           CANNOT_ASSESS
```

**Correction**: Earlier report invented "OFFICIAL_RTF_GATE = p90 < 1". This rule is NOT supported by any official documentation. The only known reference is 1.087 as a point value with unknown methodology.

---

## 7. Functional Gates (Confirmed)

```
T3 (A/B -t 4 vs -t 8)            = PASS  (-t 4 wins: same perf, 43% less thread growth)
T6 (Exception injection)          = PASS  (5/5 patterns recovered)
T7 (Streaming TTS)                = PASS  (previously verified)
T8 (Cross-session isolation)      = PASS  (previously verified)

TTS_INCREMENTAL_STREAMING         = PASS
CROSS_SESSION_ISOLATION           = PASS

STABILITY_SESSION_SUCCESS         = 109/109  (56 + 55 across two 60-min runs)
SERVER_CRASH_COUNT                = 0
NEXT_SESSION_REJECTION_COUNT      = 0

OPENMP_TEAM_RETENTION_ROOT_CAUSE  = CONFIRMED
RUNTIME_MITIGATION                = -t 4
```

---

## 8. Final Status

```
FUNCTIONAL_STABILITY_EVIDENCE       = PASS  (109/109, 跨两轮测试)
THREAD_EXHAUSTION_MITIGATION        = PASS_WITH_-t_4
THREAD_COUNT_PLATEAU                = NO  (accelerating growth, 3.8% saturation)
BOUNDED_OPENMP_RETENTION_MODEL      = SUPPORTED  (ceiling 2558, prerequisites apply)
SERVER_OPENMP_BOUND_LT_PIDS_MAX     = YES
SHARED_CGROUP_PID_SAFETY            = NOT_PROVEN

DRAIN_FUNCTIONAL_GATE               = PASS  (0 data loss, 0 rejection)
DRAIN_LOG_CLEANLINESS               = FAIL  (36 DRAIN_TIMEOUT in log)
DRAIN_TIMEOUT_ROOT_CAUSE            = OBSERVABILITY_RACE + POST_STOP_CHECK
DRAIN_TIMEOUT_RELEASE_IMPACT        = NO_OBSERVED

WS_SESSION_E2E_RTF_F16_P50          = 6.65
WS_SESSION_E2E_RTF_F16_P90          = 11.41
OFFICIAL_SPEAK_TO_WAV_RTF           = NOT_PROVEN
OFFICIAL_BASELINE_COMPLIANCE        = NOT_PROVEN
OFFICIAL_RTF_GATE_p90_lt_1          = DELETED  (not supported by any official spec)

LLM_PHASE_DOMINANCE                 = 60-85% of E2E
PERFORMANCE_BOTTLENECK_ATTRIBUTION  = NOT_PROVEN  (no profiler evidence)

RUNTIME_CONFIG_CANDIDATE            = YES_WITH_-t_4
SOURCE_RELEASE_CANDIDATE            = CONDITIONAL  (HEAD ≠ bdd4550, 4 session-fix commits)
OFFICIAL_COMPETITION_READY          = NO  (blocked by: starter kit, official metric definition)
```

---

## 9. Evidence Index

| Artifact | Path |
|----------|------|
| Corrected judgment (this file) | `FINAL_JUDGMENT_CORRECTED.md` |
| Status update | `STATUS_UPDATE_20260806.md` |
| Plateau 60min report | `plateau_60min/plateau_report.json` |
| Plateau 60min checkpoints | `plateau_60min/checkpoints.jsonl` (41 entries) |
| Plateau 60min sessions | `plateau_60min/sessions.jsonl` (55 entries) |
| Stability 60min summary | `stability_60min/summary.json` |
| WS session RTF (corrected name) | `official_rtf/official_speak_to_wav_rtf.json` |
| WS adapter debug files | `official_rtf/ws_adapter_*.jsonl` (30 files) |
| A/B -t 4 vs -t 8 | `ab_t4_t8/` |
| Official spec (all provisional) | `competition/METRIC_CONTRACT.md` |
| Official benchmark | `competition/benchmark_client.py` @ d50ebeac |
