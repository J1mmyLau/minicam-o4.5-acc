# CANN FLOW + VOCODER BREAKTHROUGH — EVIDENCE MANIFEST

**Date**: 2026-07-29
**Status**: CANDIDATE_FREEZE — RTF=0.274
**Tag**: cann-flow-vocoder-rtf027-20260729

---

## 1. Source

| Item | Value |
|------|-------|
| Branch | `perf/flow-chunk-rtf` |
| HEAD commit | `7f5f349bf0dcf57253252c4fb845c752227f9d16` |
| HEAD subject | docs(P15-C): CANN Flow msprof — Im2col 42%, kernel launch overhead 73% |
| Worktree | `/workspace/llama.cpp-omni-operator` |
| Origin | `git@github.com:ggml-org/llama.cpp.git` fork (proprietary omni extension) |

---

## 2. Binary

| Binary | SHA256 |
|--------|--------|
| `build/bin/llama-omni-cli` | `6913c972b30177fdde9700ead6863f96519c2fdf3400d25487127448cd9bcac0` |
| `build/bin/libggml-cann.so.0.13.1` | `47bb4386f791c9bb70d4a0c545f3134b6a98a1a2651f470b18092d66b5f13b96` |

---

## 3. Model

| Item | Value |
|------|-------|
| Path | `/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf` |
| SHA256 | `1237a97ee081b8abebc47aa7dad565701e8f5f904cdc92f6723ac4281bbc0932` |

---

## 4. Platform

| Item | Value |
|------|-------|
| NPU | Ascend 910C (Chip Name: Ascend910, dav-2201) |
| CANN | 9.1.0-beta.1 (V100R001C23SPC006B220) |
| Driver | 25.5.1 |
| ascendshal | 7.35.23 |
| prof_version | 2.0 |
| Host arch | aarch64 (Kunpeng 920) |
| OS | Linux 5.10.0-216.0.0.115.oe2203sp4 |

---

## 5. Canonical Command

```bash
OMNI_T2W_DEVICE=cann-flow-only \
OMNI_VOC_DEVICE=gpu \
OMNI_T2W_PROFILE=2 \
OMNI_T2W_PRINT_GRAPH=1 \
./build/bin/llama-omni-cli \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
  --mmproj /workspace/models/MiniCPM-o-4_5-gguf/mmproj-Q4_K_M.gguf \
  -ngl 8 \
  --test-start 0 \
  -tc 4
```

---

## 6. Environment Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| OMNI_T2W_DEVICE | cann-flow-only | Flow model → CANN (worker-thread deferred init) |
| OMNI_VOC_DEVICE | gpu | Vocoder → CANN (maps to ggml_backend_cann_init) |
| OMNI_T2W_PROFILE | 2 | Per-chunk `[timing]` lines |
| OMNI_T2W_PRINT_GRAPH | 1 | Dump ggml graph node count |

---

## 7. Raw Timing Data

| Dataset | Path | Chunks | Description |
|---------|------|--------|-------------|
| CPU Flow baseline | `/tmp/p14_graph_full.stderr` | 41 | CPU Flow + CPU Vocoder baseline |
| CANN Flow single | `/tmp/p15_cann_flow.stderr` | 60 | CANN Flow + CANN Vocoder (single batch) |
| CANN Flow stability B1 | `/tmp/p15_stability_batch1.stderr` | ~17 | Stability batch 1 |
| CANN Flow stability B2 | `/tmp/p15_stability_batch2.stderr` | ~23 | Stability batch 2 |
| CANN Flow stability B3 | `/tmp/p15_stability_batch3.stderr` | ~22 | Stability batch 3 |
| CANN Flow stability B4 | `/tmp/p15_stability_batch4.stderr` | ~30 | Stability batch 4 |
| CANN Flow stability B5 | `/tmp/p15_stability_batch5.stderr` | ~16 | Stability batch 5 |
| P7 CPU Vocoder | `/tmp/p7_cpu_batches/batch_*.stderr` | 77 | CPU Vocoder only |
| P7 CANN Vocoder | `/tmp/p7_cann_batches/batch_*.stderr` | 136 | CANN Vocoder only |

---

## 8. Correctness Evidence

| Check | Result |
|-------|--------|
| WAV validity (all 60 chunks) | 60/60 valid |
| Silence (zero samples) | 0/60 |
| Clipping (>0dBFS) | 0/60 |
| All 24kHz 16-bit mono | ✅ |

---

## 9. Competition Metric

```
Per-Chunk RTF = (flow_compute + vocoder_compute) / audio_duration_ms
              = (154.9 + 119.1) / 1000.0
              = 0.2740  (mean, steady-state, n=65)
              = 0.2737  (median, steady-state, n=65)
```

---

## 10. Document Inventory

| Document | Path | Purpose |
|----------|------|---------|
| Performance number reconciliation | `PERFORMANCE_NUMBER_RECONCILIATION.md` | Corrected 24.1×/2.92×/14.8× |
| CANN backend env semantics | `CANN_BACKEND_ENV_SEMANTICS.md` | `gpu` → CANN mapping |
| Flow CANN reachability audit | `FLOW_CANN_REACHABILITY_AUDIT.md` | "Flow=CANN" discrepancy |
| Flow profile percentage audit | `FLOW_PROFILE_PERCENTAGE_AUDIT.md` | Im2col 42% vs launch overhead 73% |
| Evidence manifest (this) | `EVIDENCE_MANIFEST.md` | SHA256, config, data paths |
| CANN Vocoder final verdict | `CANN_VOCODER_FINAL_VERDICT.md` | Vocoder INTEGRATION_CANDIDATE |
| P7 CANN vs CPU A/B | `P7_CANN_VS_CPU_PAIRED_AB.md` | Vocoder 2.92× speedup |
| P13 Flow architecture audit | `P13_FLOW_ARCHITECTURE_AUDIT.md` | Flow model topology |
| P14 Flow canonical baseline | `P14_FLOW_CANONICAL_BASELINE.md` | CPU Flow baseline |
| P15 CANN Flow discovery | `P15_FLOW_CANN_DISCOVERY.md` | THE BREAKTHROUGH |
| P15-A Correctness + stability | `P15A_CORRECTNESS_AND_STABILITY.md` | 60/60 valid, 5 stable batches |
| P15-C CANN Flow msprof | `P15C_CANN_FLOW_MSPROF.md` | Im2col 42%, kernel analysis |

---

## 11. Candidate Freeze

```
FREEZE_TAG: cann-flow-vocoder-rtf027-20260729
HEAD: 7f5f349bf0dcf57253252c4fb845c752227f9d16
BRANCH: perf/flow-chunk-rtf
STATUS: INTEGRATION_CANDIDATE
  - CANN_FLOW = INTEGRATION_CANDIDATE
  - CANN_VOCODER = INTEGRATION_CANDIDATE
  - COMBINED_INTERNAL_STEADY_RTF ≈ 0.274
  - PRODUCTION_READY: NO
  - OFFICIAL_RTF: NOT_AVAILABLE
  - GUARANTEED_15×: NO
```
