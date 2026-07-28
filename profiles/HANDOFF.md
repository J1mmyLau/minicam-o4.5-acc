# Operator Profiling Mission — HANDOFF

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/operator-decode-speak`
**HEAD:** `111a48a` (P7-P8 docs: baseline report, candidate ranking, stack decision)
**Updated:** 2026-07-28 08:45 UTC

---

## Commit Chain

```
111a48a (HEAD -> perf/operator-decode-speak) docs(P7-P8): baseline report, candidate ranking, stack decision
7752c5f chore(P7-D): audit profiling commit — move raw msprof data out of git
8a5abcb docs(P4-P6): profiling reports, candidate proposal, P6 verification
b686120 feat(P6): RoPE F16 cast elimination — GGML_CANN_ROPE_FP16 gate
4822478 (tag: kv-cache-optin-candidate-20260728) fix(runner): add corrupt_cache_by_key for multi-entry
```

### Clean binary (no diagnostic code)

- **llama-omni-cli:** SHA `6913c972` (baseline build)
- **libggml-cann.so:** SHA `10592a58` (diagnostic code fully removed)
- All fusion diagnostic instrumentation cleaned up from `ggml-cann.cpp` and `aclnn_ops.cpp`

---

## Completed

| Phase | Description | Status | Evidence |
|-------|-------------|--------|----------|
| P0 | State recovery | PASS | KV cache freeze at kv-cache-optin-candidate-20260728 |
| P2 | Environment checks | PASS | ascendc-env-check, npu-arch: dav-2201, CANN 9.1 |
| P3 | Baseline measurement | **COMPLETE** | 15/15 clean, extreme LLM variance (2.3×-41×) |
| P4 | msprof profiling | PASS | `profiles/decode-speak/PROF_000001_20260728064555800/` |
| P4 | Profiling report | PASS | CANN kernel 0.164s (0.08% wall), wait 72.3s (36%) |
| P5 | Candidate proposal | PASS | `profiles/CANDIDATE_PROPOSAL.md` — RoPE F16 |
| P6 | Implementation | **COMMITTED** | b686120, +33/−19 in aclnn_ops.cpp |
| P6 | Smoke tests | PASS | OFF and ON both produce valid audio |
| P6 | Verification | PASS | `profiles/P6_VERIFICATION_REPORT.md` |
| P7-A | Baseline audit | PASS | `DECODE_TO_SPEAK_BASELINE.md` |
| P7-B | RoPE A/B | STOPPED | CONFIG INVALID — `-ngl 0` instead of production `-ngl 8` |
| P7-C | RoPE verdict | **REJECTED_WITH_EVIDENCE** | src0->type always f32, FP16 path NEVER hit |
| P7-D | Commit audit | PASS | 328 raw files removed, manifest created |
| P7 | Candidate ranking | PASS | `KERNEL_CANDIDATE_RANKING.md` |
| P8 | Stack decision | PASS | `OPERATOR_STACK_DECISION.md` |
| P9 | Top-1 implement (OP002) | **REJECTED** | ADD+RMSNorm: Talker LLM ops NOT on CANN |
| OP-002 | API audit | PASS | `ASCENDC_HIGH_LEVEL_API_AUDIT.md` |
| OP-002 | Graph pattern audit | PASS | `OP002_GRAPH_PATTERN_AUDIT.md` — 54 fusion points |
| OP-002 | Runtime graph diag | **COMPLETE** | `OP002_RUNTIME_GRAPH_DIAG.md` — definitive rejection |
| V0 CANN fusion | A/B complete | **DONE** | `V0_FUSION_VERDICT.md` — E2E NO_SIGNAL (r=0.999) |

---

## Key Technical Findings

### OP002 ADD+RMSNorm Fusion — DEFINITIVELY REJECTED

**Root cause:** `GGML_OP_OFFLOAD_MIN_BATCH=32` prevents element-wise ops (ne[1]=1) from CANN offload during decode.

- 1,132 CANN graph evaluations, **zero** 1152-dim (Talker LLM)
- Only 4096-dim flow model graphs reach CANN (~18 fusions/run)
- MIN_BATCH=1 crashes scheduler (CPU buffer tensors clash with CANN backend)
- Verdict: `NOT_REACHABLE_UNDER_CURRENT_OFFLOAD_POLICY`

### RoPE FP16 — CORRECTED STATUS

```
ROPE_FP16_CANN_LOCAL_PATH      = WEAK_POSITIVE  (+4.1%, but on Flow/vision ROPE, not Talker)
TALKER_DECODE_ROPE_OPTIMIZED   = NOT_PROVEN      (Talker RoPE ops not on CANN during decode)
TARGET_PATH_E2E_BENEFIT        = NOT_PROVEN
DEFAULT_ON                     = NO              (unconditionally)
```

### V0 CANN Fusion A/B

- 10 pairs, r(Δwav, Δwall) = 0.999 — wall time dominated by output length
- Pair 10 (matched wavs=6): Δ=+31ms (+0.06%) — within noise
- E2E wall-time A/B cannot detect sub-1% effects against 41× LLM variance

---

## In-Flight

| Item | Detail |
|------|--------|
| Nothing active | All experiments complete, no background runners |

---

## Document Inventory

| Document | Path |
|----------|------|
| Status | `profiles/STATUS.md` |
| Handoff (this) | `profiles/HANDOFF.md` |
| Baseline data | `profiles/baseline/` |
| Profiling report | `profiles/decode-speak/PROFILING_REPORT.md` |
| Candidate proposal | `profiles/CANDIDATE_PROPOSAL.md` |
| P6 verification | `profiles/P6_VERIFICATION_REPORT.md` |
| Decode-to-speak baseline | `docs/experiments/operator-optimization/DECODE_TO_SPEAK_BASELINE.md` |
| Kernel candidate ranking | `docs/experiments/operator-optimization/KERNEL_CANDIDATE_RANKING.md` |
| Stack decision | `docs/experiments/operator-optimization/OPERATOR_STACK_DECISION.md` |
| OP002 API audit | `docs/experiments/operator-optimization/ASCENDC_HIGH_LEVEL_API_AUDIT.md` |
| OP002 Graph pattern | `docs/experiments/operator-optimization/OP002_GRAPH_PATTERN_AUDIT.md` |
| OP002 Runtime diag | `docs/experiments/operator-optimization/OP002_RUNTIME_GRAPH_DIAG.md` |
| RoPE definitive verdict | `docs/experiments/operator-optimization/ROPE_FP16_DEFINITIVE_VERDICT.md` |
| V0 fusion verdict | `docs/experiments/operator-optimization/V0_FUSION_VERDICT.md` |
| CANNBot install audit | `docs/experiments/operator-optimization/CANNBOT_INSTALL_AUDIT.md` |
| V0 fusion A/B data | `profiles/cann_fusion_v0/pairs.csv` |
| RoPE A/B data | `profiles/rope_fp16_ab/pairs.csv` |

---

## Next After /compact — Candidate E: Runtime Overhead Reduction

### Constraint

The user explicitly directed: **profile first, implement only if ROI proven**. Do NOT modify code based solely on `aclrtSetDevice` call counts.

### V0: Profiling Audit (READ-ONLY)

Add low-overhead counters only (no behavior change) to measure:

| Metric | Target |
|--------|--------|
| `aclrtSetDevice` | call_count, total_time, avg/p95, thread_id, device, redundancy_rate (same-device consecutive calls) |
| `aclrtSynchronizeStream` | call_count, total_time, per-callsite breakdown |
| `aclrtMemcpy` / `aclrtMemcpyAsync` | call_count, total_time, direction |
| Queue wait gap | Host→NPU gap decomposition |
| Graph launch gap | Inter-graph idle time |

### Implementation Gates

1. **V0 counters only** — measure overhead, compute ROI
2. **V1 thread-local cache** — IF `aclrtSetDevice` redundancy > threshold AND cumulative host time significant
3. **Gate:** `GGML_CANN_CACHE_DEVICE_CONTEXT=0` (default OFF)
4. **If cumulative benefit < measurable** → REJECTED_WITH_EVIDENCE

### Key Code Location

- `ggml/src/ggml-cann/ggml-cann.cpp` — `ggml_backend_cann_graph_compute()`, CANN backend init, device context management

---

## Git Status

- Modified: `profiles/STATUS.md` (updated with OP002 verdict, RoPE correction, Candidate E plan)
- Modified: `profiles/rope_fp16_ab/pairs.csv` (RoPE A/B partial data)
- Untracked: Several new docs in `docs/experiments/operator-optimization/`
- Untracked: `profiles/cann_fusion_v0/` (V0 fusion A/B data)
- Untracked: `profiles/rope_fp16_ab/pair*` (individual run outputs)
- Untracked: `scripts/operator-profiling/run_cann_fusion_v0.sh`
- **No diagnostic code residual** — `ggml-cann.cpp` and `aclnn_ops.cpp` are clean
