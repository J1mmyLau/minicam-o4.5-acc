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
| P10: Candidate E | **NEXT** | — | Runtime Overhead Reduction — profiling audit first, implement only if ROI proven |
| OP-002 API audit | PASS | 111a48a | ASCENDC_HIGH_LEVEL_API_AUDIT.md |
| OP-002 Graph pattern | PASS | 111a48a | OP002_GRAPH_PATTERN_AUDIT.md — 54 fusion points confirmed at source level |
| OP-002 Runtime diag | **COMPLETE** | 10592a58 | OP002_RUNTIME_GRAPH_DIAG.md — NOT_REACHABLE_UNDER_CURRENT_OFFLOAD_POLICY |
| RoPE definitive verdict | PASS | 111a48a | ROPE_FP16_DEFINITIVE_VERDICT.md — F32 dtype + CANN unreachability |
| V0 CANN fusion A/B | **DONE** | 10592a58 | V0_FUSION_VERDICT.md — E2E NO_SIGNAL (r=0.999 with Δwav) |

## P6 / RoPE Corrected Status

```text
ROPE_FP16_CANN_LOCAL_PATH      = WEAK_POSITIVE  (+4.1%, but on Flow/vision ROPE, not Talker)
TALKER_DECODE_ROPE_OPTIMIZED   = NOT_PROVEN      (Talker RoPE ops not on CANN during decode)
TARGET_PATH_E2E_BENEFIT        = NOT_PROVEN
DEFAULT_ON                     = NO              (unconditionally)
```

## Next Candidate

**Candidate E: Runtime Overhead Reduction**

Targets: `aclrtSetDevice` (6,559 calls), `aclrtSynchronizeStream`, `aclrtMemcpy`, Host/NPU wait gap.

Methodology:
1. Profiling audit FIRST (call count, total time, per-site breakdown, redundancy rate)
2. Implement only if cumulative Host time is significant AND reducible
3. V0: low-overhead counters only (no behavior change)
4. V1: thread-local device cache if ROI > threshold
5. Gate: GGML_CANN_CACHE_DEVICE_CONTEXT (default OFF)
6. If cumulative benefit < measurable → REJECTED_WITH_EVIDENCE
