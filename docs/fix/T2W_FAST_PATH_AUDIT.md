# T2W Generation Fast-Path Audit

**Date**: 2026-08-05  
**Context**: fix/ws-session-lifecycle commit 7fbf19a — ws_finalize_context_reusable Step 2 advances T2W drain generations  
**Question**: Is `use_tts_template=true` SAFE? Can the finalizer prematurely advance T2W generations during an active TTS session?

---

## 1. Three Call Sites

| # | Line | Context | Guard | Behavior |
|---|------|---------|-------|----------|
| 1 | 1180-1182 | Turn-based (chat/completions), after stream_decode, before response.done | `!parsed_input.use_tts_template` | **TTS NEVER reaches this** |
| 2 | 1353 | Full-duplex (/realtime), after decode_thread.join(), before response.done | **NONE** | ALL full-duplex (text + TTS) reach this |
| 3 | 1416 | Cleanup (disconnect), BEFORE omni_prepare_for_reuse | N/A (cleanup always runs) | ALL paths reach this |
| 3b| 1431 | Cleanup, AFTER KV clear + omni_prepare_for_reuse | N/A | Completes DRAINING→REUSABLE |

---

## 2. Call Site 1 (Turn-Based Text-Only): SAFE ✅

```
if (!parsed_input.use_tts_template) {   ← GUARD
    ws_finalize_context_reusable(octx);
}
```

- **TTS sessions**: `parsed_input.use_tts_template == true` → `!true == false` → **SKIP**
- **Text-only sessions**: `parsed_input.use_tts_template == false` → `!false == true` → **EXECUTE**

**Verdict**: IMPOSSIBLE for TTS turn-based sessions to enter the finalizer here.

---

## 3. Call Site 2 (Full-Duplex): CONDITIONALLY SAFE ⚠️

No guard — ALL full-duplex decodes (text AND TTS) reach line 1353.

### TTS Full-Duplex Timeline
```
T0: decode_thread starts (stream_decode full-duplex)
T1: LLM generates text + sends to TTS
T2: T2W worker dequeues TTS tasks, produces WAV chunks
T3: decode_thread.join() ← LLM done
T4: ws_finalize_context_reusable(octx)  ← CALL SITE 2
    Step 1: CAS ACTIVE→DRAINING → OK
    Step 2: Advances tts_producer_done + final_processed
    Step 3: active_t2w_generation != 0?  ← T2W still processing gen N
            → returns early, leaves state = DRAINING
T5: response.done sent to client
T6: Client disconnects → call site 3 (cleanup)
```

### Safety Analysis: Step 2 Advances Generations Prematurely?

At T4, the finalizer advances `tts_producer_done_generation` and `final_processed_generation` to the current `request_generation`. The T2W worker may still be processing the last batch (active_t2w_task_count > 0).

**Key safety property** (from R13 T2W worker flow, omni.cpp ~11641):
```
1. Dequeue task → active_t2w_task_count++
2. Flow+Vocoder → Write WAV      ← AUDIO WRITTEN HERE
3. active_t2w_task_count--       ← active drops AFTER write
4. Set active_t2w_generation=0    ← idle AFTER active drops
5. Set final_processed_generation ← set LAST
```

The drain predicate (omni.cpp:6222-6228) requires ALL FOUR:
```
(1) tts_producer_done >= my_gen     ← advanced by finalizer
(2) queued_t2w_task_count == 0      ← real state
(3) active_t2w_task_count == 0      ← real state, drops AFTER WAV write
(4) final_processed >= my_gen       ← advanced by finalizer
```

**Race window**: Between steps 3 and 5 above, `active==0 && queued==0` but `final_processed` not yet set by worker. If finalizer runs in this window:
- Conditions (1)(4): PASS (advanced by finalizer)
- Conditions (2)(3): PASS (worker just finished)
- Result: Drain predicate passes... but is the WAV safe?

**WAV safety**: Step 2 (Write WAV) happens BEFORE step 3 (active_t2w_task_count--). So when `active==0`, the WAV is already written. The finalizer's advance of `final_processed` is idempotent — the audio is complete.

**Conclusion**: Even if the finalizer advances generations during the race window, the WAV is already safe. The worst case: drain returns 1-2ms earlier than it would have with native final_processed update. No audio loss.

### Step 3 Protection

Even if Step 2 advances generations early, Step 3's `active_t2w_generation != 0` check prevents REUSABLE:
- T2W worker still processing gen N → active_t2w_generation == gen_N
- Comparison: `active_gen (gen_N) != 0` → TRUE
- Result: **return early, leaves state = DRAINING**

### At Disconnect (Call Site 3)
```
ws_finalize_context_reusable(octx)   ← idempotent (already DRAINING)
omni_prepare_for_reuse(octx)         ← joins TTS thread + T2W drain
ws_cleanup_kv_cache_for_reuse(octx)  ← clear KV after threads joined
ws_finalize_context_reusable(octx)   ← NOW active_t2w==0 → REUSABLE ✅
```

---

## 4. Call Site 3 (Cleanup): SAFE ✅

Called twice in sequence:

### First call (line 1416): Advances generations BEFORE omni_prepare_for_reuse
- Sets break_event, clears text_queue, notifies text_cv
- Calls finalizer → advances T2W generations
- Step 3: if T2W still active → stays DRAINING (not REUSABLE yet)

### omni_prepare_for_reuse (line 1418):
- Joins TTS thread (no more TTS tasks will be produced)
- t2w_drain_signal_and_wait:
  - For text-only: all 4 conditions pass immediately (gens advanced, no T2W tasks)
  - For TTS: waits for active==0, queued==0 (real drain), then returns

### Second call (line 1431): Completes REUSABLE transition
- All threads joined → active_t2w_generation == 0
- CAS DRAINING→REUSABLE succeeds

---

## 5. Is `use_tts_template=true` safe?

| Path | Finalizer Reachable? | Premature Gen Advance? | Premature REUSABLE? | WAV Loss? |
|------|---------------------|----------------------|--------------------|-----------|
| Turn-based TTS | NO (guard) | N/A | N/A | NO |
| Full-duplex TTS | YES (no guard) | YES (theoretical) | NO (Step 3 blocks) | NO (WAV before active-- ) |
| Abort mid-TTS | YES (cleanup) | YES | NO (Step 3 + omni_prepare_for_reuse) | NO |
| Text-only (all paths) | YES | YES (by design) | YES (correct) | N/A |

---

## 6. Conclusion

**TTS SAFETY: CONFIRMED** — The `use_tts_template` guard at call site 1 prevents TTS turn-based sessions from ever entering the finalizer. Call site 2 (full-duplex) lacks a guard, but Step 3's `active_t2w_generation` check prevents premature REUSABLE, and the drain predicate's 4-condition AND ensures WAV completeness before drain returns. The advance of `final_processed_generation` by the finalizer is safe because the T2W worker writes WAV before decrementing `active_t2w_task_count` — when all conditions pass, audio is always complete.

**Recommendation**: No code change needed. The CAS-based safety net is sufficient. Proceed to T7 empirical verification.
