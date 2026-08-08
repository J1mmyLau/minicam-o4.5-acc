# WebSocket Session Lifecycle Analysis

## State Machine

```
CTX_STATE_REUSABLE     = 0  // Idle, ready for next request
CTX_STATE_ACTIVE       = 1  // Request in progress (stream_decode running)
CTX_STATE_DRAINING     = 2  // T2W drain in progress (defined, never stored)
CTX_STATE_NOT_REUSABLE = 3  // Drain failed — reject next request
```

## All Paths

### Path 1: HTTP normal text-only (server-omni.cpp)
```
Entry: context_state=REUSABLE (checked at :455)
  → stream_decode() → context_state=ACTIVE (:13437 omni.cpp)
  → decode completes
  → T9 fix (:556-559): context_state=REUSABLE ✓
Exit: REUSABLE
```

### Path 2: HTTP normal TTS (server-omni.cpp)
```
Entry: context_state=REUSABLE
  → stream_decode() → ACTIVE
  → omni_duplex_drain_tts_audio() → REUSABLE or NOT_REUSABLE (:14594/14596 omni.cpp)
Exit: REUSABLE (drain ok) or NOT_REUSABLE (drain fail)
```

### Path 3: HTTP NOT_REUSABLE recovery (server-omni.cpp)
```
Entry: context_state=NOT_REUSABLE
  → Check drain predicate (:469-472): final_processed >= req_gen, active==0
  → If recovered → REUSABLE (:476)
Exit: REUSABLE (recovered) or NOT_REUSABLE (still pending)
```

### Path 4: WebSocket normal text-only, turn_based (ws_handler.cpp)
```
Entry: context_state=REUSABLE (initial)
  → stream_decode() in thread → ACTIVE (:13437 omni.cpp)
  → Text poll loop (:978-1029)
  → decode_thread.join() (:1031)
  → use_tts_template=false → skip TTS drain (:1044-1049)
  → NO context_state reset ← BUG
  → response.done (:1074)
  → Loop continues, waiting for next message
  → On disconnect → fall through to cleanup (:1249)
  → cleanup: omni_prepare_for_reuse (:1274)
      → stops threads, clears queues
      → does NOT set context_state ← BUG
Exit: ACTIVE (stale!)
```

### Path 5: WebSocket normal TTS, turn_based (ws_handler.cpp)
```
Entry: context_state=REUSABLE
  → stream_decode() → ACTIVE
  → decode_thread.join()
  → omni_duplex_drain_tts_audio() (:1044-1048) → REUSABLE ✓
  → response.done
Exit: REUSABLE (TTS drain sets it)
```

### Path 6: WebSocket client disconnect mid-decode (ws_handler.cpp)
```
Entry: context_state=ACTIVE (from active decode)
  → session removed from manager (:1025)
  → decode_thread.join() (:1026)
  → goto cleanup (:1027)
  → cleanup: break_event=true (:1267)
  → text_queue cleared (:1270)
  → omni_prepare_for_reuse (:1274)
  → does NOT set context_state ← BUG
Exit: ACTIVE (stale!)
```

### Path 7: WebSocket full-duplex (ws_handler.cpp)
```
Same pattern as turn_based.
Entry: context_state=REUSABLE
  → stream_decode() → ACTIVE
  → Text poll loop
  → decode_thread.join() or goto cleanup
  → NO context_state reset for text-only ← BUG
Exit: ACTIVE (stale!)
```

## Root Cause

`omni_prepare_for_reuse` stops all threads and clears queues but **never touches `context_state`**. The only functions that set `context_state=REUSABLE` are:
- `omni_duplex_drain_tts_audio` (TTS drain — sets REUSABLE at :14594 omni.cpp)
- `server-omni.cpp:559` (HTTP text-only — T9 fix)
- `server-omni.cpp:476` (HTTP NOT_REUSABLE recovery)
- `server-omni.cpp:691` (HTTP non-streaming text-only)

None of these are called from the WebSocket /backend path for text-only sessions.

The T9 fix (server-omni.cpp:556-560) was applied to the HTTP API path but never ported to ws_handler.cpp.

## Text-only T2W Thread Issue

Even for text-only sessions (use_tts=false), `stream_decode` (omni.cpp) creates a T2W generation:
- `my_gen = prev_gen + 1` (:13435)
- `context_state = ACTIVE` (:13437)
- T2W thread processes is_final but produces no WAV
- The T2W thread runs `t2w_drain_signal_and_wait` in omni_prepare_for_reuse
- DRAIN_TIMEOUT fires because `tts_producer_done_generation` and `final_processed_generation` never advance for text-only

`omni_prepare_for_reuse` calls the drain which waits 5s and times out. This is normal cleanup but wastes time.

## Fix Design

### Location: ws_handler.cpp

1. **Helper: `ws_finalize_decode_turn`** — Called after decode_thread.join() for same-session turn completion
2. **Cleanup section** — After omni_prepare_for_reuse, set context_state=REUSABLE

### Safety Conditions (both paths):
- `active_t2w_generation == 0` (no in-flight processing)
- For text-only: immediate transition (no real drain)
- For TTS: drain already completed by omni_duplex_drain_tts_audio
- Use `compare_exchange_strong` — don't overwrite NOT_REUSABLE

### State Transition:
```
ACTIVE
  → (decode completes, thread joined)
  → active_t2w_generation == 0 ✓
  → context_state.compare_exchange(ACTIVE → DRAINING)
  → advance drain_complete_generation
  → context_state.compare_exchange(DRAINING → REUSABLE)
```
