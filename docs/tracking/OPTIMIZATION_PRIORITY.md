# Optimization Priority Ranking — TASK-007

**Profile:** 20260716-131033-full-omni-msprof
**Baseline:** 3f7a7f0
**Date:** 2026-07-16

---

## Priority Score Formula

```
priority_score = Potential_Gain × Confidence × Reproducibility
               ÷ (Correctness_Risk × Engineering_Cost)
```

Each dimension scored 1–5 (higher = more gain/confidence/repro/risk/cost).

## Summary Ranking

| # | Candidate | Layer | Cost | Gain Level | Score |
|---|-----------|-------|------|------------|-------|
| 1 | CAND-002: Sync memcpy → Async memcpy | L2 | 2325ms | MEDIUM (2–5% of host API path) | 8.89 |
| 2 | CAND-003: Memory allocation pooling (buffer reuse) | L2 | 1170ms | MEDIUM (2–5% of host API path) | 6.67 |
| 3 | CAND-004: Reduce Cast + Transpose + Contiguous overhead | L2 | 336ms | MEDIUM (2–5% of device time) | 2.25 |
| 4 | CAND-001: Reduce aclrtSynchronizeStream calls | L2 | 173ms | LOW (<2% of host API path) | 7.50 |
| 5 | CAND-005: Fuse element-wise operations | L5 | 126ms | LOW (<2% of device time) | 0.50 |
| 6 | CAND-006: Overlap vision/audio encode with LLM prefill | L3 | 4300ms | LOW-MEDIUM (1–3% of E2E) | 0.32 |
| 7 | CAND-007: Token2Wav pipeline optimization | L3 | 110000ms | HIGH (5–10% of E2E if T2W optimized 20%) | 1.60 |
| 8 | CAND-008: MatMul shape/layout optimization | L5 | 1834ms | LOW-MEDIUM (1–3% of device time if specific inefficiencies found) | 0.27 |

## First Batch Experiments (Top 3)

1. **EXP-001** (CAND-002) — Sync memcpy → Async
2. **EXP-002** (CAND-003) — Memory allocation pooling
3. **EXP-003** (CAND-004) — Reduce Cast/Transpose/Contiguous

## Why Not MatMul First?

- MatMulV2 is 68-75% of device time, but device time is only ~2.6s of 130s E2E
- The E2E is dominated by CPU TTS (~110s) and host-side overhead (~10s)
- Host-side optimizations (memcpy, malloc, sync) affect 10s of E2E, not 2.6s
- MatMul optimization has HIGH engineering cost and LOW confidence without shape-level profiling
- Fix host-side overhead first, then re-profile to see what remains

## Why Not AscendC?

**AscendC Gate: NOT SATISFIED**

- No specific inefficient MatMul shape has been identified
- Cube utilization at 87% median suggests ACLNN GEMM is already efficient
- Cast/Transpose overhead (12% device time) may be masking MatMul inefficiency
- Pipeline and host-side overhead dominate E2E, not device compute
- Conditions required: shape clustering, ACLNN inadequacy proof, frozen contract, measurable E2E gain

## Detailed Candidate Profiles

### 1. CAND-002: Sync memcpy → Async memcpy

- **Layer:** 2 — Low-risk source optimization
- **Current cost:** 2325.2 ms (2479 calls)
- **Device %:** N/A (host-side)
- **E2E %:** ~1.8% of 130s E2E, but 22.5% of host API path
- **Expected gain:** MEDIUM (2–5% of host API path)
- **Correctness risk:** MEDIUM
- **Engineering complexity:** MEDIUM
- **Needs source change:** True
- **Needs AscendC:** False
- **Priority score:** 8.89 (Gain=4, Conf=4, Risk=3, Eng=3, Repro=5)
- **Evidence:** aclrtMemcpy: 2325ms / 2479 calls (22.5% of host API). aclrtMemcpyAsync already used 412 times (4.2ms) — async path exists.
- **Hypothesis:** 2479 sync memcpy calls block the host. Switching to aclrtMemcpyAsync + stream sync can overlap data transfers with compute, reducing host-side wall time.
- **Validation:** aclrtMemcpy total time reduction; aclrtMemcpyAsync count increase; no correctness regression

### 2. CAND-003: Memory allocation pooling (buffer reuse)

- **Layer:** 2 — Low-risk source optimization
- **Current cost:** 1169.9 ms (142 calls)
- **Device %:** N/A (host-side)
- **E2E %:** ~0.9% of 130s E2E, but 11.3% of host API path
- **Expected gain:** MEDIUM (2–5% of host API path)
- **Correctness risk:** MEDIUM
- **Engineering complexity:** MEDIUM
- **Needs source change:** True
- **Needs AscendC:** False
- **Priority score:** 6.67 (Gain=3, Conf=4, Risk=3, Eng=3, Repro=5)
- **Evidence:** aclrtMalloc: 947ms / 63 calls (avg 15ms/call), aclrtFree: 112ms / 63 calls, aclrtMallocPhysical: 73ms / 16 calls. Total alloc/free: ~1170ms (11.3% of host API).
- **Hypothesis:** Repeated allocate/free for temporary tensors (per-op or per-graph). A workspace/buffer pool can eliminate most of these calls, replacing them with sub-allocations.
- **Validation:** aclrtMalloc/Free count reduction; no memory leak; peak HBM unchanged

### 3. CAND-004: Reduce Cast + Transpose + Contiguous overhead

- **Layer:** 2 — Low-risk source optimization
- **Current cost:** 336.0 ms (85188 calls)
- **Device %:** ~12% (Cast 6.8% + TransData 1.5% + Transpose 0.9% + TensorMove 0.4%)
- **E2E %:** ~0.26% of 130s E2E
- **Expected gain:** MEDIUM (2–5% of device time)
- **Correctness risk:** MEDIUM
- **Engineering complexity:** HIGH
- **Needs source change:** True
- **Needs AscendC:** False
- **Priority score:** 2.25 (Gain=3, Conf=3, Risk=4, Eng=4, Repro=4)
- **Evidence:** Cast: 163ms device (6-7% device time, 79449 calls), aclnnContiguous: 111ms host (4284 calls), TransData: 40ms, Transpose: 12ms, TensorMove: 10ms. Combined device+host: ~336ms.
- **Hypothesis:** Frequent Cast (F32↔F16) + Transpose + Contiguous indicate dtype/layout mismatches in the compute graph. Aligning tensor dtypes upstream can eliminate redundant conversions without precision loss.
- **Validation:** Cast/TransData/Contiguous count reduction; numerical equivalence check on output tokens

### 4. CAND-001: Reduce aclrtSynchronizeStream calls

- **Layer:** 2 — Low-risk source optimization
- **Current cost:** 172.9 ms (4542 calls)
- **Device %:** N/A (host-side)
- **E2E %:** ~0.13% of 130s E2E
- **Expected gain:** LOW (<2% of host API path)
- **Correctness risk:** LOW
- **Engineering complexity:** LOW
- **Needs source change:** True
- **Needs AscendC:** False
- **Priority score:** 7.50 (Gain=2, Conf=3, Risk=2, Eng=2, Repro=5)
- **Evidence:** aclrtSynchronizeStream: 172.7ms / 4535 calls (1.7% of host API), aclrtSynchronizeDevice: 0.13ms / 7 calls.
- **Hypothesis:** Many sync points are at per-op boundaries rather than graph boundaries. Removing unnecessary ones reduces host blocking.
- **Validation:** SynchronizeStream count reduction; no correctness regression

### 5. CAND-005: Fuse element-wise operations

- **Layer:** 5 — Operator-level optimization
- **Current cost:** 126.0 ms (32087 calls)
- **Device %:** ~5%
- **E2E %:** ~0.10% of 130s E2E
- **Expected gain:** LOW (<2% of device time)
- **Correctness risk:** MEDIUM
- **Engineering complexity:** HIGH
- **Needs source change:** True
- **Needs AscendC:** False
- **Priority score:** 0.50 (Gain=1, Conf=2, Risk=3, Eng=4, Repro=3)
- **Evidence:** Mul: 76.7ms + Add: 32.8ms + Swish: 13.9ms + Gelu: 2.0ms. Combined element-wise: ~126ms device time (~5%).
- **Hypothesis:** Adjacent element-wise ops (e.g., Swish = Mul + Sigmoid) can be fused into single CANN kernels, reducing kernel launch overhead and intermediate tensor traffic.
- **Validation:** Reduced Mul/Add/Swish count; numerical equivalence check

### 6. CAND-006: Overlap vision/audio encode with LLM prefill

- **Layer:** 3 — Graph / Pipeline optimization
- **Current cost:** 4300.0 ms (N/A (pipeline stage) calls)
- **Device %:** N/A
- **E2E %:** ~3.3% of 130s E2E
- **Expected gain:** LOW-MEDIUM (1–3% of E2E)
- **Correctness risk:** HIGH
- **Engineering complexity:** HIGH
- **Needs source change:** True
- **Needs AscendC:** False
- **Priority score:** 0.32 (Gain=2, Conf=2, Risk=5, Eng=5, Repro=2)
- **Evidence:** Vision encode: 306ms (serial), audio encode: ~4s (serial). Both run before LLM prefill. Vision and audio are independent and could overlap.
- **Hypothesis:** Vision encoder (device_0) and audio encoder can run concurrently on separate streams/devices. This reduces the critical path before LLM prefill begins.
- **Validation:** E2E wall time reduction; correct vision/audio features; no race conditions

### 7. CAND-007: Token2Wav pipeline optimization

- **Layer:** 3 — Graph / Pipeline optimization
- **Current cost:** 110000.0 ms (27 chunks calls)
- **Device %:** N/A (CPU)
- **E2E %:** ~85% of 130s E2E
- **Expected gain:** HIGH (5–10% of E2E if T2W optimized 20%)
- **Correctness risk:** MEDIUM
- **Engineering complexity:** HIGH
- **Needs source change:** True
- **Needs AscendC:** False
- **Priority score:** 1.60 (Gain=4, Conf=2, Risk=3, Eng=5, Repro=3)
- **Evidence:** T2W: 27 chunks serial, RTF ~3.95 per chunk, ~110s total. Each chunk: encode → decode → write. Pipeline can overlap encode of chunk N+1 with decode of chunk N.
- **Hypothesis:** Token2Wav dominates E2E at ~110s. Overlapping encode/decode across chunks could reduce wall time by 10-30%.
- **Validation:** T2W total wall time; audio quality comparison (PESQ/MOS)

### 8. CAND-008: MatMul shape/layout optimization

- **Layer:** 5 — Operator-level optimization
- **Current cost:** 1834.1 ms (30928 calls)
- **Device %:** 68-75%
- **E2E %:** ~1.4% of 130s E2E (device is 2% of E2E)
- **Expected gain:** LOW-MEDIUM (1–3% of device time if specific inefficiencies found)
- **Correctness risk:** MEDIUM
- **Engineering complexity:** HIGH
- **Needs source change:** True
- **Needs AscendC:** False
- **Priority score:** 0.27 (Gain=2, Conf=1, Risk=3, Eng=5, Repro=2)
- **Evidence:** MatMulV2: 1834ms device (68-75% device time), 30928 calls, P50=36.9us, P90=105.9us, median cube util=87.3%. Device 0 avg 55.5us, device 1 avg 63.8us.
- **Hypothesis:** Some MatMul shapes may benefit from weight pre-packing or layout optimization. Cube utilization at 87% suggests reasonable efficiency but some headroom exists.
- **Validation:** Per-shape MatMul microbenchmark; overall device time reduction

