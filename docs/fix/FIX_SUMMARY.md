# WebSocket Session Lifecycle Fix

## Summary

**Branch:** `fix/ws-session-lifecycle` (based on frozen `bdd4550`)
**Worktree:** `/workspace/llama.cpp-omni-session-fix`
**Commits:** `0021584` + `17d9542`

## Problem

The WebSocket `/backend` path (`ws_handler.cpp`) called `stream_decode()` for text-only sessions but never reset `context_state` back to `CTX_STATE_REUSABLE` after decode completed. The HTTP API path (`server-omni.cpp:556-560`, T9 fix) had this reset, but it was never ported to the WebSocket path.

`omni_prepare_for_reuse()` (called at cleanup) stops threads and clears queues but does NOT touch `context_state`.

**Result:** After any text-only session, `context_state` stayed `ACTIVE` (1), causing the lifecycle guard (`omni.cpp:13416-13418`) to reject the next request with "context_state=1 (not REUSABLE/DRAINING)".

## Fix

Added `ws_finalize_context_reusable()` — a unified helper that safely transitions `context_state` from `ACTIVE → DRAINING → REUSABLE`.

### Safety
- Uses `compare_exchange_strong` — won't overwrite `NOT_REUSABLE` (drain failure)
- Checks `active_t2w_generation == 0` before final `REUSABLE` transition
- Goes through `DRAINING` phase for observability
- `CAS` is a no-op if TTS drain already set `REUSABLE`

### Call Sites (all exit paths covered)
1. Turn-based normal completion (after TTS drain block, line 1122)
2. Full-duplex normal completion (after `decode_thread.join()`, line 1294)
3. Cleanup path (after `omni_prepare_for_reuse`, line 1358)

### State Machine
```
context_state lifecycle:
  REUSABLE (0)
    ↓ stream_decode starts
  ACTIVE (1)  
    ↓ decode completes / session closes
    ↓ ws_finalize_context_reusable()
  DRAINING (2)  [transient]
    ↓ drain_complete_generation advanced
    ↓ active_t2w_generation == 0 ✓
  REUSABLE (0)  → next session can start
```

## Regression Results

| Test | Result | Notes |
|------|--------|-------|
| T1 Single text | PASS | HELLOworld, 0.5s decode |
| T2 Sequential ×3 (direct backend) | PASS | All 3 clean, no restart |
| T2 Sequential ×3 (E2E) | PASS | Session B needed 1 retry (worker BUSY — separate issue) |
| T5 Abort recovery | PASS (session accepted) | KV cache contamination causes wrong output (separate issue) |

## Known Limitations

1. **T2W drain delay (~10s):** For text-only, the T2W thread still waits for audio that never arrives. `omni_prepare_for_reuse` calls `t2w_drain_signal_and_wait` which takes 5s×2 rounds. `ws_finalize_context_reusable` runs AFTER this, so cleanup takes ~10s before the next session starts. Optimizing the drain predicate for text-only is a separate enhancement.

2. **Worker BUSY state:** The Demo worker's `RemoteBackendWorker` stays BUSY during cleanup. Rapid sequential connections get HTTP 403. Mitigation: retry with 3-5s delay between sessions.

3. **KV cache on abort:** When a session is aborted mid-decode, the KV cache (`n_past`) is not reset, potentially causing stale context for the next session. The `context_state` fix allows the next session to START (unblocks the lifecycle), but output quality may be affected. A separate fix should reset `n_past=0` in the cleanup path when `break_event` was set.

## Diff

```bash
git diff bdd4550..fix/ws-session-lifecycle -- tools/server/ws_handler.cpp
```

2 commits, +85 insertions in `ws_handler.cpp` only. No other files modified.
