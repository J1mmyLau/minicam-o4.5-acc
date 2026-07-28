# Operator Profiling Mission — HANDOFF

**Worktree:** `/workspace/llama.cpp-omni-operator`  
**Branch:** `perf/operator-decode-speak`  
**HEAD:** `b686120` (P6: RoPE F16 cast elimination)  
**Updated:** 2026-07-28 07:15 UTC

---

## Commit Chain

```
b686120 (HEAD -> perf/operator-decode-speak) feat(P6): RoPE F16 cast elimination — GGML_CANN_ROPE_FP16 gate
4822478 (tag: kv-cache-optin-candidate-20260728) fix(runner): add corrupt_cache_by_key for multi-entry
```

## Completed

| Phase | Description | Status | Evidence |
|-------|-------------|--------|----------|
| P2 | Environment checks | PASS | ascendc-env-check, npu-arch: dav-2201 |
| P3 | Binary build | PASS | llama-omni-cli 6913c972b30177fd |
| P3 | Baseline measurement | RUNNING | 12/15 iter done, tc=7 in progress |
| P4 | msprof profiling | PASS | `profiles/decode-speak/PROF_000001_20260728064555800/` |
| P4 | Profiling report | PASS | `profiles/decode-speak/PROFILING_REPORT.md` |
| P5 | Candidate proposal | PASS | `profiles/CANDIDATE_PROPOSAL.md` — RoPE F16 |
| P6 | Implementation | **COMMITTED** | b686120, +33/−19 in aclnn_ops.cpp |
| P6 | Smoke tests | PASS | OFF and ON both produce valid audio |
| P6 | msprof A/B | PASS | `profiles/decode-speak/rope_fp16/` |
| P6 | Verification report | PASS | `profiles/P6_VERIFICATION_REPORT.md` |

## P6 Implementation Details

- **File:** `ggml/src/ggml-cann/aclnn_ops.cpp` → `ggml_cann_rope()`
- **Gate:** `GGML_CANN_ROPE_FP16` env var, parse_bool, default OFF
- **Mechanism:** Skip F16→F32→F16 round-trip; pass F16 tensors directly to `aclnnRotaryPositionEmbedding`
- **5 code paths modified:** Cast skip, head tensors, RoPE execution, has_tail copy-back, tail copy
- **Fallback:** When OFF or src0 not F16 → identical to original path

## In-Flight

| Item | Detail |
|------|--------|
| Baseline runner | PID 2889536, `profiles/baseline/run_baseline.sh`, tc=7 (LONG), 12/15 done |

## Document Inventory

| Document | Path |
|----------|------|
| Status | `/workspace/llama.cpp-omni-operator/profiles/STATUS.md` |
| Profiling report | `/workspace/llama.cpp-omni-operator/profiles/decode-speak/PROFILING_REPORT.md` |
| Candidate proposal | `/workspace/llama.cpp-omni-operator/profiles/CANDIDATE_PROPOSAL.md` |
| P6 verification | `/workspace/llama.cpp-omni-operator/profiles/P6_VERIFICATION_REPORT.md` |
| Baseline data | `/workspace/llama.cpp-omni-operator/profiles/baseline/` |
| msprof baseline | `/workspace/llama.cpp-omni-operator/profiles/decode-speak/PROF_000001_20260728064555800/` |
| msprof F16 ON | `/workspace/llama.cpp-omni-operator/profiles/decode-speak/rope_fp16/PROF_000001_20260728070559546/` |
| Audit log | `/workspace/llama.cpp-omni-kvcache-prod/docs/tracking/AUDIT.md` |

## Next for Continuation

1. Wait for P3 baseline to complete (tc=7 × 5 iter)
2. Generate baseline report from collected data
3. Evaluate P7: default-ON recommendation based on A/B evidence
4. P8-P15: Remaining operator profiling phases per mission spec
