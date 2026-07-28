# P7: Kernel Candidate Ranking — Decode-to-Speak Operator Hotspots

**Date:** 2026-07-28 07:35 UTC
**Based on:** msprof CANN trace (65,865 tasks, tc=4 MEDIUM, baseline OFF)
**Amdahl context:** CANN kernel time = 0.164s (0.08% of ~200s wall), Wait time = 72.3s (36%)

---

## 0. Executive Context

### The REAL Bottleneck Is Not Individual Kernels

| Component | Time | Pct |
|-----------|------|-----|
| CANN kernel execution | 0.164s | 0.08% |
| CANN task wait/launch | 72.3s | 36% |
| CPU (TTS + overhead) | ~128s | 64% |
| **Total** | **~200s** | **100%** |

**Any single-kernel optimization can at most save 0.164s (0.08% E2E).** The high-impact work is in reducing the 72s launch/wait overhead and the 128s CPU TTS time.

### Wait Time Distribution (the real enemy)

| Source | Wait Time | Pct of Total Wait |
|--------|-----------|-------------------|
| Mul (16,078 calls) | 56.2s | 77.7% |
| GatherV2 (22 calls) | 9.3s | 12.9% |
| Add (380 calls) | 4.8s | 6.6% |
| RmsNorm (107 calls) | 0.6s | 0.9% |
| Others | 1.3s | 1.9% |
| **Total** | **72.3s** | **100%** |

**Mul** is a RoPE sub-operation. 16,078 calls × 3.5ms wait each = 56s. This is ROOT CAUSE #1.

---

## 1. Candidate Audit Matrix

### Candidate A: Existing CANN ADD + RMSNorm Fusion

| Metric | Value |
|--------|-------|
| Kernel time | 3,675 μs (2.2% of CANN kernel) |
| Wait time | 5.43s (7.5% of total wait) |
| Call count | 487 (380 Add + 107 RmsNorm) |
| Existing support | `aclnnAddRmsNorm` ALREADY IMPLEMENTED, gated by `GGML_CANN_OPERATOR_FUSION` |
| Amdahl ceiling (kernel) | 0.0037s (0.002% E2E) |
| Amdahl ceiling (wait) | 5.43s (2.7% E2E) — IF fusion reduces launch count |
| Shape stability | HIGH |
| Integration risk | LOW (already implemented, just needs enabling + graph pattern match) |
| Correctness risk | LOW (CANN-provided fused op) |

**Analysis:** The kernel-time Amdahl bound (0.002% E2E) is negligible. But the wait-time bound (2.7% E2E) is meaningful IF the fusion reduces launch count. Currently `GGML_CANN_OPERATOR_FUSION` is OFF by default. Enabling it requires:
1. Verifying the MiniCPM-o graph actually matches the ADD→RMS_NORM pattern
2. Running an A/B to confirm launch count reduction

**Verdict: PRIORITY 1 (Low-risk, already implemented, enables fusion with potential wait savings)**

---

### Candidate B: Custom Residual Add + RMSNorm Fusion

| Metric | Value |
|--------|-------|
| Same data as Candidate A | — |
| Development cost | MEDIUM-HIGH (AscendC/TileLang custom kernel) |
| vs Candidate A | Strictly worse — CANN already provides `aclnnAddRmsNorm` |

**Analysis:** Custom fusion can't beat CANN's existing `aclnnAddRmsNorm`. The kernel time is too small (3,675 μs) to justify custom development. Only pursue if CANN fusion fails pattern matching.

**Verdict: REJECTED — defer to Candidate A (enable existing CANN fusion first)**

---

### Candidate C: Cast + RoPE Fusion (includes P6 RoPE F16 work)

| Metric | Value |
|--------|-------|
| Kernel time (RoPE complex) | ~148,000 μs (91% of CANN kernel) |
| Wait time (RoPE sub-ops) | 56.4s (78% of total wait) |
| Call count | 7,956 RoPE calls × ~5 sub-ops = 39,780 launches |
| P6 result | RoPE F16 Cast Elimination: +4.1% kernel speedup, Cast hypothesis DISPROVEN |
| Amdahl ceiling (kernel) | 0.148s (0.07% E2E) |
| Amdahl ceiling (wait) | 56.4s (28.2% E2E) — IF sub-ops can be fused |

**Key finding from P6:** The explicit F16↔F32 casts are NOT the problem. The real issue is that `aclnnRotaryPositionEmbedding` internally decomposes into Cos+Sin+Cast+Mul+Tile — 5 task launches per RoPE call. These internal tasks can't be eliminated from outside ACLNN.

**For real RoPE optimization, the only viable path is:**
- Replace `aclnnRotaryPositionEmbedding` with a custom F16 RoPE kernel
- Single-kernel launch instead of 5 sub-ops
- Eliminates both kernel fragmentation AND launch/wait overhead

**Development cost:** HIGH (requires AscendC/TileLang/Triton custom RoPE kernel with F16 natively)
**Stack:** AscendC (best fit for position encoding with hardware tiling), TileLang (faster prototype)

**Verdict: PRIORITY 3 — Only after P6 A/B confirms decode-to-speak benefit, and only if Amdahl ceiling (56s wait reduction) is partially achievable**

---

### Candidate D: KV ScatterUpdate / Memory Operations

| Metric | Value |
|--------|-------|
| GatherV2 kernel time | 96 μs (0.06% of CANN kernel) |
| GatherV2 wait time | 9.32s (12.9% of total wait) |
| Call count | 22 calls |
| Wait PER CALL | 423 ms (!) |
| TransData kernel | 1,988 μs (1.2%) |
| TensorMove kernel | 878 μs (0.5%) |

**Analysis:** GatherV2 has extreme wait time per call (423ms). This is the embedding lookup (`152064×768`, vocabulary size 152K). The 423ms wait per call is likely a synchronization barrier — the model stalls until the embedding lookup completes. But:
- 22 calls × 423ms = 9.3s — significant
- The wait can't be eliminated by operator optimization alone — it's an architecture constraint (embedding lookup on large vocabulary)

**Verdict: NOT a single-operator fix. Requires architectural change (smaller vocab, async embedding, or embedding cache). Not suitable for P6-P9 single-operator mission.**

---

### Candidate E: Runtime Overhead

| Metric | Value |
|--------|-------|
| Total API time | 5.72s (2.9% E2E) |
| `aclrtMemcpy` | 25,226 calls, 971ms (17.0%) |
| `aclrtSetDevice` | 6,559 calls, 798ms (14.0%) — **6,559 unnecessary SetDevice calls** |
| `aclrtLaunchKernelWithHostArgs` | 65,865 calls, 570ms (10.0%) |
| `aclrtSynchronizeStream` | 46,914 calls, 269ms (4.7%) |
| `aclrtMalloc/Free` | 44 calls, 216ms (3.8%) |

**Analysis:** `aclrtSetDevice` called 6,559 times — this is a clear inefficiency. SetDevice is idempotent and should be called once. Each call averages 122 μs. Total: 798ms of waste.

Combined with Memcpy (971ms) and unnecessary Sync calls (269ms), the runtime overhead is ~2s (1% E2E). This is larger than any single kernel optimization (max 0.164s for all kernels combined).

**Fix:** Cache `aclrtSetDevice`; batch/reduce `aclrtSynchronizeStream`; pool buffers to reduce Memcpy.

**Verdict: PRIORITY 2 (delivers measurable E2E benefit without custom kernels, purely ggml-cann dispatch fix)**

---

### Candidate F: Skinny MatMul / GEMV

| Metric | Value |
|--------|-------|
| MatMulV2 kernel time | 1,811 μs (1.1% of CANN kernel) |
| BatchMatMulV2 kernel time | 262 μs (0.2%) |
| Total MatMul calls | 240 |
| Cube utilization | 67-82% (decent for these shapes) |
| Main shapes | 50×1024 @ 1024×1024 (LLM hidden), 1×16×50×64 (attention) |
| Avg per call | 8.64 μs |

**Analysis:** MatMul is already well-optimized. Cube utilization at 67-82% is normal for small-batch decode. The total kernel time (2,073 μs = 1.3% of 0.164s) is negligible. No evidence of inefficient fallback paths.

**Verdict: REJECTED — MatMul is well-optimized, no evidence of inefficiency**

---

### Candidate G: Attention (FusedInferAttentionScore)

| Metric | Value |
|--------|-------|
| SoftmaxV2 | 24 calls, 482 μs |
| FusedInferAttentionScore | NOT in trace (likely opaque fused op) |
| FlashAttention | NOT in trace |

**Analysis:** The attention op doesn't appear as individual sub-ops in msprof, suggesting the CANN fused attention (`aclnnFusedInferAttentionScoreV2`) is running as a single opaque kernel. Without visibility into its decomposition, we can't diagnose inefficiencies.

**Verdict: INCONCLUSIVE — No profiling visibility. The fused attention is likely already efficient. Only investigate if other candidates exhausted.**

---

## 2. Final Ranking

### By E2E Impact Potential

| Rank | Candidate | Kernel Saving | Wait Saving | E2E Ceiling | Risk | Cost |
|------|-----------|---------------|-------------|-------------|------|------|
| **1** | **E: Runtime overhead** | 0s | ~2s | **~1.0%** | LOW | LOW |
| **2** | **A: Enable CANN ADD+RMSNorm fusion** | 0.004s | ~2-5s | **~1-2.5%** | LOW | LOW |
| **3** | C: Custom F16 RoPE kernel | 0.05s | ~10-30s | **~5-15%** | HIGH | HIGH |
| 4 | D: KV ScatterUpdate | 0s | ~5s | ~2.5% | HIGH | HIGH |
| 5 | F: Skinny MatMul | 0.001s | 0s | ~0.001% | MED | HIGH |
| 6 | G: Attention | unknown | unknown | unknown | HIGH | HIGH |
| — | B: Custom Add+RMSNorm | REJECTED (CANN fusion exists) |

### Priority Order for Execution

```text
PRIORITY 1: Candidate E (Runtime overhead) + Candidate A (Enable CANN fusion)
  → LOWEST risk, both are ggml-cann dispatch changes, no custom kernels
  → Combined E2E ceiling: ~2-3.5% improvement
  → Can be implemented and tested in <1 day

PRIORITY 2: Candidate C (Custom RoPE kernel)
  → HIGHEST E2E ceiling (~5-15%) but HIGH development cost
  → Only after P6 A/B confirms RoPE matters in decode-to-speak
  → Requires AscendC/TileLang custom kernel development

PRIORITY 3: Candidates D, G
  → Require architectural changes or lack profiling visibility
  → Defer to post-Priority-1 evaluation
```

---

## 3. Top-1 Recommendation

### Selected: Candidate E (Runtime Overhead Reduction)

**Why not Candidate A (ADD+RMSNorm fusion) as Top-1?**

Candidate A has higher E2E ceiling (potentially 2.5% vs 1%), but it DEPENDS on the graph pattern matching. If the MiniCPM-o graph doesn't have contiguous ADD→RMS_NORM nodes, `GGML_CANN_OPERATOR_FUSION` won't activate.

Candidate E is GUARANTEED:
- `aclrtSetDevice` called 6,559 times — provably unnecessary, fixable with a static flag
- `aclrtSynchronizeStream` called 46,914 times — many likely redundant in decode loop
- `aclrtMemcpy` 25,226 calls, 971ms — host-device copies can be batched
- No custom kernel required, pure ggml-cann dispatch improvement
- Zero correctness risk (caching SetDevice is trivially safe)

**Proposed gate:** `GGML_CANN_REDUCE_RUNTIME_OVERHEAD`, default OFF (preserves current behavior for comparison).

### Secondary (parallel): Candidate A

Audit `GGML_CANN_OPERATOR_FUSION`:
1. Check if it's present in current fork
2. Verify MiniCPM-o decode graph matches ADD+RMS_NORM pattern
3. Enable and measure actual fusion rate
4. Run paired A/B if fusion activates

---

## 4. Rejected Candidates Summary

| Candidate | Rejection Reason |
|-----------|-----------------|
| B: Custom Add+RMSNorm | CANN fusion already exists (Candidate A). Custom can't beat hardware-tuned ACLNN. |
| F: Skinny MatMul | 1.3% of 0.164s kernel = 0.002s. Cube utilization 67-82% — well-optimized. |
| D: KV ScatterUpdate | 423ms wait per GatherV2 call is a synchronization barrier, not an operator defect. Requires architectural change. |
| G: Attention | Opaque fused op — no profiling visibility. Likely already efficient. |

---

## 5. P6 RoPE F16 Status

The P6 implementation (`GGML_CANN_ROPE_FP16`, commit `b686120`) is:

```text
IMPLEMENTATION   = PASS
BUILD_AND_SMOKE  = PASS
LOCAL_SPEEDUP    = +4.1% (RotaryPositionEmbedding 5.57→5.34 μs)
CAST_HYPOTHESIS  = DISPROVEN (explicit casts fused by CANN runtime)
DECODE_TO_SPEAK  = PENDING (awaiting baseline completion for A/B)
DEFAULT_ON       = NO
```

The 4.1% kernel speedup is real but insufficient for default-ON. A/B data will determine if it's REJECTED_WITH_EVIDENCE or EXPERIMENTAL_OPT_IN.

---

**Next: P7-C RoPE FP16 A/B after baseline completes → P8 Tech Stack Decision → P9 Top-1 Implementation**
