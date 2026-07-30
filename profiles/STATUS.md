# CANN Flow + Vocoder Optimization — STATUS

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/flow-chunk-rtf`
**HEAD:** `a14aee4`
**Final Tag:** `cann-flow-vocoder-aclgraph-kvcache-final-20260729`
**Updated:** 2026-07-30 03:30 UTC

---

## PROJECT PHASE: EVIDENCE RECONCILIATION + OFFICIAL BENCHMARK PREPARATION

Performance optimization is FROZEN. Current phase is evidence correction, terminology audit, and preparation for official benchmark harness.

---

## COMPETITION METRIC (llama.cpp-omni sub-track)

```
Primary metric: Per-Chunk RTF = (flow_compute + vocoder_compute) / audio_duration_ms

CPU baseline:                 RTF ≈ 4.21  (internal measurement)
Phase 2 (CANN Flow+Vocoder):  RTF ≈ 0.274
Phase 3 (+ACL Graph+Fusion):  RTF ≈ 0.229

Internal speedup vs CPU:  ~18.4×
```

**Important:** 0.229 is an internal measurement using internal timing. The official RTF score must be measured using the official competition harness and scripts. Internal RTF ≠ official score.

---

## CURRENT STATE

```
INTERNAL_PERFORMANCE_GATE       = PASS
INTERNAL_DEMO_GATE              = PASS
INTERNAL_STABILITY_GATE         = PASS
CLEAN_REPRODUCTION_GATE         = PASS
KV_CACHE_FUNCTIONAL_GATE        = PASS
MULTI_PREFIX_AND_CORRUPTION     = PASS
T2W_LIFECYCLE                   = PASS (confirmed via F1: 0 unexpected_no_audio)

DAILY_OMNI_GATE                 = PENDING (harness not yet available)
TTS_SEED_GATE                   = PENDING (harness not yet available)
VIDEO_MME_GATE                  = PENDING (harness not yet available)
OFFICIAL_RTF_GATE               = PENDING (official timing script needed)

OFFICIAL_BENCHMARK_GATE         = BLOCKED_EXTERNAL
OFFICIAL_SUBMISSION_PASS        = NO
FINAL_SUBMISSION_CANDIDATE      = NO
IM2COL_OPTIMIZATION             = DEFERRED

CURRENT_HEAD                    = a14aee4
CURRENT_TAG                     = cann-flow-vocoder-aclgraph-kvcache-final-20260729
CURRENT_BINARY_SHA256           = 6913c972b30177fdde9700ead6863f96519c2fdf3400d25487127448cd9bcac0
ACTIVE_RUNNER                   = F2 matched-pair test (PID 1082503)
ACTIVE_RUN_DIR                  = /workspace/llama.cpp-omni-operator/profiles/f2_matched_pairs
```

---

## Gate Results (Corrected)

Total gates: 14

| # | Gate | Status | Key Result |
|---|------|--------|------------|
| G1 | Perf consistency | ✅ PASS | Numbers self-consistent |
| G2 | Graph cache audit | ✅ PASS | 12-component cache key verified |
| G3 | 4-quadrant A/B | ✅ PASS | Q4(ON,ON): RTF=0.245 |
| G4 | Chunk buckets | ✅ PASS | Steady RTF=0.224 (call≥4) |
| G5 | Benchmark harness | ⏭️ BLOCKED | External harnesses unavailable |
| G6 | Demo validation | ✅ PASS | 9 cases, 0 CANN errors |
| G7 | 30-min stability | ✅ PASS | 37 iters, 661 WAVs, 0 errors |
| G8 | 1-hr stability | ✅ PASS | 66 iters, 1368 WAVs, 0 errors |
| G9 | KV cache regression | ✅ PASS | 28/30 HIT, 0 genuine misses (F3) |
| G10 | Multi-prefix | ✅ PASS | 3 keys isolated, corruption detected |
| G11 | T2W lifecycle | ✅ PASS | 154 runs, 0 unexpected_no_audio (F1) |
| G12 | Clean reproduction | ✅ PASS | RTF 0.236 vs 0.245 (±3.6%) |
| G13 | Submission package | ✅ DONE | Pending official benchmark |
| G14 | Im2col decision | ⏭️ DEFERRED | Amdahl-limited, benefit < 3% |

```
Confirmed PASS:     12 (G1-G4, G6-G13)
BLOCKED (external):  1 (G5)
DEFERRED:            1 (G14)
                    ──
Total:              14
```

---

## Evidence Reconciliation Status

| Task | Status | Output |
|------|--------|--------|
| F0: Gate count reconciliation | ✅ DONE | `F0_GATE_COUNT_RECONCILIATION.md` |
| F1: G11 non-audio classification | ✅ DONE | `F1_G11_NON_AUDIO_CLASSIFICATION.md` |
| F2: KV cache matched-pair benefit | 🔄 RUNNING | 30 matched OFF/HIT pairs |
| F3: G9 non-HIT classification | ✅ DONE | `F3_KV_CACHE_NON_HIT_CLASSIFICATION.md` |
| F4: RTF same-metric comparison | 🔄 RUNNING | Part of F2 paired test |
| F5: Terminology correction | 🔄 IN PROGRESS | This file |
| F6: Tag and HEAD verification | ✅ DONE | tag a14aee4 = HEAD |
| F7: Submission package update | ⏭️ PENDING | After F2/F4 complete |

---

## Official Competition Benchmarks (Race Track 1 — llama.cpp-omni)

Per official rules published 2026-07-30:

| Benchmark | Status | Requirement |
|-----------|--------|-------------|
| Daily-Omni | ⏭️ PENDING | Accuracy vs baseline ≤ 2pp drop |
| TTS-Seed | ⏭️ PENDING | Accuracy vs baseline ≤ 2pp drop |
| Video-MME | ⏭️ PENDING | Accuracy vs baseline ≤ 2pp drop |
| Official RTF | ⏭️ PENDING | Must use official timing scripts |

**Priority:** Get official harness → run baseline → run candidate → verify accuracy → submit.

---

## Terminology Policy (F5)

### Permitted
- INTERNAL_INTEGRATION_GATES_COMPLETE
- KV_CACHE_OPT_IN_READY / DEFAULT_OFF
- INTERNAL_PERFORMANCE_GATE_PASS
- DEMO_GATE_PASS
- STABILITY_GATE_PASS
- CLEAN_REPRODUCTION_PASS
- OFFICIAL_BENCHMARK_BLOCKED_EXTERNAL
- IM2COL_DEFERRED

### Forbidden (without corresponding evidence)
- ALL_PRODUCTION_GATES_CLOSED
- PRODUCTION_READY
- OFFICIAL_SUBMISSION_PASS
- OFFICIAL_SCORE
- PRESERVED_EXACTLY_59_PERCENT

---

## Remaining

1. ~~F0: Gate count~~ → DONE
2. ~~F1: G11 classification~~ → DONE
3. ~~F3: G9 non-HIT classification~~ → DONE
4. 🔄 F2/F4: Matched-pair RTF + KV cache benefit (running)
5. F5: Terminology audit complete → this file
6. F7: Update submission package with corrected language
7. P0: Obtain official Daily-Omni/TTS-Seed/Video-MME harness
8. P1: Run official baseline + candidate on all 3 benchmarks
9. P2: Verify accuracy ≤ 2pp drop on each
10. P3: Measure RTF with official scripts
11. P4: Complete submission package

---

## Stop Conditions

Only stop on: user request, missing credentials, hardware failure, git corruption, or all evidence + official benchmarks complete.
