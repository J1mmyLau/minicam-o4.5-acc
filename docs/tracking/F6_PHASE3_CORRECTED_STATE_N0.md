# F6 Phase 3 — Corrected State (N0)

**Date:** 2026-08-01
**HEAD:** `0377adef4b938127d780c942f8b9ba0bbd1c8b09` (+ uncommitted N2-N6 fixes)
**Branch:** `perf/f6-decode-to-speak`

## State Gates (Corrected from Previous Session)

| Gate | Status | Evidence |
|------|--------|----------|
| C7_IMPLEMENTATION | COMPILED | commit 9a916ce |
| C7_CLI_RUNTIME_SMOKE | PROVISIONAL_PASS | 2 CLI runs, Talker summary present, ~36 steps, p50=33ms |
| C7_SERVER_ASYNC_RUNTIME_SMOKE | PENDING | Not yet tested on production server path |
| C8_IMPLEMENTATION | COMPILED (+FIXED) | commit 0377ade + N5 thread_local RAII guard |
| C8_CLI_RUNTIME_SMOKE | PROVISIONAL_PASS | 2 CLI runs, Flow/Vocoder per-stage present, no stale_write |
| C8_SERVER_ASYNC_RUNTIME_SMOKE | PENDING | Not yet tested on production server path |
| C8_REQUEST_ATTRIBUTION_CONCURRENCY | PASS (thread_local) | N5: process-global raw ptr → thread_local RAII guard |
| M2_EVENT_SCHEMA | PASS | 21 enum = 21 names = STAGE_COUNT=21, no mismatch |
| M3_RING_BUFFER_RACE | CLOSED | N6: generation guard + finalize gate + rejection counters |
| C9_CORRECTNESS | NOT_READY | Requires N8 server async smoke first |

## Fixed Issues (This Session)

### N2+N3: Event Schema + Q-Semantics
- Fixed `STAGE_t2w_preprocess_end` comment: Q1→Q2
- Verified: 21 enum entries = 21 stage_names = STAGE_COUNT=21
- Q0=t2w_submit, Q1=t2w_dequeue, Q2=t2w_preprocess_end
- No "22 functional events" — confirmed 21 only
- Documented: F6_EVENT_SCHEMA_V5_FINAL.md

### N5: Global Mirror Pointer → thread_local RAII
- Removed: 4 process-global `g_c8_*_ptr` raw pointers
- Added: `C8FlowVocoderTargets` struct + `C8ProfileScope` RAII guard
- Thread-local: no cross-thread visibility
- Exception-safe: destructor always runs
- Nesting support: depth counter
- Documented: F6_C8_GLOBAL_MIRROR_POINTER_AUDIT.md

### N6: Ring Buffer Race Closeout
- Added: `active_generation` atomic for generation guard
- Added: `finalized` flag to prevent write-after-dump
- Added: 3 rejection counters (late_write_rejected, write_after_finalize, invalid_generation_write)
- Updated: 2 record_step() call sites to pass `tts_thread_generation`
- Documented: F6_TALKER_RING_BUFFER_RACE_CLOSEOUT.md

## Binary Provenance (N1+N7)

| Binary | SHA256 |
|--------|--------|
| llama-omni-cli | `fbda1fb024827c4795f8a4f0b5f58481645837194cd9c3af3c632ece8aa5c2a1` |
| llama-omni-server | `74d0ca312a1434f2eaab556af65069d676c454beeb8eef41a600162b67ce69d6` |
| libomni.so | `57ba8602bed0e2a563d3c313de714ecca309b76e7383d653511fbe9a6745cf71` |

## Uncommitted Changes

```
tools/omni/omni.h                       — N2/N3 comment fix + N6 generation guard
tools/omni/omni.cpp                     — N5 RAII scope + N2 comment + N6 call site update
tools/omni/token2wav/token2wav-impl.h   — N5 C8ProfileScope + C8FlowVocoderTargets
tools/omni/token2wav/token2wav-impl.cpp — N5 thread_local context + e2e_record_ns rewrite
docs/tracking/AUDIT.md                  — This session's entries
```

## Next Actions (Priority Order)

1. **N8**: Canonical server async 5-request smoke (requires server startup with FP16+CANN)
2. **N9**: Overlap/late-drain smoke (10 A→B pairs)
3. **N10**: CLI vs Server event parity
4. **N11**: Update C7/C8 gates (only after N8-N10 pass)
5. **N12**: 30-request C9 correctness gate
