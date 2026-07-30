# F6: Tag and Artifact Verification

**Date:** 2026-07-30

---

## Tag Verification

```
Tag:  cann-flow-vocoder-aclgraph-kvcache-final-20260729
HEAD: a14aee4ce5d9e29ac171def2b31f00d75031dd99
Tag points to: a14aee4ce5d9e29ac171def2b31f00d75031dd99
Match: ✅ YES — tag == HEAD
```

## Tag Chain

```
cann-flow-vocoder-rtf027-20260729               (Phase 2 freeze)
cann-flow-vocoder-aclgraph-rtf0229-20260729      (Phase 3 freeze)
cann-flow-vocoder-aclgraph-kvcache-final-20260729 (Internal integration gates complete)
```

## Artifact SHA256

```
6913c972b30177fdde9700ead6863f96519c2fdf3400d25487127448cd9bcac0  llama-omni-cli
297f1abca5b7a2a862a7a1b2ae7510dffe2f580db72a6a62cf4111fb37f681b9  libggml-cann.so.0
1237a97ee081b8abebc47aa7dad565701e8f5f904cdc92f6723ac4281bbc0932  MiniCPM-o-4_5-Q4_K_M.gguf
```

## Git State

```
Branch:   perf/flow-chunk-rtf
HEAD:     a14aee4
Status:   Modified files (uncommitted):
          - profiles/rope_fp16_ab/pairs.csv (experimental data)
          - tools/omni/omni.cpp (pipeline trace infrastructure)
          - tools/omni/omni.h (pipeline trace infrastructure)
          Untracked: experiment docs, profiling data, rope_fp16 results
```

## Canonical Command

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

Note: `OMNI_VOC_DEVICE=gpu` maps to CANN backend in the Ascend build, not NVIDIA CUDA.
