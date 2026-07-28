# Operator Profiling Mission — STATUS

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/operator-decode-speak`
**HEAD:** `b686120` (P6: RoPE F16 cast elimination)

---

## Phase Status

| Gate | Status | Commit | Notes |
|------|--------|--------|-------|
| P0: State recovery | PASS | 4822478 | KV cache freeze at kv-cache-optin-candidate-20260728 |
| P2: Environment | PASS | — | ascendc-env-check, npu-arch: dav-2201, 910C |
| P3: Baseline | RUNNING | — | tc=7 still running (LONG, ~9min per iter) |
| P4: Profiling | PASS | — | msprof trace collected (65,865 tasks); PROFILING_REPORT.md |
| P5: Candidate | PASS | — | CANDIDATE_PROPOSAL.md: RoPE F16 Cast Elimination |
| P6: Implementation | **COMPLETE** | b686120 | GGML_CANN_ROPE_FP16 gate, default OFF |

## P6 Key Results

- Implementation: `ggml_cann_rope()` in aclnn_ops.cpp (+33/-19)
- Smoke: OFF ✓, ON ✓ (no crashes, valid audio)
- msprof A/B: RotaryPositionEmbedding 5.57→5.34 μs (−4.1%)
- Gate verified: default OFF, ON via GGML_CANN_ROPE_FP16=1
- Fallback preserved: when OFF or non-F16 src0, identical to original path

## Next

1. Wait for P3 baseline to finish → write baseline report
2. P7: Evaluate if A/B warrants default-ON recommendation
3. P8-P15: Remaining operator profiling phases (if applicable)

## In-flight

- Baseline runner: PID 2889536, running tc=7 (LONG), 12/15 complete
- Last output: tc7_r2 completed at 07:14
