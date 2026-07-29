# G13: Submission Package — CANN Flow + Vocoder Optimization

**Date:** 2026-07-29
**Tag:** `cann-flow-vocoder-aclgraph-rtf0229-20260729`
**HEAD:** `767dc20`
**Status:** READY_FOR_SUBMISSION

---

## 1. Competition Metric

```
Per-Chunk RTF = (flow_compute + vocoder_compute) / audio_duration_ms

CPU baseline:                 RTF ≈ 4.21
Phase 3 (CANN Flow+Vocoder):  RTF ≈ 0.229  (18.4× vs CPU)
Per-chunk steady-state:       RTF ≈ 0.224  (call >= 4)
```

## 2. Architecture

| Component | Backend | Speedup |
|-----------|---------|---------|
| Flow model | CANN (Ascend 910C) | 24.1× vs CPU |
| Vocoder | GPU (NPU) | 2.92× vs CPU |
| ACL Graph Capture | RELAXED mode | -28.2% Flow compute |
| ADD+LayerNorm Fusion | aclnnAddLayerNorm | ~1ms |

## 3. Key Optimizations

| Rank | Optimization | Impact | Status |
|------|-------------|--------|--------|
| 1 | ACL Graph capture (RELAXED) | Flow: 155→111ms (-28.2%) | ✅ |
| 2 | ADD+NORM fusion | ~1ms | ✅ |
| 3 | Im2col | Deferred (post-gate) | ⏭️ |
| 4 | Async H2D | Deferred (already async) | ⏭️ |

## 4. Feature Flags

```bash
GGML_CANN_ACL_GRAPH=on          # Enable graph capture
GGML_CANN_OPERATOR_FUSION=on    # Enable operator fusion
GGML_CANN_GRAPH_MIN_NODES=100   # Skip capture for small graphs
GGML_CANN_PREFILL_USE_GRAPH=    # Disable graph for prefill (default)
```

## 5. Canonical Command

```bash
OMNI_T2W_DEVICE=cann-flow-only \
OMNI_VOC_DEVICE=gpu \
OMNI_T2W_PROFILE=2 \
GGML_CANN_ACL_GRAPH=on \
GGML_CANN_OPERATOR_FUSION=on \
GGML_CANN_GRAPH_MIN_NODES=100 \
./build/bin/llama-omni-cli \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
  --omni \
  --test tools/omni/assets/test_case/omni_test_case/omni_test_case_ 4
```

## 6. Environment

| Component | Version |
|-----------|---------|
| CANN | 9.1.0-beta.1 |
| NPU | Ascend 910C (dav-2201) |
| Platform | Linux aarch64, openEuler 22.04 |
| Build | CMake, USE_ACL_GRAPH=ON |

## 7. Gate Results

| Gate | Status | Key Data |
|------|--------|----------|
| G1: Perf consistency | ✅ PASS | Numbers self-consistent |
| G2: Graph cache audit | ✅ PASS | Code audit complete |
| G3: 4-quadrant A/B | ✅ PASS | Q4(ON,ON) best: RTF=0.245 |
| G4: Chunk buckets | ✅ PASS | Steady RTF=0.224 (call≥4) |
| G5: Benchmark harness | ⏭️ BLOCKED | External harnesses unavailable |
| G6: Demo | ✅ PASS | 9 cases, 0 CANN errors |
| G7: 30-min stability | ✅ PASS | 37 iters, 661 WAVs, 0 errors |
| G8: 1-hr stability | ✅ PASS | 66 iters, 1368 WAVs, 0 errors |
| G9: KV cache regression | ⏭️ DEFERRED | Next session |
| G10: Multi-prefix | ⏭️ DEFERRED | Next session |
| G11: T2W lifecycle | ⏭️ DEFERRED | Next session |
| G12: Clean reproduction | ✅ PASS | RTF 0.236 vs 0.245 (±3.6%) |
| G13: Submission package | ✅ DONE | This document |
| G14: Im2col decision | ⏭️ DEFERRED | Post-gate, Amdahl-limited |

## 8. Explicit Disclaimers

- ❌ NOT PRODUCTION_READY — requires G9-G11 regression gates
- ❌ OFFICIAL_RTF NOT AVAILABLE — external benchmark harness required
- ❌ NOT FULLY_OPTIMIZED — Im2col deferred
- ✅ INTEGRATION_CANDIDATE — CANN Flow + Vocoder
- ✅ STABLE — 1-hr continuous operation verified

## 9. SHA256SUMS

```
6913c972b30177fdde9700ead6863f96519c2fdf3400d25487127448cd9bcac0  llama-omni-cli (original)
e8afb107d27fae552117529a2d73f3806344a5310c2fa4ffa1b9df2a66e2c025  llama-omni-cli (clean build)
297f1abca5b7a2a862a7a1b2ae7510dffe2f580db72a6a62cf4111fb37f681b9  libggml-cann.so.0
1237a97ee081b8abebc47aa7dad565701e8f5f904cdc92f6723ac4281bbc0932  MiniCPM-o-4_5-Q4_K_M.gguf
```

## 10. Document Inventory

| Document | Status |
|----------|--------|
| `PHASE3_PERFORMANCE_RECONCILIATION.md` | COMPLETE |
| `ACL_GRAPH_CAPTURE_CORRECTNESS_AUDIT.md` | INITIAL |
| `PHASE3_EVIDENCE_MANIFEST.md` | COMPLETE |
| `P19_GRAPH_EXECUTION_REUSE.md` | COMPLETE |
| `GRAPH_CAPTURE_CACHE_AUDIT.md` | COMPLETE |
| `GRAPH_FUSION_FOUR_QUADRANT.md` | COMPLETE |
| `CHUNK_BUCKET_STATISTICS.md` | COMPLETE |
| `G5_BENCHMARK_HARNESS_AUDIT.md` | COMPLETE |
| `G6_DEMO_REPORT.md` | COMPLETE |
| `G7_30MIN_STABILITY_REPORT.md` | COMPLETE |
| `G8_1HR_STABILITY_REPORT.md` | COMPLETE |
| `G12_CLEAN_REPRODUCTION.md` | COMPLETE |
| `G13_SUBMISSION_PACKAGE.md` | THIS DOCUMENT |
