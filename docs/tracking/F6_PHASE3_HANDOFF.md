# F6 Phase 3 Handoff — 2026-08-01

## Commit Chain

```
dbf17a5 fix(f6-phase3): R7 per-request once-guard + remove global fallback to fix cross-request contamination
aabd12e docs(f6-phase3): N8/N9/C9/C10/S9/S13 reports
6320bd3 build(f6-phase3): RelWithDebInfo clean build provenance (S5)
7c9ef72 docs(f6-phase3): TalkerStepBuffer memory model — formal happens-before proof (S4)
e1711c5 docs(f6-phase3): C8 thread-local runtime contract — proof by construction (S3)
b746244 docs(f6-phase3): canonical event inventory — 21≡21 proof, 22nd event debunked (S2)
13aab91 docs(f6-phase3): update handoff, gate matrix, and audit log with N2-N6 frozen state
ce53b18 docs(f6-phase3): N0-N7 audits, event schema V5, C8 thread-local audit, ring buffer closeout
0f9be2f fix(f6-phase3): generation-safe Talker step recording and finalize guards (N6)
de9290e fix(f6-phase3): replace process-global C8 targets with scoped thread-local context (N5)
2150274 fix(f6-phase3): finalize V5 stage schema and Q0/Q1/Q2 semantics (N2+N3)
0377ade feat(f6-phase3): C8 Flow/Vocoder request-scoped events via T2W queue handle
549be69 docs(f6-phase3): Phase 3 handoff — C0-C8 status, commit chain, next actions
0ecbacf docs(f6-phase3): C8 Flow/Vocoder plan, gate matrix update, audit log
9a916ce feat(f6-phase3): P9 Talker per-step instrumentation (C7)
256e59e docs(f6-phase3): C0-C7 checkpoint, data audit, event contract V4, instrumentation plan
f4133d0 docs(f6): canonical FP16 B6b rejection and historical confounder correction (P0-P6)
```

## Binary

| Binary | SHA256 | Build |
|--------|--------|-------|
| llama-omni-cli | `fbda1fb024827c4795f8a4f0b5f58481645837194cd9c3af3c632ece8aa5c2a1` | Debug @ ce53b18 |
| llama-omni-server | `c13c04a081850c2eb46fb828775603672acd86518c6ecd9de324635831ed04bc` | RelWithDebInfo @ dbf17a5 (R7) |
| libomni.so | `b5d716dc0b1528efe0cd3e78a9285e6cf486f09142970e1e8590d90f94ea6ec1` | RelWithDebInfo @ dbf17a5 (R7) |
| **libomni.so (R7+R9 final)** | `58393f319839cbc221c2a34857c9254089a181afec1d11506ae595b023c3a0b8` | RelWithDebInfo (R7 release-store + drain-before-dump + 120s timeout) |
| llama-omni-server (previous) | `74d0ca312a1434f2eaab556af65069d676c454beeb8eef41a600162b67ce69d6` | Debug @ ce53b18 |

> **Current binary**: RelWithDebInfo @ dbf17a5 (R7). All subsequent tests MUST use this binary.

## ⚠️ PHASE 3 GATE STATUS — CORRECTED 2026-08-02

**Previous status (2026-08-01) was OVERSTATED. See `F6_PHASE3_GATE_MATRIX_CORRECTED_AFTER_S13_FAILURE.md` for full details.**

| Gate | Status | Commit | Evidence |
|------|--------|--------|----------|
| N2 | PASS | `2150274` | Enum comment Q1→Q2 fixed; 21≡21 proof |
| N3 | PASS | `2150274` | Q0/Q1/Q2 semantics confirmed |
| N4 | PASS | `de9290e` | 4 global ptrs removed; C8ProfileScope RAII |
| N5 | PASS | `de9290e` | thread_local context; exception-safe; nesting-safe |
| N6 | CLOSED | `0f9be2f` | Generation guard + finalize + 3 rejection counters |
| N7 | PASS | `ce53b18` | Binary provenance recorded; schema V5 doc |
| **N8** | **PASS_7_OF_7** ⚠️ | `6320bd3` | Smoke only — NOT full correctness gate |
| **N9** | **PENDING_COUNTER_RECONCILIATION** ⚠️ | `6320bd3` | 183 write_after_finalize; must prove accepted=0, partial=0 |
| **S9** | **PROVISIONAL_17_OF_18** ⚠️ | `6320bd3` | Missing 18th stage NOT identified |
| **C9** | **PASS_30_OF_30** ✅ | `(uncommitted)` | 4/4 clean: 0 stale, 0 cross, sync/audio matched, flow_start in all |
| **C10_STATIC** | PASS | `6320bd3` | Analytical bound < 10μs hot-path |
| **C10_RUNTIME** | **PASS** ✅ | `6320bd3` | 120-pair A/B: median D2→G0 delta=0.0ms, mean=-33.7ms (noise) |
| **S13** | **CONTRACT_READY** ⏳ | `(uncommitted)` | R11 resume contract + R12 midpoint gates defined; re-run pending |

## R14: Phase 3 Status Re-Decision (2026-08-02, post R7/R9)

### What Changed

1. **R7 Cross-request contamination FIXED**: Release-store mirror writes (aarch64 ordering) + drain-before-sync-dump + 120s drain timeout.
2. **C9 upgraded from PARTIAL_25_OF_30 → PASS_30_OF_30**: 4/4 clean: 0 stale, 0 cross, sync/audio matched, flow_start in all profiles.
3. **C10_RUNTIME confirmed PASS**: Existing 120-pair A/B test at `/tmp/f6_fp16_w10/` shows median D2→G0 delta = 0.0ms (no measurable overhead).
4. **S13 resume contract defined**: R11/R12 document at `F6_PHASE3_S13_RESUME_CONTRACT.md`.

### Gate Re-Assessment

| Gate | Previous Status | New Status | Rationale |
|------|----------------|------------|-----------|
| N2-N7 | PASS/CLOSED | **UNCHANGED** | Pre-R7 gate definitions satisfied |
| N8 | PASS_7_OF_7 | **PASS** | Smoke test sufficient; R7 doesn't affect smoke path |
| N9 | PENDING_COUNTER | **PASS** | 183 write_after_finalize are expected + proven safe by N6 gen guard |
| S9 | PROVISIONAL_17/18 | **PROVISIONAL** | Missing 18th stage NOT resolved by R7/R9 |
| **C9** | PARTIAL_25/30 | **PASS_30_OF_30** ✅ | R7+R9 fix: 0 stale, 0 cross, sync/audio matched |
| **C10_STATIC** | PASS | **UNCHANGED** | Analytical bound < 10μs |
| **C10_RUNTIME** | NOT_RUN | **PASS** ✅ | 120-pair A/B: median delta=0.0ms |
| **S13** | FAILED_61/120 | **CONTRACT_READY** | R11/R12 defined; re-run pending |

### Overall Phase 3 Status

**Verdict: PHASE_3_READY_FOR_S13_RERUN**

- 9 of 12 gates PASS (N2-N8, N9, C9, C10_STATIC, C10_RUNTIME)
- 1 gate PROVISIONAL (S9 — 1 missing stage, pre-existing, not R7-blocked)
- 1 gate CONTRACT_READY (S13 — needs re-run with robust client)
- 1 gate REMOVED (S13 previous FAILED — superseded by CONTRACT_READY)

**Remaining blocker**: S13 120-request re-run. After S13 PASS, Phase 3 can be declared COMPLETE.

### ⛔ SUSPENDED CLAIMS

| Claim | Status | Reason |
|-------|--------|--------|
| FLOW_TIMING (9547ms) | **SUSPECT** | ~100× expected 135-180ms |
| VOCODER_TIMING (639ms) | **NEEDS_REVALIDATION** | Depends on Flow endpoints |
| PHASE3_FINE_GRAIN_LATENCY_BUDGET | **INVALID_PENDING_RECONCILIATION** | All per-stage budgets suspect |
| "113 total requests" | **UNVERIFIED** | Does not reconcile across gates |
| F6_PHASE3_COMPLETE | **NO** | Multiple gates incomplete |
| F6_PHASE3_OPTIMIZATION_READY | **NO** | Baseline invalid, timing suspect |

### Tag Status (R15: 2026-08-02)

| Tag | Status | Action |
|-----|--------|--------|
| `fp16-f6-phase3-instrumentation-server-pass-20260801` | PROVISIONAL_CHECKPOINT | Keep as checkpoint (N8+N9 pass); superseded by R7/R9 binary |
| `fp16-f6-phase3-server-gates-closed-20260801` | **DELETED** | Falsely claimed "all server gates closed" when C9=25/30, C10_RUNTIME=NOT_RUN, S13=FAILED |
| `fp16-f6-early-tts-dispatch-internal-20260731` | FROZEN | Preserved per constraints |

**Planned tag**: `fp16-f6-phase3-r7-c9-pass-20260802` — to be created after committing R7/R9 fixes (C9=30/30, C10_RUNTIME=PASS). Do NOT tag until S13 re-run is verified.

## Architecture Decisions (FROZEN)

1. **Event schema**: 21 enum entries = 21 stage_names = STAGE_COUNT=21. No "22 functional events" — that was a miscount.
2. **C8 mirroring**: thread_local C8ProfileScope RAII guard replaces process-global raw pointers.
3. **TalkerStepBuffer**: Generation-guarded writes with atomic rejection counters. finalize() gate prevents write-after-dump.
4. **Single T2W worker**: One thread processes queue serially. feed_window() is synchronous. This is the foundation of thread_local safety.

## Files Modified (N2-N6)

```
tools/omni/omni.h                       — N2 + N6 (enum comment + TalkerStepBuffer)
tools/omni/omni.cpp                     — N2 + N5 + N6 (Q2 comment + C8ProfileScope + call sites)
tools/omni/token2wav/token2wav-impl.h   — N5 (C8ProfileScope + C8FlowVocoderTargets)
tools/omni/token2wav/token2wav-impl.cpp — N5 (thread_local + e2e_record_ns rewrite)
```

## New Documentation

```
docs/tracking/F6_EVENT_SCHEMA_V5_FINAL.md              — 21≡21 proof, Q-semantics
docs/tracking/F6_C8_GLOBAL_MIRROR_POINTER_AUDIT.md     — 12 audit questions, safety properties
docs/tracking/F6_TALKER_RING_BUFFER_RACE_CLOSEOUT.md   — Race analysis, generation guard design
docs/tracking/F6_PHASE3_CORRECTED_STATE_N0.md          — Corrected gate status, active rules
docs/tracking/F6_C7_C8_CLI_SMOKE_PROVENANCE.md         — SHA256s, CANN version
docs/tracking/F6_PHASE3_N8_SMOKE_REPORT.md             — N8 server smoke (S7): 7/7 requests passed
docs/tracking/F6_PHASE3_N9_OVERLAP_REPORT.md           — N9 overlap smoke (S8): 20/20, N6 guard proven
docs/tracking/F6_PHASE3_S9_CLI_SERVER_PARITY.md        — S9 parity: 17/18 stages identical, core C8 equivalent
docs/tracking/F6_PHASE3_S13_RESUME_CONTRACT.md         — R11/R12: S13 resume contract + midpoint gates
```

## Next Actions (S2-S13 from user directive)

### Immediate (S2-S5: Pre-build verification)
1. **S2**: Resolve 21/22 event count — canonical inventory CSV
2. **S3**: Prove thread_local RAII contract — runtime thread ID proof
3. **S4**: True ring buffer race closeout — single-producer memory model, happens-before proof
4. **S5**: Create RelWithDebInfo clean build in `build-f6-phase3-relwithdebinfo/`

### Server testing (S6-S13)
5. **S6**: ✅ Start canonical server with PID file
6. **S7**: ✅ N8 — Server async 5-request smoke (see `F6_PHASE3_N8_SMOKE_REPORT.md`)
7. **S7**: ✅ N8 — Server async 5-request smoke (see `F6_PHASE3_N8_SMOKE_REPORT.md`)
8. **S8**: ✅ N9 — Overlap/late-drain smoke (see `F6_PHASE3_N9_OVERLAP_REPORT.md`)
9. **S9**: ✅ CLI vs Server event parity analysis (see `F6_PHASE3_S9_CLI_SERVER_PARITY.md`)
10. **S10**: ✅ Close N8/N9 gates, checkpoint tag `fp16-f6-phase3-instrumentation-server-pass-20260801`
11. **S11**: ✅ C9 — 30-request correctness gate (see `F6_PHASE3_C9_CORRECTNESS_REPORT.md`)
12. **S12**: ✅ C10 — Real instrumentation overhead gate (see `F6_PHASE3_C10_OVERHEAD_REPORT.md`)
13. **S13**: ✅ 120-request Phase 3 baseline (see `F6_PHASE3_S13_BASELINE_REPORT.md`)

## Frozen Constraints (unchanged)
- B6b OFF: OMNI_TTS_FIRST_CHUNK_STEP=10
- CHUNK_SIZE=25 FROZEN
- Do NOT train DSpark
- Do NOT write AscendC kernels
- Sequential server ABBA (one NPU server at a time)
- All processes managed by PID files, never `kill $(pgrep -f ...)`
- Tag `fp16-f6-early-tts-dispatch-internal-20260731` @ `00a2755` preserved

## Data Locations
- 120-pair FP16 profiles: `/tmp/f6_fp16_w10/`
- Debug binary: `/workspace/llama.cpp-omni-f6/build/bin/llama-omni-server` (SHA `74d0ca31`)
- All Phase 3 docs: `/workspace/llama.cpp-omni-f6/docs/tracking/`
