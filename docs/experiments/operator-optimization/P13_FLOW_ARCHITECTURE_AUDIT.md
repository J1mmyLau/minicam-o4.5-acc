# P13: Flow Model (token2mel) Architecture Audit

**Date**: 2026-07-29
**Phase**: P13 — Flow Architecture Audit
**Status**: IN_PROGRESS

---

## 1. Architecture Overview

### 1.1 Model Topology

```
Token2Mel (public API)
  └── flowGGUFModelRunner (streaming runner)
        └── flowCausalMaskedDiffWithXvec (encoder + decoder)
              ├── ueUpsampleConformerEncoderV2 (encoder)
              │     ├── Input: token_ids (25+3=28 tokens per chunk)
              │     ├── Token Embedding (vocab → hidden)
              │     ├── Speaker Affine transform
              │     ├── Conformer Encoder (2× upsample + conformer layers)
              │     │     ├── Conv1d upsampler (×2 scale)
              │     │     └── Conformer layers (multi-head self-attn + conv + FFN)
              │     ├── Encoder Projection (hidden → 80 mel)
              │     └── Output: mu_ctb (80 mel channels)
              │
              └── fmCausalConditionalCFM (decoder / ODE solver)
                    ├── Input: mu from encoder, noise, timestep
                    ├── CFG (Classifier-Free Guidance): cfg_rate=0.7
                    ├── n_timesteps=10 ODE loop:
                    │     └── fmDiT (16-layer DiT, hidden=512, heads=8, head_dim=64)
                    │           ├── timestep embedder (sinusoidal + MLP)
                    │           ├── DiTBlock × 16:
                    │           │     ├── adaLN modulation
                    │           │     ├── fmAttention (QK-norm, KV cache)
                    │           │     ├── fmCausalConvBlock (2× causal conv1d)
                    │           │     └── fmMLP (hidden=512, mlp_ratio=4.0)
                    │           └── fmFinalLayer (adaLN + linear → 80)
                    └── Output: feat_ctb (predicted mel, 80 channels)
```

### 1.2 Key Dimensions

| Parameter | Value |
|-----------|-------|
| Mel channels | 80 |
| Speaker dim | 192 |
| Token vocab | 4,218+ padding |
| Tokens per chunk | 28 (25 main + 3 pre-lookahead) |
| Mel per chunk | ~50-58 frames (varies) |
| Encoder hidden size | (from gguf weights) |
| DiT hidden size | 512 |
| DiT depth | 16 |
| DiT attention heads | 8 |
| DiT head dim | 64 |
| DiT MLP ratio | 4.0 |
| ODE timesteps | 10 |

### 1.3 Three Pre-Built Graphs

| Graph | Purpose | When Used |
|-------|---------|-----------|
| `gf_setup` | Prompt setup: encode prompt tokens + build caches | Stream start only |
| `gf_nonlast` | Non-last streaming chunk with full cache round-trip | Every non-last chunk |
| `gf_last` | Last streaming chunk (different time slicing) | Final chunk of stream |

---

## 2. Compute Graph Structure

### 2.1 Flow Compute Phases (from profiling)

Each chunk's `t2m.compute` (ggml_backend_graph_compute) runs ALL of these in a single call:

| Phase | Ops | Description | Estimated Weight |
|-------|-----|-------------|------------------|
| Token embedding | lookup + matmul | Embed tokens → hidden | <1% |
| Speaker affine | matmul + add | Speaker embedding → hidden dim | <1% |
| Encoder upsample | conv1d | ×2 time dimension | ~5% |
| Conformer layers | attention + conv + ffn | Per-layer encode | ~20% |
| Encoder projection | matmul | hidden → 80 mel | <1% |
| ODE loop × 10 | **(dominates)** | 10 timesteps × 16 DiT blocks | ~70% |
| └ DiT per block | attn + conv + mlp + adaLN | One DiT block forward | ~4.4% each |
| CFG merge | scale + sub | (1+cfg)*main - cfg*uncond | ~1% |
| Euler step | add + scale | x += dphi * dt | <1% |

### 2.2 Operator Composition per DiT Block

Each of the 16 DiT blocks contains:

| Op | Type | Input Shape | Notes |
|----|------|-------------|-------|
| adaLN_modulation | silu + mul + add | [B, 1, 512] | Timestep-conditioned |
| QKV projection | mul_mat (fused) | [B, T, 512] × [512, 3*512] | Phase 2.3: fused QKV |
| QK norm | rms_norm × 2 | [B, 8, T, 64] | Pre-attention |
| Attention score | mul_mat | Q × K^T | With KV cache |
| Softmax | softmax + scale | [B, 8, T, T_cache] | Causal mask |
| Attention output | mul_mat | attn_weights × V | |
| Output projection | mul_mat | [B, T, 512] × [512, 512] | |
| Causal Conv1d × 2 | conv1d (depthwise) | [B, 512, T] | kernel=3, causal |
| Layer norms | rms_norm × 2 | [B, T, 512] | Pre/post block |
| MLP FC1 | mul_mat | [B, T, 512] × [512, 2048] | mlp_ratio=4 |
| MLP activation | silu | [B, T, 2048] | |
| MLP FC2 | mul_mat | [B, T, 2048] × [2048, 512] | |
| Residual add | add | [B, T, 512] + [B, T, 512] | Skip connection × 2 |

### 2.3 Total Operator Count Estimate

```
Per DiT block:    ~25 ggml ops
16 DiT blocks:    ~400 ops
ODE × 10:         ~4,000 ops
+ Encoder:        ~200 ops
Total per chunk:  ~4,200 ggml ops
```

---

## 3. CANN Backend Utilization

### 3.1 Backend Path

The Flow model uses the SAME ggml CANN backend as the vocoder:
```cpp
// token2wav-impl.cpp:7426
#ifdef GGML_USE_CANN
backend = ggml_backend_cann_init(gpu_idx);
#endif
```

This means both Flow and Vocoder share the optimization surface in `ggml/src/ggml-cann/ggml-cann.cpp`.

### 3.2 Key Observation: Flow Already Uses CANN

- In all our P7 experiments with `OMNI_VOC_DEVICE=gpu`, the Flow model was ALREADY running on CANN
- The `token2mel` time in CPU mode (3,863ms) and CANN mode (3,798ms) are nearly identical
- This is because the binary was compiled with `GGML_USE_CANN` and the Flow model always prefers GPU backend
- **The Flow model is ALREADY on CANN, and it's still taking 3,798ms**

### 3.3 Implication

The vocoder optimization was a straightforward backend switch (CPU→CANN). The Flow model optimization is fundamentally different — it requires optimizing the CANN graph compute itself, not just enabling CANN.

---

## 4. Profiling Infrastructure (Already In Place)

### 4.1 Environment Variables

| Variable | Effect |
|----------|--------|
| `OMNI_T2W_PROFILE=1` | Collect stats, print summary at exit |
| `OMNI_T2W_PROFILE=2` | Per-chunk `[timing]` lines with all components |
| `OMNI_T2W_PRINT_GRAPH=1` | Dump `ggml_graph_print()` for gf_nonlast/gf_last |

### 4.2 Per-Stage Timing (already in code)

| Stage | What It Measures |
|-------|-----------------|
| `t2m.upload` | Token/spk tensor upload to backend |
| `t2m.feed_noise` | Noise/timestep tensor upload |
| `t2m.compute` | `ggml_backend_graph_compute()` — THE MAIN TARGET |
| `t2m.download` | Feat tensor download from backend |

### 4.3 P7 Data Confirms

From our P7 steady-state CANN data:
- `t2m.compute` = 3,798ms average (97% of T2W)
- This is ~35× the vocoder compute (110ms)
- The `t2m.compute` dominates everything

---

## 5. Optimization Surface

### 5.1 What We Can Optimize (ggml CANN Backend)

The Flow model's CANN graph compute runs through the same ggml-cann backend. Optimization targets:

| Target | Description | Estimated Gain |
|--------|-------------|----------------|
| **Kernel fusion** | Fuse adjacent ops (e.g., silu+mul+add in adaLN) | 5-15% |
| **Attention optimization** | Fused flash-attention or CANN-optimized MHA | 10-30% |
| **Conv1d optimization** | CANN-optimized depthwise conv1d | 5-10% |
| **Graph-level batching** | Reduce kernel launch count (4,200 ops → fewer kernels) | 5-15% |
| **FP16 inference** | Half-precision for DiT (quality risk) | 20-40% |
| **Cache pre-compute** | Share cond_cat across ODE steps (already partially done) | 2-5% |

### 5.2 What We CANNOT Optimize (Architecture-Level)

| Constraint | Why |
|------------|-----|
| DiT depth (16) | Model architecture — would change output |
| ODE timesteps (10) | Quality-critical — reducing changes audio quality |
| CFG (classifier-free guidance) | Doubles compute per step (main + unconditional) |
| Encoder architecture | Model definition from GGUF weights |

### 5.3 Amdahl's Law for Flow Optimization

```
Flow T2W time: 3,798ms
├── Encoder (~20%): 760ms
└── ODE loop (~80%): 3,038ms
    ├── DiT attention (~35%): 1,330ms
    ├── DiT MLP (~25%): 950ms
    ├── DiT conv (~15%): 570ms
    └── CFG + Euler + overhead (~25%): 950ms
```

Optimizing attention (35% of 80%) gives biggest ROI per engineering hour.

---

## 6. Next Steps

### P14: Flow Canonical Baseline (NEXT)

1. Run `OMNI_T2W_PROFILE=2` with detailed per-stage timing
2. Enable `OMNI_T2W_PRINT_GRAPH=1` to count actual ggml ops
3. Measure per-stage breakdown: upload, feed_noise, compute, download
4. Establish steady-state Flow RTF baseline (n≥30)

### P15: Flow Profiling

1. msprof on the Flow model CANN graph compute
2. Identify top-10 operators by CANN kernel time
3. Check kernel launch overhead (analogous to P8 vocoder finding)

### P16: Candidate Ranking

Based on P14+P15 data, rank optimization candidates by:
- Expected RTF improvement
- Implementation complexity
- Quality risk
- Engineer-hours required

---

## 7. Key Files

| File | Content |
|------|---------|
| `token2wav-impl.h` | All Flow struct definitions |
| `token2wav-impl.cpp` | Flow model implementation |
| `token2wav-profile.h` | Profiling infrastructure |
| `ggml/src/ggml-cann/ggml-cann.cpp` | CANN backend (shared with vocoder) |
| `ggml/include/ggml-cann.h` | CANN backend header |
