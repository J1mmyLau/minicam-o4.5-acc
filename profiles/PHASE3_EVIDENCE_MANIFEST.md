# Phase 3 Evidence Manifest

**Date:** 2026-07-29
**Tag candidate:** `cann-flow-vocoder-aclgraph-rtf0229-20260729`

---

## Artifacts

| Artifact | SHA256 | Notes |
|----------|--------|-------|
| `build/bin/llama-omni-cli` | `6913c972b30177fdde9700ead6863f96519c2fdf3400d25487127448cd9bcac0` | Dynamically linked |
| `build/bin/libggml-cann.so.0` | `297f1abca5b7a2a862a7a1b2ae7510dffe2f580db72a6a62cf4111fb37f681b9` | Contains graph capture code |
| Model GGUF | `1237a97ee081b8abebc47aa7dad565701e8f5f904cdc92f6723ac4281bbc0932` | MiniCPM-o-4_5-Q4_K_M.gguf |
| Encoder GGUF | `(model dir)` | `token2wav-gguf/encoder.gguf` |
| Flow GGUF | `(model dir)` | `token2wav-gguf/flow_matching.gguf` |
| Flow Extra GGUF | `(model dir)` | `token2wav-gguf/flow_extra.gguf` |
| Vocoder GGUF | `(model dir)` | `token2wav-gguf/hifigan2.gguf` |
| Prompt Cache GGUF | `(model dir)` | `token2wav-gguf/prompt_cache.gguf` |

---

## Canonical Command

```bash
OMNI_T2W_DEVICE=cann-flow-only \
OMNI_VOC_DEVICE=gpu \
OMNI_T2W_PROFILE=2 \
GGML_CANN_ACL_GRAPH=on \
GGML_CANN_GRAPH_MIN_NODES=100 \
./build/bin/llama-omni-cli \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
  --omni \
  --test tools/omni/assets/test_case/omni_test_case/omni_test_case_ 4
```

---

## Environment

| Component | Version/Value |
|-----------|---------------|
| CANN | 9.1.0-beta.1 |
| NPU | Ascend 910C (dav-2201) |
| Platform | Linux aarch64, openEuler 22.04 |
| Compiler | GCC (CANN-bundled) |
| CMake | USE_ACL_GRAPH=ON |
| Capture mode | ACL_MODEL_RI_CAPTURE_MODE_RELAXED |

---

## Documents

| Document | Path | Status |
|----------|------|--------|
| P19: Graph execution reuse | `P19_GRAPH_EXECUTION_REUSE.md` | COMPLETE |
| P20: Operator fusion (implicit) | In commits `9a7f5c2` | COMPLETE |
| Performance reconciliation | `PHASE3_PERFORMANCE_RECONCILIATION.md` | COMPLETE |
| Graph capture audit | `ACL_GRAPH_CAPTURE_CORRECTNESS_AUDIT.md` | INITIAL |
| Evidence manifest | `PHASE3_EVIDENCE_MANIFEST.md` | COMPLETE |
| Status | `STATUS.md` | Updated |
| Handoff | `HANDOFF.md` | Updated |

---

## Commit Chain

```
6154b85 docs: HANDOFF — Phase 3 final commit chain updated
9aa54f9 docs: Phase 3 final status — RTF 0.229 (-16.4%)
7e46faf docs: Phase 3 Rank 2 complete — ADD+NORM fusion, ~1ms gain
9a7f5c2 feat(P20): ADD+NORM (Add+LayerNorm) operator fusion
4a2cbcd feat(P19): CANN ACL graph capture — RELAXED mode + min_nodes filter
```

---

## Key Performance Numbers

| Metric | Value | Statistic | n |
|--------|-------|-----------|---|
| CPU Flow compute | 3,726 ms | mean | — |
| Phase 2 CANN Flow compute | 154.9 ms | mean | 65 |
| Phase 3 CANN Flow compute | **111.3 ms** | mean | 29 |
| Phase 2 RTF | 0.274 | competition | 65 |
| Phase 3 RTF | **0.229** | competition | 29 |
| Total speedup vs CPU | **18.4×** | RTF ratio | — |
| Phase 3 relative reduction | **16.4%** | (0.274-0.229)/0.274 | — |

---

## SHA256SUMS

```
6913c972b30177fdde9700ead6863f96519c2fdf3400d25487127448cd9bcac0  llama-omni-cli
297f1abca5b7a2a862a7a1b2ae7510dffe2f580db72a6a62cf4111fb37f681b9  libggml-cann.so.0
1237a97ee081b8abebc47aa7dad565701e8f5f904cdc92f6723ac4281bbc0932  MiniCPM-o-4_5-Q4_K_M.gguf
```
