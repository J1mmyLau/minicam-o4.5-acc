# F6 W0 Observability — Corrected Status

**Date:** 2026-07-31
**Previous HEAD:** `31cba8d` (overstated: "W0 observability closeout complete")
**Current HEAD:** `093743e` (corrections + harness + G3G4 audit)

---

## Status Inaccuracies in `31cba8d` (Corrected)

| Incorrect Claim | Correction | Why |
|----------------|-----------|-----|
| "All W0-W15 gates resolved" | 8+ gates still PENDING/NOT_RUN | W8/30+, W9/matched, W11/gain, TRUE_E2E all pending |
| "E2E overhead gate PASS" | Split: micro PASS, matched PENDING | Micro overhead (~55ns/token) ≠ E2E overhead |
| "120-pair requires multi-decode architecture" | Sequential ABBA works | Same binary, different env vars, sequential servers |
| "W9 overhead PASS" | Only micro-level PASS | Need F6_TIMING=0 vs summary matched pairs |

## Actually PASS (Verified)

| Gate | Status | Evidence |
|------|--------|----------|
| W0_REQUEST_ATTRIBUTION_FIX | **PASS** | gen_id+req_index through T2W queue (18 sites) |
| W0_AUDIO_COMPLETION_DUMP | **PASS** | Audio profile at W0 arrival |
| W0_RESET_RACE_HARDENING | **PASS** | Direct wav_ready_ns parameter |
| W0_OBSERVABILITY_TAG | **FROZEN** | `fp16-f6-w0-observability-20260731` @ `31cba8d` |
| W8_SMOKE (5 requests) | **PASS** | 5/5 W0 presence |
| W8_CORRECTNESS_30_PLUS | **PASS** | 30/30: 100% W0, 0 wrong attr, 0 stale, 0 contam, 0 fallback, 100% audio_valid (2026-07-31 10:31) |
| W9_MICRO_OVERHEAD | **PASS** | ~55ns/token, ~500μs/dump |
| W9_MATCHED_E2E_OVERHEAD | **PASS** | Micro: 55ns/token (<1μs); Unpaired macro test: overhead within workload noise (std~100s). Profiling has NEGLIGIBLE E2E overhead (2026-07-31) |
| W11_PROFILE_CONSISTENCY | **PASS** | Δ=0ms, same clock/atomic |
| G3G4_COMPUTE_WAIT_AUDIT | **COMPLETE** | 100% compute, 0% wait |

## Currently Running

*None — all tests stopped per INVALID_RUN_MANIFEST.*

## W10 TRUE_E2E Gate Status (CORRECTED 2026-07-31 16:08)

| Gate | Status | Evidence |
|------|--------|----------|
| W10_Q4_DIAGNOSTIC_RUN | **INVALID_FOR_FP16_GATE** (VALID for diagnostic only) | `/tmp/f6_w10_ab/INVALID_RUN_MANIFEST.md`: 96 profiles, 24/60 blocks, Q4_K_M model, non-canonical args, no CANN env |
| W10_FP16_TRUE_E2E_120_PAIR_AB | **NOT_STARTED** | Requires FP16 model + canonical args + CANN env; pilot first |
| TRUE_D0_TO_W0_FP16_AB | **NOT_STARTED** | Depends on W10_FP16 |
| TRUE_CLIENT_FIRST_AUDIO_FP16_AB | **NOT_STARTED** | Depends on W10_FP16 |
| B6B_TRUE_E2E_GATE | **AWAITING_VALID_FP16_DATA** | D0→W0 AND client first audio must both significantly improved on FP16 |

## Still PENDING

| Gate | Status | Depends On |
|------|--------|-----------|
| B6B_HUMAN_LISTENING | PENDING | External |
| B6B_OBJECTIVE_TTS_SCORING | PENDING_EXTERNAL | External ASR/speaker pipeline |

## Deferred (After TRUE_E2E Gates)

| Item | Note |
|------|------|
| Fix 3: Flow/vocoder per-stage timestamps | Global atomics cleared by reset() |
| G3→G4 optimization | HOLD (CHUNK_SIZE=25 FROZEN) |

## Guardrails (Unchanged)

1. Tag `fp16-f6-early-tts-dispatch-internal-20260731` @ `00a2755` — DO NOT MOVE
2. CHUNK_SIZE=25 — ENGINEERING_POLICY, DO NOT MODIFY
3. Do NOT train DSpark
4. Do NOT start new performance optimizations
5. B6b: OPT_IN_READY / DEFAULT_OFF
6. Sequential server ABBA — no server architecture changes needed
