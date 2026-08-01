# F6 Phase 3 Handoff — 2026-08-01

## Commit Chain

```
0ecbacf docs(f6-phase3): C8 Flow/Vocoder plan, gate matrix update, audit log
9a916ce feat(f6-phase3): P9 Talker per-step instrumentation (C7)
256e59e docs(f6-phase3): C0-C7 checkpoint, data audit, event contract V4, instrumentation plan
f4133d0 docs(f6): canonical FP16 B6b rejection and historical confounder correction (P0-P6)
```

## Binary

| SHA256 | Source |
|--------|--------|
| `bd000463a8732500e5184882ece0cc7af8b3e2f383f1194f44ee27a651204bf5` | HEAD `9a916ce` |

## Completed (C0-C7, C8 plan)

| Gate | Status | Evidence |
|------|--------|----------|
| C0 | COMPLETE | Checkpoint: HEAD, binary/model SHA, frozen decisions |
| C1 | COMPLETE | `F6_PHASE3_INPUT_DATA_AUDIT.md` — ms resolution, split JSON, 240 profiles verified |
| C2 | COMPLETE | `F6_C2_D0D2_CI_ZERO_AUDIT.md` — ROUNDING_ARTIFACT (59% delta=0) |
| C3 | COMPLETE | `F6_C3_D2G0_ZERO_GAP_AUDIT.md` — BIMODAL (72% 0ms, 28% ~221ms OFF) |
| C4 | COMPLETE | `F6_EVENT_CONTRACT_V4.md` — 20 events, globals cataloged |
| C5 | COMPLETE | `F6_C5_GLOBAL_FALLBACK_AUDIT.md` — 4 globals, fix: T2W queue handle |
| C6 | COMPLETE | `F6_C6_PROFILE_LIFECYCLE_STATE_MACHINE.md` — 8-state FSM |
| C7 | COMPLETE | `9a916ce` — Talker per-step ring buffer, 2 hooks, JSON output |
| C8 | PLAN | `F6_C8_FLOW_VOCODER_FINEGRAINED.md` — implementation plan only |

## Key Findings from C1-C3 Audit

### 1. D0→D2 CI95 [0,0] — ROUNDING_ARTIFACT
Server stores integer milliseconds. True D0→D2 variation <1ms.
59% paired delta=0, 41% delta=±1-2ms.
**Correction:** `B6B_MAIN_LLM_ACCELERATION = NO_OBSERVED_DIFFERENCE_AT_CURRENT_RESOLUTION`

### 2. D2→G0 is BIMODAL, not always 0ms
- Mode 1 (72%): 0ms — TTS worker already waiting
- Mode 2 (23% OFF): ~221ms — TTS idle wake latency
- Mode 2 (18% ON): ~98ms — B6b reduces idle wake by 55%
Median is 0ms (CI95 [0,0]) — correct but incomplete. Gaps cluster in specific blocks.

### 3. Flow+Vocoder residual = 0ms at ms resolution
Flow: 135ms (p50), Vocoder: 122ms (p50), Sum = 267ms = T2W→WAV (267ms).
Previous analysis of 10ms residual was incorrect — caused by using different computation methods.
At ms resolution, pre_flow gap = 0ms, post_voc gap = 0ms.

### 4. G3/G4 missing from 115/120 FP16 profiles
`record()` silently rejects writes on generation mismatch. Workers snapshot generation once at wake, but `reset()` may bump it before the worker records. Fix: re-snapshot generation before each critical `record()` call.

## P9 Implementation Summary

```cpp
// omni.h: added TalkerStepRecord (72B), TalkerStepBuffer (500 steps, 36KB), TalkerStepSummary
// omni.cpp: recording hooks in TTS simplex loop (line ~6778) and TTS local loop (line ~7489)
// JSON: talker_step_summary in both modes, talker_steps[] in full mode
// Env: F6_PHASE3_TALKER_STATS=1 (default off)
```

## Next Actions (Priority Order)

### Immediate (C9 prerequisite)
1. **Smoke test C7 instrumentation**: Start server with `F6_PHASE3_TALKER_STATS=1`, send 1 TTS request, verify `talker_step_summary` in profile JSON
2. **Verify G3/G4 fix**: Add re-snapshot of `tts_thread_generation` before G3/G4 `record()` calls

### Short-term (C8-C10)
3. **Implement C8**: Add request-scoped profile handle to T2W queue item; replace global atomics
4. **C9 correctness gate**: 30 requests, verify all stages present, `critical_missing=0`
5. **C10 overhead gate**: 20 matched pairs, D0→W0 Δ ≤1%

### Medium-term (C11-C17)
6. Freeze Phase 3 workload (4 case types)
7. 120-request canonical baseline with full decomposition
8. Compute/wait/policy decomposition of G0→T2W dequeue
9. Backend reachability + msprof
10. Amdahl candidate ranking

## Frozen Constraints (unchanged)
- B6b OFF: OMNI_TTS_FIRST_CHUNK_STEP=10
- CHUNK_SIZE=25 FROZEN
- Do NOT train DSpark
- Do NOT write AscendC kernels
- Tag `fp16-f6-early-tts-dispatch-internal-20260731` @ `00a2755` preserved

## Data Locations
- 120-pair FP16 profiles: `/tmp/f6_fp16_w10/`
- C7 binary: `/workspace/llama.cpp-omni-f6/build/bin/llama-omni-server` (SHA `bd000463`)
- All Phase 3 docs: `/workspace/llama.cpp-omni-f6/docs/tracking/F6_PHASE3_*.md`, `F6_C*_*.md`, `F6_EVENT_CONTRACT_V4.md`
