# A0 — F6 Finalization Start Manifest

**Date:** 2026-08-02
**Mission:** MiniCPM-O 4.5 Ascend 910C Competition Finalization

## Git State

| Field | Value |
|-------|-------|
| Branch | `perf/f6-decode-to-speak` |
| HEAD commit | `0d39885b3d6922d6040bd24c79d3566759619a11` |
| HEAD message | `docs(f6-phase3): Step 9 static prefix PASS + S13 pilot 5/5 clean (2026-08-02)` |
| Modified files | `tools/omni/omni.cpp` (+14/-1), `tools/server/server-omni.cpp` (+82/-8) |
| Untracked | `docs/tracking/f6_lifecycle/`, `scripts/f6_*.py` |
| Working tree | clean except F6 lifecycle instrumentation/fix (uncommitted) |

### Last 15 Commits

```
0d39885 docs(f6-phase3): Step 9 static prefix PASS + S13 pilot 5/5 clean (2026-08-02)
b471d3e docs(f6-phase3): C10 final report + handoff update (2026-08-02)
6bb797c fix(f6-phase3): add T2W drain to HTTP handler for request serialization
c1d9418 fix(f6-phase3): scope drain-before-dump to DUMP_FULL only
70e6eb0 fix(f6-phase3): audio dump acquire-load pairing + R7 drain audit (DIAGNOSTIC_FIX)
5d2762e fix(f6-phase3): R7/R9 cross-request contamination fix + C9 30/30
dbf17a5 fix(f6-phase3): R7 per-request once-guard + remove global fallback to fix cross-request contamination
aabd12e docs(f6-phase3): N8/N9/C9/C10/S9/S13 reports — Phase 3 server gates closed (S7-S13)
6320bd3 build(f6-phase3): RelWithDebInfo clean build provenance (S5)
7c9ef72 docs(f6-phase3): TalkerStepBuffer memory model — formal happens-before proof (S4)
e1711c5 docs(f6-phase3): C8 thread-local runtime contract — proof by construction (S3)
b746244 docs(f6-phase3): canonical event inventory — 21≡21 proof, 22nd event debunked (S2)
13aab91 docs(f6-phase3): update handoff, gate matrix, and audit log with N2-N6 frozen state
ce53b18 docs(f6-phase3): N0-N7 audits, event schema V5, C8 thread-local audit, ring buffer closeout
0f9be2f fix(f6-phase3): generation-safe Talker step recording and finalize guards (N6)
```

## Binary SHA256

| Binary | SHA256 |
|--------|--------|
| `llama-omni-server` | `5a414af699e8f7a52126e61c405876342667f5081251a94e2bf7bdb1a4053525` |
| `llama-omni-cli` | `54999244edf4a2edb0fb42a5797007a7d9671ed3e592665b49de5a9488479658` |
| `libomni.so` | `b611a2bcfd3e478e35925107dfdba102aba60760d5c063dc8ef3c4b1e80856a1` |

All built from `build-f6-phase3-relwithdebinfo/` with uncommitted F6 lifecycle instrumentation.

## Model SHA256

| Model | SHA256 | Size |
|-------|--------|------|
| `MiniCPM-o-4_5-F16.gguf` | `d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de` | 16.4 GB |
| `MiniCPM-o-4_5-Q4_K_M.gguf` | `1237a97ee081b8abebc47aa7dad565701e8f5f904cdc92f6723ac4281bbc0932` | 5.0 GB |

## CANN / NPU / Driver

| Component | Version |
|-----------|---------|
| CANN toolkit | `9.1.0-beta.1` (V100R001C11B050) |
| Driver / npu-smi | `25.5.1` |
| NPU chip | Ascend910 (2 chips) |
| HBM per chip | 64 GB |
| HBM usage | 3133 MB / 2876 MB (idle) |
| AICore usage | 0% (idle) |
| NPU processes | None running |

## Uncommitted Changes (F6 Lifecycle Fix v1)

### `tools/server/server-omni.cpp` (+82/-8)
- Nanosecond-precision event instrumentation (`_f6_ns_now`, `_f6_event`, `_f6_event_ctx_state`)
- `omni_duplex_drain_tts_audio` return value check → reject request on drain timeout
- Handler event tracing: OMNI_INIT_HANDLER_ENTER, OMNI_FREE_BEGIN/END, OMNI_INIT_BEGIN/END, HANDLER_ENTER, OCTX_LOCK_WAIT_BEGIN, OCTX_LOCK_ACQUIRED, STREAM_DECODE_BEGIN/END, OCTX_UNLOCKED, T2W_DRAIN_BEGIN/END, HANDLER_RETURN, HANDLER_RETURN_DRAIN_FAILED

### `tools/omni/omni.cpp` (+14/-1)
- Context state reset before async path: `need_speek.store(false)`, `prefill_done.store(false)`
- Diagnostic log of stale values at entry

## Frozen Constraints (Reaffirmed)

- B6b OFF
- CHUNK_SIZE=25 FROZEN
- No DSpark training
- No FA/speculation/operator fusion optimization
- No performance optimization
- No re-enabling B6b
- No one-server-per-request
- PID files only (no pgrep/pkill)
- Do NOT modify omni_init/omni_free paths until root cause confirmed

## Test Scripts (Existing)

| Script | Purpose | Port |
|--------|---------|------|
| `scripts/f6_mode_a_context_reuse.py` | MODE_A: context reuse, 4 variants V1-V4 | 18084 |
| `scripts/f6_mode_b_context_rebuild.py` | MODE_B: context rebuild, omni_init per request | 18083 |

## Known Issue: `queue.size()` Without Lock

The current `_f6_event_ctx_state` in `server-omni.cpp` reads `ctx->t2w_thread_info->queue.size()` without holding `t2w_thread_info->mtx`. Per A1 requirements, this must be replaced with atomic counters (`queued_t2w_task_count`, `active_t2w_task_count`).

## Run ID

```
F6_A0_20260802_manifest
```

All subsequent tests will bind to: HEAD=`0d39885`, server=`5a414af6`, model=`1237a97e` (Q4_K_M) or `d1e69845` (F16).
