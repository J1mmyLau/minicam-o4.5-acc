# FLOW PROFILE PERCENTAGE AUDIT

**Date**: 2026-07-29
**Status**: AUDITED — Percentages use different denominators, corrected

---

## 1. The Problem

P15-C reported both:
- "Im2col 42% of NPU time" — from msprof `op_statistic.csv`
- "Kernel launch overhead 73%" — estimated from CANN Flow wall time

These numbers have DIFFERENT DENOMINATORS and CANNOT be directly compared or summed.

---

## 2. Definitions

### 2.1 Flow Wall Time

```
flow_wall_ms = 154.9ms  (mean steady-state, from OMNI_T2W_PROFILE=2 timing)
```

This is the end-to-end `ggml_backend_graph_compute()` time measured by the application.
It includes everything: host dispatch + NPU execution + synchronization.

### 2.2 NPU Kernel Time (from msprof)

```
total_npu_kernel_ms = 2,290ms  (from msprof op_statistic, device_0)
                      across ~60 chunks, ~188k kernels
per_chunk_npu_kernel_ms ≈ 2,290 / 60 ≈ 38ms
```

### 2.3 Im2col Time (from msprof)

```
total_im2col_ms = 926ms  (from msprof op_statistic, device_0)
per_chunk_im2col_ms ≈ 926 / 60 ≈ 15.4ms
```

---

## 3. Corrected Time Budget

### 3.1 Per-Chunk CANN Flow Wall Time (154.9ms)

```
flow_wall_ms = 154.9ms (100.0%)
├── NPU kernel execution:     ~38ms  (24.5%)  ← from msprof
│   ├── Im2col:               ~15ms  (9.7%)   ← from msprof
│   ├── Transpose:             ~4ms  (2.6%)
│   ├── Element-wise (Add+Mul+Cast): ~5ms  (3.2%)
│   ├── Normalization:         ~2ms  (1.3%)
│   ├── MatMul (Cube):         ~2ms  (1.3%)
│   └── Other NPU ops:         ~9ms  (5.8%)
│
├── Host kernel launch + sync: ~112ms (72.3%) ← residual
│   (includes: ACL API dispatch, stream sync,
│    memory allocator, graph executor overhead)
│
└── H2D/D2H:                    ~4ms  (2.6%)  ← from t2m.upload+download
```

### 3.2 NPU Kernel Time Internal Breakdown (38ms = 100%)

```
npu_kernel_ms = 38ms (100%)
├── Im2col:        15.4ms  (40.5%)  ← 42% in msprof
├── Transpose:      4.0ms  (10.6%)
├── Add:            3.0ms  (7.9%)
├── Mul:            2.1ms  (5.5%)
├── ConcatD:        1.5ms  (3.9%)
├── LayerNormV3:    1.5ms  (3.8%)
├── Cast:           1.5ms  (3.8%)
├── BatchMatMulV2:  1.4ms  (3.6%)
├── AsStrided:      1.3ms  (3.4%)
├── Other:          6.3ms  (16.6%)
```

---

## 4. Im2col End-to-End Significance

| Metric | Value | % Denominator |
|--------|-------|--------------|
| Im2col / NPU kernel time | 40.5% | NPU kernel execution |
| Im2col / Flow wall time | **9.7%** | End-to-end Flow |
| Im2col / Total T2W | **5.6%** | Total 274ms |

**Eliminating ALL Im2col would save at most ~15ms from 274ms total → 5.6% improvement.**
This is NOT the top priority for further optimization.

---

## 5. Kernel Launch Overhead End-to-End Significance

| Metric | Value | % Denominator |
|--------|-------|--------------|
| Launch overhead / Flow wall time | 72.3% | End-to-end Flow |
| Launch overhead / Total T2W | **40.9%** | Total 274ms |

**Kernel launch overhead (~112ms) is the #1 optimization target, NOT Im2col.**
Reducing launch overhead by 50% would save ~56ms → RTF 0.27 → 0.22.

---

## 6. Caveats

1. **msprof captures all chunks**: The 2.29s NPU time is for the entire run (~60 chunks).
   Per-chunk breakdown is approximate (total / 60).

2. **msprof precision**: Not all CANN operations may be captured. The residual
   (wall - kernel - H2D/D2H = 112ms) is attributed to host-side overhead,
   but some may be from unprofiled CANN operations.

3. **Overlap**: Some host dispatch may overlap with NPU execution on different streams.
   The 112ms is an upper bound on non-overlapped overhead.

4. **NPU idle time**: If the NPU is idle during host dispatch, the total wall time
   includes NPU idle periods. The msprof kernel time measures only active NPU time.

---

## 7. Optimization Priority (Corrected)

| Rank | Target | End-to-End % | Est. Savings | Approach |
|------|--------|-------------|-------------|----------|
| **1** | **Kernel launch/dispatch** | **72% of Flow** | **20-60ms** | Graph execution reuse, reduce sync points |
| 2 | NPU kernel execution | 24% of Flow | 10-15ms | Operator fusion, better layout |
| 3 | Im2col (within kernel) | 10% of Flow | 5-8ms | Fused conv1d, custom kernel |
| 4 | H2D/D2H | 3% of Flow | 1-2ms | Async transfer, pinned memory |

**The #1 optimization target is host-side kernel launch/dispatch overhead (~112ms),
not Im2col (~15ms).** This is the same pattern found in P8 for the vocoder
(75ms kernel launch overhead vs 3ms NPU compute).

---

## 8. Methodology Note for Future Profiling

When reporting msprof percentages, always state the denominator:

| Statement | Correct? | Why |
|-----------|----------|-----|
| "Im2col is 42% of NPU kernel time" | ✅ | Denominator = total NPU kernel execution time |
| "Im2col is 42% of Flow time" | ❌ | Actually 9.7% |
| "Im2col is 42% of total T2W" | ❌ | Actually 5.6% |
| "Launch overhead is 73% of Flow time" | ✅ | Denominator = Flow wall time |
| "Launch overhead + Im2col = 115%" | ❌ | Different denominators |

Every percentage must include the denominator scope.
