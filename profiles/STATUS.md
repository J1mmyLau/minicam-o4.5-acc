# Operator Profiling Mission — STATUS

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/operator-decode-speak`
**HEAD:** `111a48a` (P7-P8 docs)
**Updated:** 2026-07-28 07:45 UTC

---

## Phase Status

| Gate | Status | Commit | Key Finding |
|------|--------|--------|-------------|
| P0: State recovery | PASS | 4822478 | KV cache freeze at kv-cache-optin-candidate-20260728 |
| P2: Environment | PASS | — | dav-2201, CANN 9.1, TileLang NOT_RUNNABLE, Triton NOT_REGISTERED |
| P3: Baseline | **COMPLETE** | 111a48a | 15/15 clean. Extreme variance (2.3×-41×) due to LLM non-determinism |
| P4: Profiling | PASS | 8a5abcb | msprof: CANN kernel 0.164s (0.08% wall), wait 72.3s (36%) |
| P5: Candidate | PASS | 8a5abcb | Top-1 proposed: RoPE F16 Cast Elimination |
| P6: Implementation | PASS | b686120 | RoPE F16 gate. Kernel +4.1%. Cast hypothesis DISPROVEN. |
| P7-A: Baseline audit | PASS | 111a48a | DECODE_TO_SPEAK_BASELINE.md |
| P7-B: RoPE A/B | STOPPED | — | CONFIGURATION INVALID — `-ngl 0` instead of production `-ngl 8` |
| P7-C: RoPE verdict | **REJECTED_WITH_EVIDENCE** | — | src0->type always f32, FP16 path NEVER hit. See ROPE_FP16_DEFINITIVE_VERDICT.md |
| P7-D: Commit audit | PASS | 7752c5f | 328 raw files removed, manifest created |
| P7: Candidate ranking | PASS | 111a48a | KERNEL_CANDIDATE_RANKING.md (needs re-audit with ngl=8) |
| P8: Stack decision | PASS | 111a48a | OPERATOR_STACK_DECISION.md |
| P9: Top-1 implement | **REJECTED** | 10592a58 | ADD+RMSNorm fusion: Talker LLM ops NOT on CANN (op_offload_min_batch=32 > decode ne[1]=1). V0 fusion works for flow model only. |
| P10: Candidate E | **REJECTED** | 035839b | E1 (SetDevice): 95.6% TLS guard already. E2 (Sync): 33ms total (0.17%), Amdahl bound. |
| P11: Next candidate | **NEXT** | — | H2D aggregation, D2H readback, pipeline idle decomposition |
| OP-002 API audit | PASS | 111a48a | ASCENDC_HIGH_LEVEL_API_AUDIT.md |
| OP-002 Graph pattern | PASS | 111a48a | OP002_GRAPH_PATTERN_AUDIT.md — 54 fusion points confirmed at source level |
| OP-002 Runtime diag | **COMPLETE** | 10592a58 | OP002_RUNTIME_GRAPH_DIAG.md — NOT_REACHABLE_UNDER_CURRENT_OFFLOAD_POLICY |
| RoPE definitive verdict | PASS | 111a48a | ROPE_FP16_DEFINITIVE_VERDICT.md — F32 dtype + CANN unreachability |
| V0 CANN fusion A/B | **DONE** | 10592a58 | V0_FUSION_VERDICT.md — E2E NO_SIGNAL (r=0.999 with Δwav) |
| E1: SetDevice cache | **REJECTED** | 035839b | CANDIDATE_E1_SETDEVICE_VERDICT.md — TLS guard 95.6% hit rate |
| E2: Sync reduction | **REJECTED** | pending | CANDIDATE_E2_SYNC_VERDICT.md — 33ms total (0.17%), DUPLICATE=74.3% but only 6.3ms |

## P6 / RoPE Corrected Status

```text
ROPE_FP16_CANN_LOCAL_PATH      = WEAK_POSITIVE  (+4.1%, but on Flow/vision ROPE, not Talker)
TALKER_DECODE_ROPE_OPTIMIZED   = NOT_PROVEN      (Talker RoPE ops not on CANN during decode)
TARGET_PATH_E2E_BENEFIT        = NOT_PROVEN
DEFAULT_ON                     = NO              (unconditionally)
```

## Candidate E — REJECTED (both sub-candidates)

### E1: aclrtSetDevice Caching → `REJECTED_WITH_EVIDENCE`
- `ggml_cann_set_device`: 9,296 requests, 408 actual (95.6% TLS guard hit rate)
- Remaining 6,150 calls from ACLNN/CAN internal (not modifiable)
- See: `CANDIDATE_E1_SETDEVICE_VERDICT.md`

### E2: aclrtSynchronizeStream Reduction → `REJECTED_BY_AMDAHL_BOUND`
- 3,861 syncs, 74.3% DUPLICATE_NO_WORK
- Total sync time: 32.98ms (0.17% of request wall)
- avg DUPLICATE: 2.2μs, avg MANDATORY: 26.9μs
- Even 100% duplicate elimination saves only 6.3ms (0.03%)
- See: `CANDIDATE_E2_SYNC_VERDICT.md`

## Next Candidate (P11)

**Data Movement & Pipeline Auditing:**

1. H2D small-transfer aggregation (2,293 H2D transfers per request)
2. D2H readback frequency (928 D2H transfers)
3. Graph launch gap analysis (inter-graph idle time)
4. Pipeline idle decomposition (where does the 72.3s Wait actually come from?)
5. Pinned host memory for transfer buffers
