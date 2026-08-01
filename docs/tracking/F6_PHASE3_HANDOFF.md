# F6 Phase 3 Handoff — 2026-08-01

## Commit Chain

```
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
| llama-omni-server | `74d0ca312a1434f2eaab556af65069d676c454beeb8eef41a600162b67ce69d6` | Debug @ ce53b18 |
| libomni.so | `57ba8602bed0e2a563d3c313de714ecca309b76e7383d653511fbe9a6745cf71` | Debug @ ce53b18 |

> **Provenance note**: These are Debug builds produced before the clean RelWithDebInfo build (S5). All subsequent N8/N9/C9/C10/120-baseline MUST use the RelWithDebInfo binary from `build-f6-phase3-relwithdebinfo/`.

## Phase 3 Gate Status (N0-N6 FROZEN)

| Gate | Status | Commit | Evidence |
|------|--------|--------|----------|
| N2 | PASS | `2150274` | Enum comment Q1→Q2 fixed; 21≡21 proof |
| N3 | PASS | `2150274` | Q0=t2w_submit, Q1=t2w_dequeue, Q2=t2w_preprocess_end confirmed |
| N4 | PASS | `de9290e` | 4 global ptrs removed; C8ProfileScope RAII added |
| N5 | PASS | `de9290e` | thread_local context; exception-safe; nesting-safe |
| N6 | CLOSED | `0f9be2f` | Generation guard + finalize + 3 rejection counters |
| N7 | PASS | `ce53b18` | Binary provenance recorded; schema V5 doc |
| N8 | PENDING | — | Server async 5-request smoke (requires RelWithDebInfo build) |
| N9 | PENDING | — | Overlap/late-drain smoke (10 A→B pairs) |
| C9 | NOT_READY | — | Requires N8 server async smoke first |
| C10 | NOT_READY | — | Requires RelWithDebInfo binary |

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
```

## Next Actions (S2-S13 from user directive)

### Immediate (S2-S5: Pre-build verification)
1. **S2**: Resolve 21/22 event count — canonical inventory CSV
2. **S3**: Prove thread_local RAII contract — runtime thread ID proof
3. **S4**: True ring buffer race closeout — single-producer memory model, happens-before proof
4. **S5**: Create RelWithDebInfo clean build in `build-f6-phase3-relwithdebinfo/`

### Server testing (S6-S13)
5. **S6**: Start canonical server with PID file
6. **S7**: N8 — Server async 5-request smoke
7. **S8**: N9 — Overlap/late-drain smoke
8. **S9**: CLI vs Server event parity analysis
9. **S10**: Close N8/N9 gates, checkpoint tag
10. **S11**: C9 — 30-request correctness gate
11. **S12**: C10 — Real instrumentation overhead gate
12. **S13**: 120-request Phase 3 baseline

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
