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
| W9_MICRO_OVERHEAD | **PASS** | ~55ns/token, ~500μs/dump |
| W11_PROFILE_CONSISTENCY | **PASS** | Δ=0ms, same clock/atomic |
| G3G4_COMPUTE_WAIT_AUDIT | **COMPLETE** | 100% compute, 0% wait |

## Currently Running

| Gate | Status | Target |
|------|--------|--------|
| W8_CORRECTNESS_30_PLUS | **IN_PROGRESS** | 30+ requests, 100% W0, 0 errors |

## Still PENDING

| Gate | Status | Depends On |
|------|--------|-----------|
| W9_MATCHED_E2E_OVERHEAD | PENDING | W8 completion, 20-pair timing comparison |
| TRUE_D0_TO_W0_AB | NOT_RUN | W8 + W9 completion |
| TRUE_CLIENT_FIRST_AUDIO_AB | NOT_RUN | W8 + W9 completion |
| B6B_TRUE_E2E_GATE | NOT_REACHED | Both TRUE_E2E gates must show significant improvement |

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
