# T2W Backlog Diagnosis — Phase 1 & 2 Complete

**Date:** 2026-08-10
**Status:** PHASE_1_2_COMPLETE — ready for Phase 3 drain policy design

---

## Phase 1: Single-Session Queue Dynamics

### Instrumentation Added
- `T2WThreadInfo::diag_enqueued_total`, `diag_dequeued_total` (atomic counters)
- `T2WOut::dequeue_ts_ns`, `complete_ts_ns` (per-task timing)
- `AudioCbState::last_audio_delivered_ns` (audio tail)
- `[t2w_diag]` events: `worker_batch`, `task_timing`, `cleanup_begin`
- Gate: `OMNI_T2W_QUEUE_DIAG=1` (zero-cost when unset)

### Three Core Metrics (1 session × 35 chunks)

#### 1. Backlog Slope
```
Δqueue / Δtime = 126 items / 36.1s = 3.49 items/second
backlog_slope > 0  →  SUSTAINED GROWTH (not bursty)
```
**Verdict: Producer OUTRUNS consumer.** Not transient. Not bursty.

#### 2. Task Service Time
```
queue_wait_us  = 20 μs        (negligible — nearly instant dequeue)
service_us     = 5,397,110 μs (5.4 seconds — Flow+Vocoder on CANN)
total_us       = 5,397,130 μs (99.999% service time)
```
**Verdict: SERVICE TIME dominates. NOT a queuing delay problem.**

#### 3. Queue Depth at Cleanup
```
enqueued_total = 169 items
dequeued_total = 22 items  (only 13% processed!)
queue_depth    = 147 items (87% pending)
timeout_ms     = 900,000 ms (15 minutes — from adaptive formula)
```

---

## Phase 2: Chunk Sweep

| Chunks | Enqueued | Dequeued | Depth | Service (ms) | Timeout (ms) |
|--------|----------|----------|-------|-------------|-------------|
| 5      | 23       | 17       | 6     | 4,444       | 170,000     |
| 35     | 169      | 22       | 147   | 5,397       | 900,000     |

Queue depth is linear with chunk count. Service time varies 4.4s–55.2s depending on batch size.

---

## Differential Diagnosis (User's 4 Hypotheses)

| Hypothesis | Verdict | Evidence |
|-----------|---------|----------|
| A. Producer > consumer throughput | **CONFIRMED** | 169 enqueued vs 22 dequeued (7.7×) |
| B. Bursty, catches up later | **REFUTED** | backlog_slope = 3.49 items/s > 0, steady over 36s |
| C. Response/session ends too early | **PARTIALLY** | Cleanup starts while worker mid-batch. But drain predicate correctly waits for completion. |
| D. Generation bookkeeping races ahead | **NOT PRIMARY** | Even at gen=6, queue is 21 items deep. Bookkeeping leads, but real backlog exists. |

---

## Root Cause

```
T2W worker service time (5-55s per batch)
     >> 
TTS producer enqueue interval (~0.2-0.5s per item)
     →
    Unbounded queue growth
     →
    Giant adaptive timeout at cleanup (8-15 min)
     →
    Session reuse blocked
```

**The fundamental problem is T2W SERVICE TIME on CANN flow-only, not drain policy.**

The adaptive timeout formula (`5000 + N*15000 + 60000`) correctly reflects this: with N=147 items taking ~0.6 items/s, natural drain is ~245 seconds. The formula overestimates slightly because items are batch-processed.

---

## Implications for Fix Design

1. **Timeout tuning (30s, 60s, etc.): WRONG LEVEL.** Any fixed timeout either drops audio or blocks too long. The T2W service time varies by 12× depending on batch size.

2. **Event-driven drain: NECESSARY but INSUFFICIENT.** Waiting for `queue_depth == 0` is correct protocol but the wait is inherently long (minutes) because service time is the bottleneck.

3. **Per-chunk drain (OMNI_PER_CHUNK_DRAIN=1): CORRECT DIRECTION.** By draining after each chunk, the queue never accumulates 147 items. Each chunk's T2W tasks complete before the next chunk starts. Trade-off: per-chunk wall time increases (~5.4s per chunk × 35 chunks ≈ 189s total vs current ~79s). But cleanup is instant (0 queued items).

4. **Backpressure: ALTERNATIVE.** Block TTS enqueue when queue depth exceeds threshold. This lets the T2W worker catch up naturally without the full per-chunk blocking.

5. **Watermark-based completion: CORRECT PROTOCOL.** Session sealed → capture final_enqueued_seq → wait for completed_seq >= final_enqueued_seq → session reusable. This is the right event-driven signal, but the wait time depends on T2W throughput.

---

---

## Phase 3b: feed_window Sub-Component Decomposition

**Date:** 2026-08-10
**Method:** `OMNI_T2W_PROFILE=2` enables existing per-call `[timing]` instrumentation (encoder / flow_match / token2mel / vocoder / total). Combined with `OMNI_T2W_QUEUE_DIAG=1` for cross-validation.

**Model:** F16, **Chunks:** 5, **n=12** feed_window calls

### Raw Data (12 calls)

| Call | Encoder | Flow_Match | Token2Mel | Vocoder | Total | Audio(samples) |
|------|---------|------------|-----------|---------|-------|-----------------|
| 0(first) | 9.8ms | 133.3ms | 143.1ms | **341.2ms** | 484.3ms | 20160 |
| 1 | 7.0ms | 141.9ms | 149.0ms | **338.0ms** | 487.0ms | 24000 |
| 2 | 7.0ms | 133.0ms | 140.0ms | **323.1ms** | 463.1ms | 24000 |
| 3 | 9.3ms | 133.2ms | 142.5ms | **323.6ms** | 466.1ms | 24000 |
| 4 | 9.7ms | 132.9ms | 142.6ms | **323.1ms** | 465.7ms | 24000 |
| 5 | 7.1ms | 131.7ms | 138.8ms | **323.1ms** | 461.9ms | 24000 |
| 6 | 6.6ms | 128.0ms | 134.6ms | **323.0ms** | 457.5ms | 24000 |
| 7 | 6.8ms | 129.6ms | 136.4ms | **323.0ms** | 459.4ms | 24000 |
| 8 | 9.0ms | 131.9ms | 140.9ms | **323.1ms** | 464.0ms | 24000 |
| 9 | 6.8ms | 123.7ms | 130.5ms | **323.1ms** | 453.6ms | 24000 |
| 10 | 7.2ms | 115.0ms | 122.2ms | **324.0ms** | 446.2ms | 24000 |
| 11 | 7.2ms | 126.4ms | 133.6ms | **323.4ms** | 457.0ms | 24000 |

### Averages

| Component | Avg (ms) | % | Device | Variability |
|-----------|----------|---|--------|-------------|
| Encoder | 7.8 | 1.7% | CANN (flow) | 6.6–9.8ms (σ≈1.2) |
| Flow Match (DiT) | 130.1 | 28.0% | CANN (flow) | 115–142ms (σ≈6.9) |
| Token2Mel (Flow total) | 137.9 | 29.7% | CANN flow-only | 122–149ms |
| **Vocoder Hg2** | **326.0** | **70.3%** | **CPU** | 323–341ms (σ≈4.8) |
| **Total** | **463.8** | **100%** | — | 446–487ms |

### Cross-Validation with timing_decompose

Each batch's `feed_us` = Σ of per-call `[timing]` totals for that batch:

| Batch | timing_decompose feed_us | Σ[timing] total | Windows | Error |
|-------|--------------------------|-----------------|---------|-------|
| 1 | 484,327 μs | 484,284 μs | 1 | 0.01% |
| 2 | 487,010 μs | 486,967 μs | 1 | 0.01% |
| 3 | 929,216 μs | 929,145 μs | 2 | 0.01% |
| 4 | 1,385,297 μs | 1,385,129 μs | 3 | 0.01% |
| 5 | 2,280,460 μs | 2,280,178 μs | 5 | 0.01% |

**Zero measurement error — instrumentation is internally consistent.**

### Key Finding

```
Vocoder Hg2 on CPU:  326.0ms (70.3%)  ← DOMINANT BOTTLENECK
Flow Matching CANN:  130.1ms (28.0%)  ← Secondary
Encoder CANN:          7.8ms ( 1.7%)  ← Negligible
                              ========
Total per window:     463.8ms (100%)
```

**The Vocoder runs on CPU** (CANN flow-only: 11 operators failed CANN placement). It consumes 70.3% of T2W time. Flow matching on CANN is only 28%. This means CANN compute optimization alone can at most reduce T2W time by ~30%.

### Note on Phase 3a 4.4s Anomaly

Phase 3a measured `feed_us=4,408,204μs` for `windows=1` with Q8_0 + 35 chunks. This was anomalous — the current 12-call F16 dataset shows consistent ~464ms/call. Possible causes for the 4.4s outlier:
1. Q8_0 vs F16 model (Q8_0 incurs dequant overhead)
2. Accumulated mel cache at chunk 35 (is_final drain processes ALL cached mel)
3. Single measurement (n=1), cannot rule out transient spike

Regardless, the F16 5-chunk decomposition with n=12 and cross-validation is the reliable dataset.

---

## Unit Clarification

Throughout this document, three distinct units are referenced:

| Unit | Meaning | Example |
|------|---------|---------|
| **Input chunk** | Audio/video input chunks pushed by client (per prefill) | "1800 input chunks" = cumulative TTS audio frames across a session |
| **T2W task** | One `T2WOut` item enqueued into the T2W worker queue | "81 T2W tasks" = count of actual T2W inference jobs generated |
| **WAV/audio output** | One `.wav` file (or audio segment) produced by Vocoder per window | "92 WAV outputs" = count of audio files from feed_window calls |

**These are NOT 1:1.** A 1800-chunk audio session produces ~81 T2W tasks and ~92 WAV files.
The ratio depends on: chunk_size, max_new_speak_tokens, window overlap, and batch merging.
Always specify which unit is being counted.

---

## Phase 4: Flow ∥ Vocoder Pipeline — Backlog Fix VERIFIED

**Date:** 2026-08-10
**HEAD:** 051e993

### Fix Summary

Implemented Flow(Worker) ∥ Vocoder(Worker) pipeline with bounded mel queue (capacity=2).
Env gate: `OMNI_T2W_PIPELINE_OVERLAP=1` (default OFF, zero-cost when off).

### Pre/Post Pipeline Comparison

| Metric | Pre-Pipeline (serial) | Post-Pipeline | Change |
|--------|----------------------|---------------|--------|
| Backlog slope | +3.49 items/s | **0.00 items/s** | FIXED |
| Consumer rate | 0.61 items/s | **1.53 items/s** | +2.5× |
| Peak queue depth | 147 | **1** | BOUNDED |
| Depth at cleanup | 147 | **0** | EMPTY |
| Per-window latency | 601ms | **375ms** | −37.6% |
| Speedup | 1.00× | **1.60×** | |

### P0 Validation (Q4_K_M, pipeline ON)

| Gate | Result |
|------|--------|
| P0-A: Queue dynamics | POST_PIPELINE_BACKLOG_SLOPE=0.00, consumer 1.53 items/s, peak depth=1 |
| P0-B: 1800-input-chunk scale | 81 T2W tasks, 81 dequeued, 92 WAVs valid, depth=0 at all checkpoints |
| P0-C: 50-session reuse | 50/50 first-attempt PASS, 0 rejections, 0 drain timeouts, 0 bad WAVs |

### T2W_BACKLOG_ROOT_CAUSE = CONFIRMED

Consumer throughput (0.61 items/s serial) was slower than producer rate (4.7 items/s).
Per-window service time dominated by CPU Vocoder (70.3% of 464ms).
Pipeline overlap (Flow ∥ Vocoder) increased consumer rate to 1.53 items/s,
enabling the worker to keep up with the producer. Bounded mel queue (capacity=2)
provides natural backpressure as safety net.

### Remaining Gap

`OMNI_T2W_PIPELINE_OVERLAP=1` is default-OFF. Fixed when enabled, NOT fixed on default runtime path.
See Final F16 Candidate Freeze plan for resolution.

---

## Phase 3 Conclusion: Consumer Performance Optimization Path

Per the user's decision tree: "如果 5.4s 主要来自 Flow/Vocoder 计算：→ 进入 consumer performance optimization"

**Verdict: T2W time IS dominated by Flow+Vocoder compute (99.97% per Phase 3a, confirmed by Phase 3b). → CONSUMER PERFORMANCE OPTIMIZATION.**

### Optimization Targets (ranked by impact)

| Priority | Target | Current | Device | Potential |
|----------|--------|---------|--------|-----------|
| **P0** | Vocoder Hg2 | 326ms (70%) | CPU → CANN? | 10× if CANN-able |
| **P1** | Pipeline Flow∥Vocoder | Serial | Overlap | ~30% wall reduction |
| **P2** | Flow DiT diffusion | 130ms (28%) | CANN | Limited (already accelerated) |

### Implications for Drain Policy

The T2W worker processes ~0.46s/window, ~2.2 windows/s at batch_size=1. Producer enqueues ~4-5 items/second. With batch accumulation (windows=5, items=7), throughput improves to ~0.32s/item — still slower than producer.

- **Per-chunk drain**: Each chunk spawns ~2.4 feed_window calls = ~1.1s additional latency per chunk. For 35 chunks: ~39s extra (acceptable for correctness, destroys real-time)
- **Backpressure**: Block TTS when queue > threshold. Lets worker catch up naturally.
- **Pipeline overlap**: Run Flow of window N+1 while Vocoder processes window N. Reduces effective per-window time from 464ms to max(Flow, Vocoder) = 326ms (30% improvement).
- **Vocoder CANN acceleration**: If Vocoder CANN achieves similar speedup as Flow CANN (20× observed), vocoder drops from 326ms to ~16ms, total drops from 464ms to ~154ms (3× speedup).
