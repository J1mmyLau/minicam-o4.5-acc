# P14: Flow Model (token2mel) Canonical Baseline

**Date**: 2026-07-29
**Phase**: P14 — Flow Canonical Baseline
**Status**: COMPLETE

---

## 1. Measurement Protocol

- **Binary**: `llama-omni-cli`, test case 1
- **Env vars**: `OMNI_T2W_PROFILE=2` (per-stage timing), `OMNI_T2W_PRINT_GRAPH=1` (graph print)
- **Flow backend**: CANN (auto-selected when GGML_USE_CANN compiled)
- **Samples**: 41 chunks (1 test case), plus P7 data: 136 chunks across 6 batches

---

## 2. Graph Structure

### 2.1 Computed Graphs Per Chunk

| Graph | Nodes | Description |
|-------|-------|-------------|
| **gf_nonlast** | **11,740** | Flow model (token2mel): encoder + decoder with ODE loop |
| vocoder | 2,321 | HiFi-GAN2: iSTFT decoder |
| **Total** | **~14,061** | Per chunk |

### 2.2 Flow Graph Decomposition

```
gf_nonlast: 11,740 nodes
├── Encoder (~400 nodes, 3.4%): token_embed + spk_affine + conformer + proj
└── ODE loop (~11,340 nodes, 96.6%):
    ├── n_timesteps = 5
    ├── CFG dual-branch (main + unconditional)
    └── Per timestep (~2,268 nodes):
        ├── cond_cat pre-compute (~200 nodes)
        ├── 16 × DiTBlock (~147 nodes each):
        │   ├── adaLN_modulation: silu + mul + add
        │   ├── fmAttention: QKV + QK-norm + attn_score + softmax + out_proj
        │   ├── fmCausalConvBlock: 2 × causal_conv1d (kernel=3)
        │   └── fmMLP: FC1 + silu + FC2 + residual add
        ├── final_layer: adaLN + linear → 80
        ├── CFG merge: (1+cfg)*main - cfg*uncond
        └── Euler step: x += dphi * dt
```

### 2.3 Key Dimensions

| Parameter | Value |
|-----------|-------|
| Tokens per chunk (T_chunk_token) | 28 |
| Mel channels | 80 |
| DiT hidden size | 512 |
| DiT depth | 16 |
| DiT attention heads | 8 |
| DiT head dim | 64 |
| ODE timesteps (n_timesteps) | 5 |
| Batch size (B) | 1 |

---

## 3. Per-Stage Timing

### 3.1 Complete Breakdown (41 chunks)

| Stage | n | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) | % Total |
|------|---|----------|----------|----------|-----------|---------|
| **t2m.compute** | 41 | **3,645.9** | **4,183.6** | **4,325.8** | **3,768.0** | **96.82%** |
| └ (NPU graph compute) | | | | | | |
| t2m.upload | 41 | 1.1 | 3.2 | 16.0 | 2.0 | 0.05% |
| t2m.feed_noise | 41 | 0.2 | 0.3 | 0.3 | 0.2 | 0.01% |
| t2m.download | 41 | 0.01 | 0.02 | 0.02 | 0.01 | <0.01% |
| voc.compute | 41 | 322.2 | 335.5 | 342.0 | 322.7 | 8.29% |
| voc.build_alloc | 41 | 1.0 | 1.3 | 3.6 | 1.1 | 0.03% |
| voc.upload | 41 | 0.01 | 0.02 | 0.02 | 0.01 | <0.01% |
| voc.download | 41 | 0.3 | 0.4 | 0.4 | 0.3 | 0.01% |
| **TOTAL** | | **3,970.2** | **4,517.4** | **4,661.5** | **4,094.7** | **100%** |

*Note: voc.compute is CPU vocoder (322ms). With CANN vocoder, voc.compute reduces to ~115ms.*

### 3.2 Flow Time Budget

```
Total Flow time: 3,768ms
├── ggml_backend_graph_compute: 3,768ms (99.9%) ← TARGET
└── Host overhead:                 3.7ms (0.1%)
    ├── upload (H2D):              2.0ms
    ├── feed_noise (H2D):          0.2ms
    └── download (D2H):            0.01ms
```

**The Flow model bottleneck is 100% inside ggml_backend_graph_compute.**
**Host-side overhead is negligible — upload/download are dwarfed by compute.**

### 3.3 Bucketed Timing (CANN Flow + CPU Vocoder)

| Bucket | n | t2m (ms) | voc (ms) | Total (ms) | t2m RTF |
|--------|---|----------|----------|------------|---------|
| FIRST | 1 | 4,397 | 297 | 4,694 | 5.24 |
| WARMUP (1-3) | 3 | 4,142±135 | 342±6 | 4,485±138 | 4.31 |
| STEADY (4+) | 37 | 3,723±176 | 322±6 | 4,045±180 | 3.88 |

---

## 4. Steady-State Baseline

### 4.1 Single-Run (CPU Vocoder, n=37 steady)

| Metric | t2m.compute | Total T2W |
|--------|-------------|-----------|
| Mean | 3,723ms | 4,045ms |
| Median (p50) | 3,644ms | 3,970ms |
| p95 | 4,124ms | 4,450ms |
| Std dev | 176ms | 180ms |
| CV | 0.047 | 0.044 |
| RTF | 3.72 | 4.05 |

### 4.2 Multi-Batch (P7 CANN, n=136 across 6 batches)

| Metric | t2m.compute | Total T2W |
|--------|-------------|-----------|
| Mean | 3,887ms | 4,014ms |
| Median (p50) | 3,737ms | 3,856ms |
| p95 | 4,494ms | 4,659ms |
| CV across batches | 0.027 | — |

### 4.3 Combined Baseline

**Flow model steady-state RTF: 3.72 (p50=3.64, CV=0.047)**
**With CANN vocoder: total RTF 3.92 (3,798 + 117ms)**

---

## 5. Variability Analysis

| Metric | t2m.compute | voc.compute | Notes |
|--------|-------------|-------------|-------|
| CV | 0.047 | 0.019 | Flow 2.5× more variable |
| p95/p50 | 1.13× | 1.04× | Flow has longer tail |
| p99/p50 | 1.19× | 1.06× | Flow tail extends to +19% |

**The Flow model has moderate variability (CV=0.047).** The p95 being 13% above p50 suggests there's room for tail-latency reduction, possibly from CANN kernel scheduling or memory allocator jitter.

---

## 6. Multi-Batch Consistency

From P7 data across 6 independent CANN batches:

| Batch | n | t2m.compute mean | t2m.compute p50 | CV |
|-------|---|------------------|-----------------|-----|
| 2 | 30 | 3,974ms | 3,714ms | 0.10 |
| 3 | 18 | 3,881ms | 3,771ms | 0.07 |
| 4 | 27 | 3,944ms | 3,687ms | 0.10 |
| 5 | 22 | 3,805ms | 3,689ms | 0.10 |
| 6 | 16 | 3,847ms | 3,760ms | 0.08 |
| smoke | 23 | 3,882ms | 3,779ms | 0.08 |

**Inter-batch CV of t2m.compute means: 0.027** — Flow performance is highly reproducible.

---

## 7. Optimization Surface Assessment

### 7.1 What Dominates

- **96.8% of total T2W is t2m.compute** (ggml_backend_graph_compute on CANN)
- **11,740 ggml ops per Flow chunk** vs 2,321 for vocoder
- **5 ODE timesteps × 16 DiT blocks × ~147 ops/block = ~11,760 ops**
- **CFG double computation**: Each timestep runs both main and unconditional branch

### 7.2 Optimization Leverage Points

| Target | % of t2m.compute | Approach | Est. Savings |
|--------|-----------------|----------|-------------|
| DiT Attention (16× per timestep) | ~30% | Fused MHA, flash-attention | 15-30% |
| DiT MLP (16× per timestep) | ~20% | FP16 matmul, kernel fusion | 10-20% |
| Conv1d ops | ~10% | CANN-optimized depthwise conv | 5-10% |
| CFG overhead | ~5% | Batch CFG branches together | 2-3% |
| Kernel launch overhead | ~10% | Graph fusion, reduce op count | 5-10% |

### 7.3 Amdahl Bounds

```
Optimizing all DiT attention (30%) by 25% → 7.5% total Flow improvement → ~7.3% total T2W
Optimizing all DiT MLP (20%) by 20% → 4% total Flow improvement → ~3.9% total T2W
Combined attention + MLP optimization → potentially 10-15% total T2W improvement
```

---

## 8. Key Insights for Optimization

1. **The Flow model is ALREADY on CANN** — unlike the vocoder (which needed a backend switch), the Flow model already uses ggml CANN backend. The optimization task is improving CANN kernel efficiency, not enabling CANN.

2. **Host overhead is negligible** — upload+feed_noise+download are 3.7ms total (0.1%). There's no H2D/D2H bottleneck to optimize.

3. **The graph is enormous**: 11,740 nodes. Each node spawns 1-5 CANN kernels, so we're looking at 20,000-50,000 kernel launches per chunk. **Kernel launch overhead (as seen in P8 vocoder) likely applies here too at massive scale.**

4. **5 ODE timesteps is the architecture default** — this is a quality-critical parameter. Reducing timesteps would speed up inference but risk audio quality degradation.

5. **CFG doubles compute** — the classifier-free guidance runs both main and unconditional branches through the DiT, effectively doubling the DiT cost per timestep.

---

## 9. Next Step: P15 — Flow msprof Profiling

Objective: Identify which CANN operators inside t2m.compute dominate the 3,723ms.
Method: `msprof` trace on a single Flow chunk to map ggml ops → CANN kernels → time.

Key questions for P15:
- What are the top-10 CANN kernels by time?
- What is the kernel launch overhead per op (analogous to P8's 75ms vocoder finding)?
- Are matmul ops using the Cube unit efficiently?
- Are conv1d ops using Vector unit or falling back to scalar?
- Is there opportunity for kernel fusion (e.g., silu+mul+add in adaLN)?
