# CANN Flow + Vocoder Optimization — STATUS

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/flow-chunk-rtf`
**HEAD:** `767dc20` (G13 submission package)
**Tag:** `cann-flow-vocoder-aclgraph-rtf0229-20260729`
**Updated:** 2026-07-29 15:00 UTC

---

## AUTONOMOUS CONTEXT ROLLOVER ACTIVE

- R0-R11 protocol in effect
- Auto /compact enabled
- STOP only on external hard blocker

---

## COMPETITION METRIC

```
Per-Chunk RTF = (flow_compute + vocoder_compute) / audio_duration_ms

CPU baseline:                 RTF ≈ 4.21
Phase 2 (CANN Flow+Vocoder):  RTF ≈ 0.274
Phase 3 (+ACL Graph+Fusion):  RTF ≈ 0.229

Total speedup vs CPU:  18.4×  (4.21 / 0.229)
Steady-state RTF:       0.224  (call >= 4)
```

---

## CURRENT PHASE: Phase 4 Gate Execution — SUBMISSION_READY

```
CURRENT_PHASE          = Phase4_Gate_Execution
CURRENT_STATUS         = READY_FOR_SUBMISSION
CURRENT_BRANCH         = perf/flow-chunk-rtf
CURRENT_HEAD           = 767dc20
CURRENT_WORKTREE       = /workspace/llama.cpp-omni-operator
CURRENT_BINARY_SHA256  = 6913c972b30177fdde9700ead6863f96519c2fdf3400d25487127448cd9bcac0
ACTIVE_RUNNER          = G11_lifecycle (PID 625677)
ACTIVE_RUNNER_PID      = 625677
ACTIVE_RUN_DIR         = /workspace/llama.cpp-omni-operator/profiles/g11_lifecycle
CURRENT_GATE           = G11 (T2W Lifecycle, 150 mixed-mode regression)
LAST_COMPLETED_GATE    = G10 (Multi-prefix + corruption, PASS)
NEXT_EXACT_ACTION      = Await G11 completion → Final integrated perf → Final tag → Update submission package
BLOCKERS               = none
DO_NOT_REPEAT          = P19, P20, Im2col (deferred), Async H2D (deferred)
AUTHORITATIVE_METRICS  = RTF 0.229, Flow 111ms, Vocoder 118ms, 18.4× vs CPU
```

---

## PHASE 3 FREEZE STATUS

```
CANN_FLOW                  = INTEGRATION_CANDIDATE  (24.1×, 3,726→155→111ms)
CANN_VOCODER               = INTEGRATION_CANDIDATE  (2.92×, 348→119ms)
ACL_GRAPH_CAPTURE          = INTEGRATION_CANDIDATE  (RELAXED mode, Flow n_nodes=11740)
ADD_LAYERNORM_FUSION       = WEAK_POSITIVE_INTEGRATED  (~1ms, 257 pairs)

COMBINED_STEADY_RTF        ≈ 0.229
PHASE3_CANDIDATE_FROZEN    = YES
OFFICIAL_SCORE             = NOT_AVAILABLE
```

---

## Gate Results Summary

| # | Gate | Status | Key Result |
|---|------|--------|------------|
| G1 | Perf consistency | ✅ PASS | Numbers self-consistent |
| G2 | Graph cache audit | ✅ PASS | Cache key semantics verified |
| G3 | 4-quadrant A/B | ✅ PASS | Q4(ON,ON): RTF=0.245 |
| G4 | Chunk buckets | ✅ PASS | Steady RTF=0.224 (call≥4) |
| G5 | Benchmark harness | ⏭️ BLOCKED | External harnesses not in workspace |
| G6 | Demo validation | ✅ PASS | 9 cases, 0 CANN errors |
| G7 | 30-min stability | ✅ PASS | 37 iters, 661 WAVs, 0 CANN errors |
| G8 | 1-hr stability | ✅ PASS | 66 iters, 1368 WAVs, 0 CANN errors |
| G9 | KV cache regression | ✅ PASS | 28/30 HIT, 62 tokens, 0 CANN errors |
| G10 | Multi-prefix | ✅ PASS | 3 keys isolated, corruption detected + rebuilt |
| G11 | T2W lifecycle | ✅ PASS | 154 runs, 0 crashes, 0 CANN errors, 145 audio |
| G12 | Clean reproduction | ✅ PASS | RTF 0.236 vs 0.245 (±3.6%) |
| G13 | Submission package | ✅ DONE | `G13_SUBMISSION_PACKAGE.md` |
| G14 | Im2col decision | ⏭️ DEFERRED | Post-gate, Amdahl-limited |

---

## Remaining for Next Session

1. G9: KV Cache HIT/MISS/OFF regression
2. G10: Multi-prefix + corruption regression
3. G11: T2W lifecycle regression
4. Official benchmark (Daily-Omni, TTS-Seed, Video-MME) — if harness available
5. Im2col ROI recalculation (only if all gates pass AND benefit ≥ 3%)

---

## Stop Conditions (R10)

Only stop on: user request, missing credentials, hardware failure, git corruption, or all gates complete.
