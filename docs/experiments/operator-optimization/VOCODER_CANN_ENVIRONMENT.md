# CANN Vocoder Environment — P0 Resource Check

**Date**: 2026-07-29
**Phase**: P0 — Field Recovery and Resource Check
**Status**: COMPLETE

---

## 1. Source & Binary

| Item | Value |
|------|-------|
| **Worktree** | `/workspace/llama.cpp-omni-operator` |
| **Branch** | `perf/operator-decode-speak` |
| **HEAD commit** | `f43155a` |
| **HEAD message** | `docs(runtime): reject SynchronizeStream optimization — Amdahl bound at 0.17%` |
| **Dirty files** | omni.cpp, omni.h, STATUS.md, HANDOFF.md, AUDIT.md, NEXT_ACTION.md, rope_fp16_ab/pairs.csv |
| **Untracked** | CHUNK_RTF_BASELINE.md, COMPETITION_METRIC_ALIGNMENT.md, E2E_PROFILE_COVERAGE_AUDIT.md, P5_PIPELINE_IDLE_ATTRIBUTION.md, P6_TOP1_CANDIDATE_SELECTION.md, PIPELINE_ATTRIBUTION_METHOD_AUDIT.md, TALKER_CPU_DECODE_PROFILE.md, VOCODER_CANDIDATE_RANKING.md, VOCODER_OPTIMIZATION_FEASIBILITY.md, profiles/cann_fusion_v0/, profiles/rope_fp16_ab/, scripts/operator-profiling/run_cann_fusion_v0.sh |

## 2. Binary Artifacts

| Item | SHA256 | Size |
|------|--------|------|
| `llama-omni-cli` | `6913c972b30177fdde9700ead6863f96519c2fdf3400d25487127448cd9bcac0` | 57K |
| `libggml-cann.so` | `c25bcbf274be472a106a00cbff8624b7553d8c9c2d97be0fc210c496dbd14c84` | 346K |

## 3. Model

| Item | Value |
|------|-------|
| **Path** | `/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf` |
| **SHA256** | `1237a97ee081b8abebc47aa7dad565701e8f5f904cdc92f6723ac4281bbc0932` |
| **Size** | 4.7 GB |
| **Architecture** | MiniCPM-o 4.5 (Qwen3 8.2B, 36 layers) |
| **Quantization** | Q4_K_M |

## 4. Platform

| Item | Value |
|------|-------|
| **Hardware** | Single Ascend 910C |
| **NPU** | Ascend910 ×2 (Chip 0: 0000:9D:00.0, Chip 1: 0000:9F:00.0) |
| **NPU Arch** | dav-2201 |
| **CANN version** | 9.1.0-beta.1 (V100R001C11B050) |
| **CANN path** | `/usr/local/Ascend/cann-9.1.0-beta.1` |
| **NPU idle** | Chip 0: 0% AICore, 3133/65536 MB HBM; Chip 1: 0% AICore, 2877/65536 MB HBM |
| **CPU** | aarch64, 640 cores (HiSilicon Kunpeng), 3000 MHz |
| **RAM** | 2.0 TiB total, 1.0 TiB free |
| **Kernel** | 5.10.0-216.0.0.115.oe2203sp4.aarch64 |
| **OS** | openEuler 22.04 SP4 |
| **GCC** | 11.4.0 |
| **CMake** | 3.22.1 |

## 5. Active Processes

| Check | Result |
|-------|--------|
| Active llama-omni | NONE |
| Active msprof | NONE |
| Active profiler | NONE |
| Active runner | NONE |
| NPU processes | NONE |

## 6. KV Production Branch

| Item | Value |
|------|-------|
| **Worktree** | `/workspace/llama.cpp-omni-kvcache-prod` |
| **Branch** | `perf/kv-cache-production-gates` |
| **HEAD** | `9a734c3` |
| **Status** | Clean (only untracked `cann-recipes-infer` and soak data) |
| **Integrity** | NOT MODIFIED by operator profiling |

## 7. Test Cases

| Item | Value |
|------|-------|
| **Path** | `/workspace/llama.cpp-omni-operator/tools/omni/assets/test_case/omni_test_case/` |
| **Count** | 9 cases (omni_test_case_0000 through 0008) |
| **Format** | .jpg + .wav pairs |

## 8. Production Candidate Configuration

```bash
# Talker: n_gpu_layers=8
# Token2Wav Flow: CANN (NPU)
# Vocoder: CPU (default)
# KV Cache: OPT_IN / DEFAULT_OFF
# Model: MiniCPM-o-4_5-Q4_K_M.gguf
```

## 9. Full Diagnostic Command (baseline reference)

```bash
OMNI_VOC_DEVICE=cpu \
  OMNI_PIPELINE_TRACE=1 \
  OMNI_E2E_PROFILE=1 \
  OMNI_E2E_PROFILE_DIR=/tmp/voc_cpu_baseline \
  ./build/bin/llama-omni-cli \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
  -ngl 8 \
  --test /workspace/llama.cpp-omni-operator/tools/omni/assets/test_case/omni_test_case/omni_test_case_ 4
```

---

**P0 Gate**: PASS — NPU idle, no active runners, KV production branch intact, environment documented.
