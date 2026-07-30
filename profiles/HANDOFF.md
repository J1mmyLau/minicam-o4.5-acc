# CANN Flow + Vocoder Optimization — HANDOFF

**Worktree:** `/workspace/llama.cpp-omni-operator`
**Branch:** `perf/flow-chunk-rtf`
**HEAD:** `ee22811`
**Final Tag:** `cann-flow-vocoder-aclgraph-kvcache-final-20260729`
**Updated:** 2026-07-30 09:40 UTC

---

## State: RUNTIME CANDIDATE FINALIZATION — 3/10 GATES PASS — 7 GATES PENDING

```
╔══════════════════════════════════════════════════════════════╗
║  FP16 CANN T2W INTERNAL RTF (uniform per-chunk mean, corrected) ║
║  FLOW_RTF    = 0.115   (mean, ACL_GRAPH=on)                  ║
║  VOCODER_RTF = 0.119   (mean, essentially unchanged)         ║
║  TOTAL_RTF   = 0.234   (optimized candidate)                 ║
║  BASELINE    = 0.264   (CANN framework: Graph OFF)           ║
║  FLOW Δ      = -21.1%  (ACL graph capture benefit)           ║
║  TOTAL Δ     = -11.4%  (candidate vs CANN framework baseline)║
╚══════════════════════════════════════════════════════════════╝

# BLOCKING GATES (corrected 2026-07-30):
R15_CANN_REINIT_MIN_REPRO              = PASS
R15_ACL_INIT_GUARD                     = IMPLEMENTED
R11_CANN_FREE_FIX                      = IMPLEMENTED_NOT_FULLY_REGRESSION_TESTED
R6_CANN_CONTEXT                        = PROVISIONAL_PASS
R10_VIDEO_ADAPTER                      = MP4_DEMUX_SINGLE_E2E_PASS

AUDIO_SERIAL_LOOP_30                   = PASS  (30/30 audio, 0 failures)
MULTIMODAL_BENCHMARK_LOOP              = PENDING
FP16_CANDIDATE_REFREEZE                = REQUIRED

# READINESS:
FP16_INTERNAL_PERFORMANCE_AB           = PROVISIONAL_PASS
FP16_SERVER_BENCHMARK_READINESS        = PROVISIONAL
FP16_OFFICIAL_BENCHMARK_READY          = NO
FP16_OFFICIAL_RTF                      = PENDING

# Q4_K_M Internal (NOT competition)
INTERNAL_PERFORMANCE_GATE         = PASS (Q4_K_M — QUANTIZED_WEIGHT_INTERNAL_ONLY)
INTERNAL_DEMO_GATE                = PASS (Q4_K_M)
INTERNAL_STABILITY_GATE           = PASS (Q4_K_M)
CLEAN_REPRODUCTION_GATE           = PASS (Q4_K_M)
KV_CACHE_FUNCTIONAL_GATE          = PASS (Q4_K_M)
MULTI_PREFIX_AND_CORRUPTION       = PASS (Q4_K_M)
T2W_LIFECYCLE                     = PASS (Q4_K_M)
```

---

## Critical Findings

### 1. CANN T2W Env Var Contract (R1-R9)

**Root cause of prior "CPU-only" finding: MISSING environment variables.**

```bash
# REQUIRED for CANN Flow/Vocoder on Ascend 910C:
export OMNI_T2W_DEVICE=cann-flow-only   # Flow Matching on CANN (deferred worker init)
export OMNI_VOC_DEVICE=gpu              # Vocoder on CANN (maps to CANN0)

# WITHOUT: Flow/Vocoder both CPU → RTF ~3.97 (CPU fallback diagnostic)
# WITH:    Flow=CANN0, Vocoder=CANN0 → RTF 0.234 (optimized candidate)
```

### 2. Weight Format Contract

```
COMPANY:  FP16 (16 GB) — required for competition, full CANN acceleration
INTERNAL: Q4_K_M (4.7 GB) — QUANTIZED_WEIGHT_INTERNAL_ONLY, deprecated for competition
```

### 3. Three-Tier Baseline (Corrected 2026-07-30)

| Tier | RTF | Composition |
|------|-----|------------|
| **CPU_FALLBACK_DIAGNOSTIC** | ~3.97 | No CANN env vars; Flow+Vocoder CPU; Q4_K_M; prior measurement |
| **FP16_CANN_FRAMEWORK_BASELINE** | **0.264** | CANN Flow ON, CANN Vocoder ON, Graph OFF, Fusion OFF; FP16 |
| **FP16_OPTIMIZED_CANDIDATE** | **0.234** | CANN Flow ON, CANN Vocoder ON, Graph ON, Fusion ON; FP16 |

```
INTERNAL_CPU_FALLBACK_TO_CANDIDATE_SPEEDUP ≈ 17.0x
  (NOT official competition speedup — internal diagnostic only)
```

### 4. Stats Reconciliation (2026-07-30)

Prior report mixed mean (Flow), p50 (Vocoder), and profile-aggregate (Total) RTF definitions. All values now use uniform per-chunk mean. See `FP16_RTF_METRIC_RECONCILIATION.md`.

Serial overhead < 0.03ms — Flow and Vocoder are purely sequential, no overlap.

### 5. Server CANN T2W (R6) — RESOLVED (Misdiagnosed)

Server E2E test 2026-07-30: omni_init → prefill → decode → WAV generation all work correctly with CANN T2W. 145+ WAVs generated, multi-turn conversations OK, no deadlock. The previous "deadlock" observation was the server idle-waiting for HTTP connections.

See: `R6_CANN_CONTEXT_DEADLOCK_INVESTIGATION.md`

### 6. Sequential Session Crash (R11) — FIX APPLIED (CLI Verified)

6-guard lifecycle-safe `ggml_backend_cann_free` in `ggml-cann.cpp:2113-2164`:
- GUARD 1: Null backend check
- GUARD 2: Null context check (double-free prevention)
- GUARD 3: Set device before ACL operations
- GUARD 4: Synchronize with error tolerance
- GUARD 5: Reset device with error tolerance
- GUARD 6: Null out context before delete

CLI smoke test: 39 WAVs, RTF=0.267, cann_dispatch=39, cann_failure=0, cpu_fallback=0.
Server sequential regression test blocked by API design (no omni_free endpoint).

See: `CANN_FREE_CRASH_ROOT_CAUSE.md`, `CANN_FREE_CRASH_MIN_REPRO.md`, `R11_CANN_FREE_CRASH_FIX_REPORT.md`

### 7. MP4 Adapter (R10) — IMPLEMENTED

ffmpeg extraction methods + prefill wiring in `llama_omni_adapter.py`. Server E2E smoke now unblocked by R15 fix.

### 8. Server CANN Re-Init (R15) — FIX APPLIED

aclInit error handling + server exception catch. Defensive fix: if CANN runtime is in bad state, server fails gracefully instead of crashing. E2E verified: server restart after SIGINT kill works correctly.

---

## Commit Chain

```
ee22811 (HEAD, tag: cann-flow-vocoder-aclgraph-kvcache-final-20260729)
        docs: HANDOFF and AUDIT final
a8acdf7 docs: G13 submission package final
50e8483 docs: G9-G11 gates PASS
8e08db4 docs: AUDIT.md — final gate log
01fdf71 docs: G13 submission package — RTF 0.229, 18.4x vs CPU
767dc20 docs: G12 clean reproduction PASS — RTF 0.236
3685050 docs: G8 1-hr stability PASS — 66 iters, 1368 WAVs
c13d2b7 docs: G7 30-min stability PASS — 37 iters, 661 WAVs
6154b85 docs: HANDOFF — Phase 3 final commit chain updated
9aa54f9 docs: Phase 3 final status — RTF 0.229 (-16.4%)
7e46faf docs: Phase 3 Rank 2 complete — ADD+NORM fusion
9a7f5c2 feat(P20): ADD+NORM (Add+LayerNorm) operator fusion for CANN
4a2cbcd feat(P19): CANN ACL graph capture for Flow model
```

## Tag Chain

```
cann-flow-vocoder-rtf027-20260729               (Phase 2 freeze)
cann-flow-vocoder-aclgraph-rtf0229-20260729      (Phase 3 freeze)
cann-flow-vocoder-aclgraph-kvcache-final-20260729 (Internal integration complete) ← CURRENT
```

---

## RTF Numbers (Complete, Corrected 2026-07-30)

### FP16 Internal RTF (uniform per-chunk mean)

| RTF | Label | Env | N | Source |
|-----|-------|-----|---|--------|
| **0.234** | **FP16 INTERNAL CANDIDATE** | Graph=on Fusion=on | 11 | R14-A (corrected) |
| 0.264 | FP16 CANN FRAMEWORK BASELINE | Graph=off Fusion=off | 17 | R13 (corrected) |
| **0.115** | **FLOW_RTF (candidate)** | Graph=on | n=11 | R14-A (mean) |
| **0.119** | **VOCODER_RTF (candidate)** | Graph=on | n=11 | R14-A (mean) |
| 0.146 | FLOW_RTF (baseline) | Graph=off | n=17 | R13 (mean) |
| 0.118 | VOCODER_RTF (baseline) | Graph=off | n=17 | R13 (mean) |
| ~0.000 | SERIAL_OVERHEAD_RTF | — | — | < 0.03ms, negligible |

### FP16 Profile-Aggregate RTF (for reference, NOT canonical)

| RTF | Label | Formula |
|-----|-------|---------|
| 0.254 | Candidate profile RTF | sum(compute)/sum(audio) = 3.263/12.840 |
| 0.275 | Baseline profile RTF | sum(compute)/sum(audio) = 5.175/18.840 |

### Q4_K_M Internal (NOT COMPETITION)

| RTF | Label | Weight | N | Source |
|-----|-------|--------|---|--------|
| 0.245 | 4-Quadrant A/B Q4 | Q4_K_M | 1 | G3 |
| 0.224 | Steady-state bucket | Q4_K_M | 1 | G4 |
| 0.229 | Phase 3 candidate | Q4_K_M | Phase 3 | Freeze |
| 0.236 | Clean reproduction | Q4_K_M | 1 | G12 |
| 0.253 | Matched-pair HIT P50 | Q4_K_M | 29 | F2/F4 |
| 0.272 | Matched-pair OFF P50 | Q4_K_M | 29 | F2/F4 |

### CPU T2W (no env vars)

| RTF | Label | Source |
|-----|-------|--------|
| 3.97 | CPU Flow+Vocoder (mean, Q4_K_M) | P5 |

---

## R0-R14 Execution Order

```
R0.  ✅ Fix P0-P6 status               → STATUS.md corrected (env var root cause)
R1.  ✅ Binary provenance audit         → SHA256 confirmed: cli=6913c972, server=61e05be0, tag=HEAD=ee22811
R2.  ✅ Process environment check       → /proc/PID/environ: OMNI_T2W_DEVICE + OMNI_VOC_DEVICE confirmed
R3.  ✅ Verify optimized code in binary → All CANN T2W strings in libomni.so
R4.  ✅ Minimal T2W backend isolation   → CLI: Flow/Vocoder both backend=CANN0, RTF 0.47 vs CPU 3.97
R5.  ✅ Worker-thread deferred init     → VERIFIED: deferred init works in CLI path
R6.  ✅ Server CANN T2W E2E test         → RESOLVED: NOT a deadlock; server E2E verified, 145+ WAVs, multi-turn OK
R7.  ✅ Fix stage timing                → VERIFIED: OMNI_T2W_PROFILE=2 gives Flow/Vocoder split
R8.  ✅ EOS/drain lifecycle            → VERIFIED: drain complete, is_final processed, AUDIO_SUCCESS
R9.  ✅ Voice cloning verification      → PASS: voice clone prompt generated, 12 WAVs, RTF 0.22-0.25
R10. ✅ MP4 adapter demux              → IMPLEMENTED: ffmpeg extraction + prefill wiring in llama_omni_adapter.py
R11. ✅ Sequential session fix          → FIX_APPLIED: 6-guard lifecycle-safe free in ggml-cann.cpp; CLI verified
R12. ✅ CANN candidate ready gate      → GATE PASSED: CANN T2W restored, P7 (FP16 RTF) approved via CLI
R13. ✅ FP16 CANN framework baseline   → RTF=0.264 (mean, n=17), FLOW=0.146, VOCODER=0.118
R14. ✅ FP16 optimized candidate       → RTF=0.234 (mean, n=11), FLOW=0.115, VOCODER=0.119
```

---

## Remaining Blocks for Competition Pilot

| Block | Impact | Resolution Path |
|-------|--------|----------------|
| **R6: Server CANN T2W** | ✅ RESOLVED — server works with CANN T2W | Misdiagnosed; see R6 investigation report |
| **R10: Adapter extraction** | ✅ IMPLEMENTED — ffmpeg extraction + prefill wiring in llama_omni_adapter.py | Server E2E smoke now unblocked |
| **R11: Sequential sessions** | ✅ FIX_APPLIED — 6-guard fix in ggml-cann.cpp | CLI verified; server regression blocked by API design |
| **R15: CANN Re-init Min Repro** | ✅ PASS — SIGINT kill → new server → CANN T2W | ACL_INIT_LIFECYCLE_AUDIT needed |
| **P8: MP4 Demux Single E2E** | ✅ PASS — ffmpeg + prefill + decode | CANN0 confirmed; visual SEMANTIC gate PENDING |
| **Audio Serial Loop 30** | ✅ PASS — 30/30 audio, 0 failures | Median E2E=8043ms; NOT full benchmark loop |
| **R11: CANN Free Fix Regression** | PENDING — 100+ mixed requests needed | Lifecycle tracking, double-free check |
| **R6: Thread Context Regression** | PENDING — thread topology analysis | Deadlock watchdog, context ownership |
| **Multimodal Benchmark Loop** | PENDING — 60 mixed samples needed | Text/Audio/Image/Video/TTS matrix |
| **FP16 Candidate Re-freeze** | REQUIRED — source changed | Clean build → RTF recheck → KV smoke → new tag |
| **G5: Benchmark data** | PENDING_ACCESS | ModelScope / mirrors / shared drives |
| **Evaluator checkpoints** | PENDING_ACCESS | Whisper/Paraformer/WavLM — can run on separate machine |

---

## Evidence Reconciliation (F0-F12) — ALL COMPLETE

| Task | Status | Output |
|------|--------|--------|
| F0: Gate count reconciliation | ✅ | 12/14 PASS, 1 BLOCKED, 1 DEFERRED |
| F1: G11 non-audio classification | ✅ | 9 HARNESS_TIMEOUT, 0 unexpected_no_audio |
| F2: KV cache matched-pair benefit | ✅ | 29/30 cache HIT, no per-chunk RTF degradation |
| F3: G9 non-HIT classification | ✅ | 2 HARNESS_TIMEOUT, 0 genuine misses |
| F4: RTF same-metric comparison | ✅ | P50 diff +0.007, within noise |
| F5: Terminology audit | ✅ | Forbidden language removed |
| F6: Tag and artifact verification | ✅ | Tag ee22811 = HEAD |
| F7: Submission package update | ✅ | G13 update complete |
| F8: Company document correction | ✅ | `COMPANY_LLAMA_OMNI_SERVER_CONTRACT.md` |
| F9: Weight format audit | ✅ | `BENCHMARK_MODEL_WEIGHT_CONTRACT.md` |
| F10: Server execution contract | ✅ | `BENCHMARK_SERVER_EXECUTION_CONTRACT.md` |
| F11: FP16 server smoke | ✅ | `FP16_SERVER_SMOKE_REPORT.md` |
| F12: TTS strengthening | ✅ | `P5_TTS_STRENGTHENING_REPORT.md` (superseded by R1-R9) |

---

## Document Inventory

| Document | Status |
|----------|--------|
| `STATUS.md` | UPDATED (2026-07-30 08:00) — Corrected naming, readiness, three-tier baselines |
| `HANDOFF.md` | UPDATED (2026-07-30 08:00) — Corrected naming, three-tier baselines |
| `FP16_RTF_METRIC_RECONCILIATION.md` | NEW — Uniform stats reconciliation, gap explanation |
| `FP16_RTF_MATCHED_PAIRS.csv` | NEW — Per-pair data (N=11) |
| `F0_GATE_COUNT_RECONCILIATION.md` | COMPLETE |
| `F1_G11_NON_AUDIO_CLASSIFICATION.md` | COMPLETE |
| `F2_F4_MATCHED_PAIR_RTF_REPORT.md` | COMPLETE |
| `F3_KV_CACHE_NON_HIT_CLASSIFICATION.md` | COMPLETE |
| `F5_TERMINOLOGY_AUDIT.md` | COMPLETE |
| `F6_TAG_AND_ARTIFACT_VERIFICATION.md` | COMPLETE |
| `OFFICIAL_BENCHMARK_STATUS.md` | COMPLETE |
| `BENCHMARK_ASSET_INVENTORY.md` | COMPLETE |
| `PROVISIONAL_ADAPTER_ASSUMPTION_AUDIT.md` | COMPLETE |
| `BENCHMARK_DATA_DOWNLOAD_CONTRACT.md` | COMPLETE (blocked by network) |
| `FINAL_CANONICAL_CONFIGURATION.md` | NEEDS UPDATE (Q4_K_M → FP16, add env vars) |
| `GRAPH_FUSION_CONFIGURATION_CONTRACT.md` | COMPLETE |
| `G9_KV_CACHE_FINAL_BINARY_REPORT.md` | COMPLETE |
| `G10_MULTI_PREFIX_REPORT.md` | COMPLETE |
| `G11_T2W_LIFECYCLE_REPORT.md` | COMPLETE |
| `G13_SUBMISSION_PACKAGE.md` | COMPLETE |
| `COMPANY_LLAMA_OMNI_SERVER_CONTRACT.md` | COMPLETE |
| `BENCHMARK_MODEL_WEIGHT_CONTRACT.md` | COMPLETE |
| `BENCHMARK_SERVER_EXECUTION_CONTRACT.md` | COMPLETE |
| `R6_CANN_CONTEXT_DEADLOCK_INVESTIGATION.md` | NEW — Server NOT deadlocked; misdiagnosed |
| `CANN_FREE_CRASH_ROOT_CAUSE.md` | NEW — R11 root cause analysis |
| `CANN_FREE_CRASH_MIN_REPRO.md` | NEW — R11 repro plan |
| `R11_CANN_FREE_CRASH_FIX_REPORT.md` | NEW — R11 6-guard fix report |
| `R10_MP4_ADAPTER_IMPLEMENTATION.md` | NEW — R10 ffmpeg + prefill implementation |
| `R15_SERVER_CANN_REINIT_FAILURE.md` | NEW — Server CANN re-init failure finding |
| `FP16_SERVER_SMOKE_REPORT.md` | COMPLETE |
| `FP16_BACKEND_REACHABILITY_REPORT.md` | COMPLETE |
| `FP16_COMPETITION_CONFIGURATION.md` | COMPLETE |
| `P5_TTS_STRENGTHENING_REPORT.md` | COMPLETE (superseded by R1-R9) |
| `SEQUENTIAL_SESSION_GATE_REPORT.md` | COMPLETE |
| `REAL_VIDEO_SMOKE_REPORT.md` | COMPLETE |
| `R2_R4_CANN_T2W_RESTORATION_REPORT.md` | COMPLETE (R1-R9; needs RTF correction) |
| `R10_MP4_ADAPTER_DEMUX_REPORT.md` | NEW — MP4 adapter code audit |
| `R11_SEQUENTIAL_SESSION_REPORT.md` | NEW — TTS state reset verified, CANN bug identified |
| `R12_CANN_CANDIDATE_READY_GATE.md` | NEW — P7 gate passed |
| `R13_R14_FP16_RTF_AB_REPORT.md` | SUPERSEDED by FP16_RTF_METRIC_RECONCILIATION.md (mixed stats fixed) |

---

## Key Decisions

| Decision | Status | Detail |
|----------|--------|--------|
| ACL_GRAPH_CAPTURE | PRIMARY | -21.1% Flow RTF (reconciled) |
| ADD_LAYERNORM_FUSION | CONDITIONAL on graph ON | Minimal T2W impact (targets LLM) |
| KV_CACHE | OPT_IN_READY / DEFAULT_OFF | Not measurable via CLI test mode |
| IM2COL | DEFERRED | Amdahl-limited, < 3% |
| OMNI_VOC_DEVICE=gpu | Maps to CANN0 in Ascend build | Required env var |
| Weight format | FP16 (16GB) | Required for competition |
| Q4_K_M | DEPRECATED for competition | QUANTIZED_WEIGHT_INTERNAL_ONLY |
| CLI vs Server | CLI WORKS for RTF measurement | Server BLOCKED by CANN threading deadlock |
| Flow/Vocoder overlap | NONE | Serial overhead < 0.03ms |

---

## Official Benchmarks (Pending)

Per competition rules:
- **Daily-Omni** — ✅ Repo cloned. PROVISIONAL adapter. BLOCKED: video gate, sequential sessions, data
- **TTS-Seed** — ✅ Repo cloned. PROVISIONAL adapter. BLOCKED: sequential sessions, data
- **Video-MME** — ✅ Repo cloned. PROVISIONAL adapter. BLOCKED: video gate, sequential sessions, data
- **OmniEvalKit** — ✅ Repo cloned. MiniCPM-o reference adapter available
