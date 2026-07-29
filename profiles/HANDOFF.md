# CANN Flow + Vocoder Optimization — HANDOFF

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/flow-chunk-rtf`
**HEAD:** `7f5f349` (P15-C: CANN Flow msprof — Im2col 42%, kernel launch overhead 73%)
**Updated:** 2026-07-29 14:00 UTC

---

## Commit Chain

```
7f5f349 (HEAD -> perf/flow-chunk-rtf) docs(P15-C): CANN Flow msprof — Im2col 42%, kernel launch overhead 73%
822d2e0 docs(status): COMPETITION METRIC RTF=0.27 — below realtime
fff6ab0 docs(P15-A,P15-B): CANN Flow correctness + stability verification
660fe91 docs(P15): Flow model CANN discovery — 21.9x speedup via cann-flow-only
edf0661 docs(P13,P14): Flow model architecture audit + canonical baseline
8a4de90 docs(P12-final): CANN_VOCODER = INTEGRATION_CANDIDATE
88d5c43 docs(P7-final): CANN vocoder paired A/B — 3.14x speedup, d=4.0, 100% win
5839200 docs(status): update NEXT_ACTION — EXIT vocoder-only optimization
be44a40 feat(P11): O2-A+O2-B graph+galloc reuse with OMNI_VOC_GRAPH_REUSE=1
9b677bc docs(P9): CANN vocoder candidate ranking — O2-A+O2-B selected as Top-1
```

---

## BREAKTHROUGH COMPLETE

### Key Numbers (Corrected)

| Component | Metric | CPU | CANN | Speedup |
|-----------|--------|-----|------|---------|
| Flow (token2mel) | Steady mean | 3,725.8ms | 154.9ms | **24.1×** |
| Vocoder | Steady mean | 348.2ms | 119.1ms | **2.92×** |
| Total T2W | Steady mean | 4,049.4ms | 274.0ms | **14.8×** |
| Per-Chunk RTF | Mean | 4.05 | **0.274** | — |

All numbers: steady-state (call ≥ 4), n=36 CPU, n=65 CANN (5 independent batches).

### How It Works

1. **Flow CANN**: `OMNI_T2W_DEVICE=cann-flow-only` defers Flow session init to worker thread, which creates its own CANN backend → avoids cross-thread CANN context invalidation.
2. **Vocoder CANN**: `OMNI_VOC_DEVICE=gpu` → maps to `ggml_backend_cann_init()` (no CUDA in build).
3. **Both CANN**: Total T2W 274ms, RTF=0.274 (well below 1.0 realtime).

### Why CANN Flow Wasn't Used Before

`omni.cpp:4971` explicitly overrides `device_token2mel = "cpu"` under CANN builds. Every prior experiment (P5, P7, P13-P14) ran Flow on CPU despite `GGML_USE_CANN` being compiled in.

---

## Completed (CURRENT SESSION)

| Phase | Description | Status | Evidence |
|-------|-------------|--------|----------|
| P0-P12 | CANN Vocoder optimization | INTEGRATION_CANDIDATE | `CANN_VOCODER_FINAL_VERDICT.md` |
| P13 | Flow architecture audit | COMPLETE | `P13_FLOW_ARCHITECTURE_AUDIT.md` |
| P14 | Flow canonical baseline | COMPLETE | `P14_FLOW_CANONICAL_BASELINE.md` |
| P15 | CANN Flow discovery | COMPLETE | `P15_FLOW_CANN_DISCOVERY.md` |
| P15-A | Correctness verification | COMPLETE | 60/60 wavs valid |
| P15-B | Stability verification | COMPLETE | 5 batches, 0 failures |
| P15-C | msprof profiling | COMPLETE | `P15C_CANN_FLOW_MSPROF.md` |
| Audit 1 | Number reconciliation | COMPLETE | `PERFORMANCE_NUMBER_RECONCILIATION.md` |
| Audit 2 | Path reachability | COMPLETE | `FLOW_CANN_REACHABILITY_AUDIT.md` |
| Audit 3 | Env semantics | COMPLETE | `CANN_BACKEND_ENV_SEMANTICS.md` |
| Audit 4 | Profile percentage | COMPLETE | `FLOW_PROFILE_PERCENTAGE_AUDIT.md` |
| Evidence | Manifest + SHA256SUMS | COMPLETE | `EVIDENCE_MANIFEST.md` |
| Checkpoint | STATUS/HANDOFF/AUDIT update | **IN PROGRESS** | This file |

---

## NOT DONE (Next Session)

| Task | Priority | Description |
|------|----------|-------------|
| Git tag | P0 | `git tag cann-flow-vocoder-rtf027-20260729` + commit all docs |
| Demo smoke | P1 | Basic "does it work end-to-end" test |
| First/warmup/steady/tail | P1 | Per-bucket characterization |
| 30min stability | P2 | Extended soak with CANN Flow+Vocoder |
| 1hr stability | P2 | Long-duration stability |
| KV cache regression | P2 | HIT/MISS/OFF with CANN Flow+Vocoder |
| Multi-prefix + T2W lifecycle | P2 | Production lifecycle validation |
| Internal audio correctness | P2 | Blind A/B listening test |
| Flow launch overhead | P3 | Graph execution reuse (#1 optimization target) |
| Im2col optimization | P3 | Fused conv1d or custom kernel |
| AscendC custom kernel | P3 | Only if launch overhead cannot be further reduced |

---

## Document Inventory

| Document | Path |
|----------|------|
| Status | `profiles/STATUS.md` |
| Handoff (this) | `profiles/HANDOFF.md` |
| Evidence manifest | `docs/experiments/operator-optimization/EVIDENCE_MANIFEST.md` |
| Number reconciliation | `docs/experiments/operator-optimization/PERFORMANCE_NUMBER_RECONCILIATION.md` |
| CANN backend env semantics | `docs/experiments/operator-optimization/CANN_BACKEND_ENV_SEMANTICS.md` |
| Flow CANN reachability audit | `docs/experiments/operator-optimization/FLOW_CANN_REACHABILITY_AUDIT.md` |
| Flow profile percentage audit | `docs/experiments/operator-optimization/FLOW_PROFILE_PERCENTAGE_AUDIT.md` |
| CANN Vocoder final verdict | `docs/experiments/operator-optimization/CANN_VOCODER_FINAL_VERDICT.md` |
| P7 CANN vs CPU A/B | `docs/experiments/operator-optimization/P7_CANN_VS_CPU_PAIRED_AB.md` |
| P13 Flow architecture audit | `docs/experiments/operator-optimization/P13_FLOW_ARCHITECTURE_AUDIT.md` |
| P14 Flow canonical baseline | `docs/experiments/operator-optimization/P14_FLOW_CANONICAL_BASELINE.md` |
| P15 CANN Flow discovery | `docs/experiments/operator-optimization/P15_FLOW_CANN_DISCOVERY.md` |
| P15-A Correctness + stability | `docs/experiments/operator-optimization/P15A_CORRECTNESS_AND_STABILITY.md` |
| P15-C CANN Flow msprof | `docs/experiments/operator-optimization/P15C_CANN_FLOW_MSPROF.md` |
| Chunk RTF baseline | `docs/experiments/operator-optimization/CHUNK_RTF_BASELINE.md` |
| Competition metric alignment | `docs/experiments/operator-optimization/COMPETITION_METRIC_ALIGNMENT.md` |
| E2E profile coverage audit | `docs/experiments/operator-optimization/E2E_PROFILE_COVERAGE_AUDIT.md` |
| Pipeline attribution method audit | `docs/experiments/operator-optimization/PIPELINE_ATTRIBUTION_METHOD_AUDIT.md` |
| P5 pipeline idle attribution | `docs/experiments/operator-optimization/P5_PIPELINE_IDLE_ATTRIBUTION.md` |
| P6 top-1 candidate selection | `docs/experiments/operator-optimization/P6_TOP1_CANDIDATE_SELECTION.md` |
| Talker CPU decode profile | `docs/experiments/operator-optimization/TALKER_CPU_DECODE_PROFILE.md` |
| Vocoder candidate ranking | `docs/experiments/operator-optimization/VOCODER_CANDIDATE_RANKING.md` |
| Vocoder optimization feasibility | `docs/experiments/operator-optimization/VOCODER_OPTIMIZATION_FEASIBILITY.md` |

---

## Git Status

- **Modified**: `profiles/STATUS.md`, `profiles/HANDOFF.md`, `docs/tracking/AUDIT.md`, `profiles/rope_fp16_ab/pairs.csv`, `tools/omni/omni.cpp`, `tools/omni/omni.h`
- **Untracked (new docs)**: 12 files in `docs/experiments/operator-optimization/`
- **Untracked (data)**: `profiles/cann_fusion_v0/`, `profiles/rope_fp16_ab/pair*`
- **Untracked (scripts)**: `scripts/operator-profiling/run_cann_fusion_v0.sh`
- **No active runner. NPU idle.**
