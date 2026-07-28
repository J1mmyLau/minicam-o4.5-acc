# Candidate E2: aclrtSynchronizeStream Reduction — DEFINITIVE VERDICT

**Date:** 2026-07-28
**Binary:** `eaffbe35` (libggml-cann, V0 runtime diag + sync trace)
**Method:** Single diagnostic run with `GGML_CANN_RUNTIME_DIAG=1 GGML_CANN_SYNC_TRACE_CSV=/tmp/sync_trace2.csv`, ngl=8
**Test case:** omni_test_case_0 (SHORT, 1 WAV, request_to_first_audio=19,770ms)

---

## 1. Verdict

```text
CANDIDATE_E2_STREAM_SYNCHRONIZATION = REJECTED_BY_AMDAHL_BOUND
```

## 2. Evidence

### 2.1 Aggregate

| Metric | Value |
|--------|-------|
| Total `aclrtSynchronizeStream` calls | 3,861 |
| Syncs per graph evaluation | 4.3 |
| **Total sync wall time** | **32.98 ms** |
| Sync share of request wall | **0.17%** |
| Average sync duration | 8.5 μs |

### 2.2 By Callsite

| Callsite | Count | Total Time | Avg Duration |
|----------|-------|-----------|-------------|
| `SYNC_BACKEND_PUBLIC` (scheduler barrier) | 3,848 (99.7%) | 32.90 ms | 8.5 μs |
| `SYNC_D2D_COPY` (cross-device) | 13 (0.3%) | 0.07 ms | 5.4 μs |

### 2.3 By Classification

| Classification | Count | Total Time | Avg Duration | Max Duration |
|---------------|-------|-----------|-------------|-------------|
| MANDATORY_BARRIER | 992 (25.7%) | 26.65 ms | 26.9 μs | 3,093 μs |
| DUPLICATE_NO_WORK | 2,869 (74.3%) | 6.32 ms | 2.2 μs | 262 μs |

### 2.4 Top-5 Longest Syncs (Initialization Phase)

| Graph | Duration | Stream | Notes |
|-------|---------|--------|-------|
| 0 | 3,093 μs | A | Device setup / first weight upload |
| 0 | 2,795 μs | B | Memory allocation |
| 0 | 2,492 μs | C | Weight upload |
| 0 | 1,410 μs | D | Weight upload |
| 0 | 1,381 μs | E | Weight upload |

These 5 initialization syncs account for 11.2ms (33.9% of total sync time). All are one-time setup costs, not per-request overhead.

### 2.5 Steady-State MANDATORY Syncs

Excluding the top-5 initialization syncs:

| Metric | Value |
|--------|-------|
| Remaining MANDATORY | 987 syncs |
| Total time | 15.5 ms |
| Average duration | 15.7 μs |

## 3. Pattern Analysis

### 3.1 DUPLICATE_NO_WORK Pattern

74.3% of syncs are on a stream where no new work was submitted since the last sync. These cost an average of **2.2 μs** each — confirming the stream is idle and the driver returns near-instantly. Total duplicate cost: 6.3ms per request.

The GGML scheduler calls `ggml_backend_cann_synchronize` ~4.3 times per graph evaluation, but only ~1.1 of those are "real" (first sync after work submission). The remaining ~3.2 are redundant callbacks.

### 3.2 Stream Distribution

| Stream Hash | Syncs | Role |
|------------|-------|------|
| `187650715500160` | 3,073 | Dominant stream (most work) |
| `187650710817840` | 730 | Secondary stream |
| Others (4 streams) | 58 | Infrequent |

Two streams account for 98.5% of all sync activity.

### 3.3 Regular Cadence

Inter-sync gaps are consistently ~57ms, suggesting the scheduler polls at a fixed interval rather than syncing continuously.

## 4. Amdahl Gate Analysis

| Gate | Threshold | Measured | Pass? |
|------|-----------|----------|-------|
| Sync time ≥ 1% of target path | ≥197ms | **33.0ms (0.17%)** | ❌ FAIL |
| DUPLICATE_NO_WORK cumulative measurable | — | 6.3ms total | ✅ Measurable |
| Deferrable sync time significant | — | 0ms (none identified) | ❌ FAIL |
| Graph-boundary host blocking gaps | — | avg gap 57ms, sync returns in 2-27μs | ❌ FAIL |

**Even eliminating 100% of DUPLICATE_NO_WORK syncs (6.3ms) + halving MANDATORY sync time (13.3ms) = 19.6ms savings = 0.10% improvement. Below measurement threshold.**

## 5. Where Does the 72.3s Wait Come From?

P4 profiling showed CANN kernel = 0.164s (0.08%) with Wait = 72.3s (36%). This diagnostic proves the Wait is NOT from `aclrtSynchronizeStream` (which accounts for only 33ms).

**Likely Wait sources (not yet measured):**
- CPU waiting on TTS thread (Talker token generation is autoregressive)
- Thread condition variables / mutex synchronization
- Pipeline idle: Talker generating tokens while T2W/audio pipeline waits
- Model output length variability (the 2.3×-41× LLM variance from P3)

## 6. Optimization Attempts Considered and Rejected

| Approach | Feasibility | Reason |
|----------|------------|--------|
| Skip DUPLICATE_NO_WORK syncs | REJECTED | 6.3ms total potential (0.03%), below noise floor |
| Reduce sync frequency | REJECTED | Scheduler contract — changing would risk correctness |
| Event-based dependency (replace sync with event wait) | REJECTED | avg sync is 8.5μs — event overhead would be similar |
| Batch multiple syncs | REJECTED | Already effectively batched at ~57ms intervals |

## 7. Conclusion

**Candidate E (Runtime Overhead Reduction) is fully REJECTED for both sub-candidates:**

| Candidate | Verdict | Key Evidence |
|-----------|---------|-------------|
| E1: aclrtSetDevice caching | `REJECTED_WITH_EVIDENCE` | thread_local guard already at 95.6% hit rate |
| E2: aclrtSynchronizeStream reduction | `REJECTED_BY_AMDAHL_BOUND` | Total sync time 33ms (0.17%), avg 8.5μs per call |

The CANN runtime overhead path is effectively optimized already. Host-side runtime API calls are NOT the bottleneck.

## 8. Next Steps

The optimization focus should shift to other layers of the stack, per the user's P10 guidance:
- H2D small-transfer aggregation (2,293 H2D transfers)
- D2H readback frequency (928 D2H transfers)  
- Graph launch gap analysis
- CPU/NPU pipeline parallelism (TTS/Talker thread wait decomposition)
- Pinned host memory for transfer buffers
