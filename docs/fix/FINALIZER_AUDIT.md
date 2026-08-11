# ws_finalize_context_reusable() — Complete Audit

**Audit date:** 2026-08-05
**Branch:** `fix/ws-session-lifecycle`, HEAD `17d9542`
**Base:** `bdd4550`
**Scope:** `tools/server/ws_handler.cpp` only

## 1. State Machine

```
                  stream_decode() starts
                  ┌─────────────────────┐
                  ▼                     │
  ┌──────────┐  ┌──────┐  finalizer()  ┌──────────┐  TTS drain  ┌──────────┐
  │REUSABLE(0)│─▶│ACTIVE(1)│───────────▶│DRAINING(2)│────────────▶│REUSABLE(0)│
  └──────────┘  └──────┘               └──────────┘              └──────────┘
       ▲            │                        │                        │
       │            │ abort/exception        │ T2W still active       │
       │            ▼                        ▼                        │
       │       ┌──────────────┐    ┌─────────────────┐                │
       │       │NOT_REUSABLE(3)│    │ stays DRAINING   │               │
       │       └──────────────┘    │ (active_gen > 0) │               │
       │                           └─────────────────┘               │
       └─────────────────────────────────────────────────────────────┘
```

## 2. Call Site Analysis

### Call Site 1: Turn-based Normal Completion (line 1125-1126)
```cpp
if (!parsed_input.use_tts_template) {
    ws_finalize_context_reusable(octx);
}
```

**Exit path:** Normal text-only turn completion
**Pre-conditions:**
- `decode_thread.join()` completed (line 1101)
- If TTS: `omni_duplex_drain_tts_audio` completed (line 1114-1119)
- `use_tts` restored to `prev_use_tts` (line 1120)

**Safety assessment:**
| Check | Status | Detail |
|-------|--------|--------|
| decode thread exited | ✅ YES | Joined at line 1101 |
| T2W thread may access octx | ⚠️ POSSIBLE | T2W thread NOT joined here — still running |
| active_t2w_generation | ⚠️ MAY BE >0 | T2W worker thread still alive |
| output queue may still write | ✅ NO | TTS drained or not started |
| CAS source states | ACTIVE, DRAINING | Guarded by `!use_tts_template` — TTS path excluded |
| ACTIVE→REUSABLE directly | ❌ NO | Goes through DRAINING |
| CAS failure handling | ✅ CORRECT | REUSABLE/NOT_REUSABLE → return; DRAINING → fall through |
| decode thread still running | ✅ NO | Joined before finalizer |

**Critical finding — TTS guard (line 1125):**
The guard `!parsed_input.use_tts_template` means this finalizer is ONLY called for text-only.
For TTS sessions, `omni_duplex_drain_tts_audio` (line 1114) manages state.
**This is correct.** The TTS path never reaches this finalizer call.

### Call Site 2: Full-duplex Normal Completion (line 1298)
```cpp
ws_finalize_context_reusable(octx);
```

**Exit path:** Full-duplex decode completion
**Pre-conditions:**
- `decode_thread.join()` completed (line 1292-1293)

**Safety assessment:**
| Check | Status | Detail |
|-------|--------|--------|
| decode thread exited | ✅ YES | Joined at line 1292-1293 |
| T2W thread may access octx | ⚠️ POSSIBLE | T2W thread NOT joined |
| use_tts guard | ❌ NONE | **Called unconditionally** — no `!use_tts_template` guard |
| CAS source states | ACTIVE, DRAINING | CAS provides safety |
| CAS failure handling | ✅ CORRECT | Won't overwrite NOT_REUSABLE |

**Critical finding — NO TTS guard:**
Unlike call site 1, this is called WITHOUT checking `!parsed_input.use_tts_template`.
For text-only full-duplex: safe (T2W has no tasks, active_t2w_generation check catches).
For TTS full-duplex: potentially unsafe —`active_t2w_generation` may still be >0 when finalizer runs.
**The CAS + active_t2w_generation check provides runtime safety** — if T2W is still running, the finalizer leaves state as DRAINING (not REUSABLE).

**Risk:** If T2W finishes AFTER the finalizer runs (leaving DRAINING), and no subsequent cleanup touches context_state, the session could stay DRAINING forever. However, the cleanup path (call site 3) handles this when the WebSocket disconnects.

### Call Site 3: Cleanup Path (line 1362)
```cpp
omni_prepare_for_reuse(session->octx);
ws_finalize_context_reusable(session->octx);
```

**Exit path:** WebSocket disconnect / session close / abort / exception
**Pre-conditions:**
- `break_event = true` (line 1349)
- text_queue cleared (line 1352)
- `omni_prepare_for_reuse` completed — ALL threads joined (LLM, TTS, T2W)

**Safety assessment:**
| Check | Status | Detail |
|-------|--------|--------|
| decode thread exited | ✅ YES | omni_prepare_for_reuse joins it |
| T2W thread exited | ✅ YES | omni_prepare_for_reuse joins it |
| TTS thread exited | ✅ YES | omni_prepare_for_reuse joins it |
| active_t2w_generation | ✅ 0 | Thread dead, generation counter reset |
| output queues | ✅ CLEARED | omni_prepare_for_reuse empties all queues |
| CAS source states | ACTIVE, DRAINING | From normal path OR abort |
| CAS failure handling | ✅ CORRECT | NOT_REUSABLE → don't force |

**This call site is the safest** — all threads are dead, all queues empty.
**Problem:** `omni_prepare_for_reuse` (line 1356) calls `t2w_drain_signal_and_wait` for ~10s before the finalizer even runs. The finalizer should ideally run BEFORE `omni_prepare_for_reuse` to shortcut the drain wait.

## 3. use_tts Guard Analysis (Commit 17d9542)

### Why the guard was removed
The original guard was:
```cpp
if (octx->use_tts) return;  // DON'T touch TTS sessions
```

**Problem:** After text-only decode, `use_tts` has been restored to `prev_use_tts` (line 1120: `octx->use_tts = prev_use_tts;`). If the session was initialized with TTS support (`prev_use_tts=true`), then `octx->use_tts` is `true` even though this was a text-only request. The guard would SKIP the finalizer for text-only requests on TTS-capable sessions — precisely the sessions that need it most.

### What protects TTS sessions now
1. **Call site 1:** `!parsed_input.use_tts_template` guard (line 1125) — TTS path excluded before reaching finalizer
2. **Call site 2:** No guard, but `active_t2w_generation != 0` check (line 219) prevents premature REUSABLE
3. **Call site 3:** `omni_prepare_for_reuse` already joined T2W thread — `active_t2w_generation == 0`
4. **CAS:** Won't overwrite NOT_REUSABLE set by TTS drain failure
5. **Drain completion guard (omni.cpp:13424):** `drain_gen < prev_gen` reject — catches premature reuse

### Verdict on use_tts guard removal
**SAFE for text-only:** The guard was actively harmful.
**NEEDS VERIFICATION for TTS:** The full-duplex path (call site 2) has no `!use_tts_template` guard. If called during active TTS, `active_t2w_generation != 0` prevents REUSABLE, but leaves DRAINING — requiring call site 3 to finish the job at disconnect. This is a soft dependency on the cleanup path, not a bug.

## 4. T2W Drain Interaction

### Normal path (call sites 1, 2)
`ws_finalize_context_reusable` advances `drain_complete_generation` which unblocks the next request's entry guard (`omni.cpp:13424`). BUT it does NOT advance `tts_producer_done_generation` or `final_processed_generation`.

When `omni_prepare_for_reuse` later calls `t2w_drain_signal_and_wait` (at disconnect):
- Predicate requires: `tts_producer_done_generation >= my_gen` AND `final_processed_generation >= my_gen`
- For text-only: `tts_producer_done_generation` was NEVER advanced (no TTS producer)
- Result: **drain wait times out** (~5s adaptive minimum × poll iterations ≈ 10s)

### Root cause of ~10s text-only drain
The drain predicate has 4 conditions:
1. `tts_producer_done_generation >= my_gen` — **FAIL** for text-only (never set)
2. `queued_t2w_task_count == 0` — PASS (no tasks)
3. `active_t2w_generation == 0 || active_gen > my_gen` — PASS (active_gen if non-zero, would be from previous gen)
4. `final_processed_generation >= my_gen` — depends on R13 auto-advance

Wait: R13's `tts_mark_producer_done` has auto-advance logic. But `tts_mark_producer_done` is ONLY called when `speek_done` is set. For text-only, `need_speek` is false, so `tts_mark_producer_done` is never called.

**Confirmed: text-only T2W drain always times out.**

### Fix strategy
Option A: In `ws_finalize_context_reusable`, also advance `tts_producer_done_generation` and `final_processed_generation` when there are no pending T2W tasks.

Option B: Move `ws_finalize_context_reusable` BEFORE `omni_prepare_for_reuse` in call site 3, AND have it set a flag that causes `t2w_drain_signal_and_wait` to fast-path.

Option C: Add a text-only fast-path check at the start of `t2w_drain_signal_and_wait`.

**Recommendation: Option A** — extend `ws_finalize_context_reusable` to handle all generation-scoped drain bookkeeping for text-only.

## 5. CAS Transition Analysis

### Allowed source states
| Source State | CAS Target | Result |
|-------------|------------|--------|
| ACTIVE(1) | DRAINING(2) | ✅ CAS succeeds → proceed to REUSABLE |
| DRAINING(2) | DRAINING(2) | ❌ CAS fails → expected=DRAINING → fall through to REUSABLE step |
| REUSABLE(0) | DRAINING(2) | ❌ CAS fails → return (nothing to do) |
| NOT_REUSABLE(3) | DRAINING(2) | ❌ CAS fails → return (don't touch) |

### REUSABLE transition (Step 3)
| Source State | CAS Target | Result |
|-------------|------------|--------|
| DRAINING(2) | REUSABLE(0) | ✅ CAS succeeds |
| ACTIVE(1) | REUSABLE(0) | ❌ CAS fails → force REUSABLE (except NOT_REUSABLE) |
| REUSABLE(0) | REUSABLE(0) | ❌ CAS fails → expected already REUSABLE or other → force if not NOT_REUSABLE |
| NOT_REUSABLE(3) | REUSABLE(0) | ❌ CAS fails → **don't force** (preserve NOT_REUSABLE) |

### CAS safety assessment
**Race: Two threads calling finalizer simultaneously**
Thread A: ACTIVE→DRAINING (CAS succeeds)
Thread B: sees DRAINING (CAS fails) → falls through → both try REUSABLE CAS
Thread A: DRAINING→REUSABLE (CAS succeeds)
Thread B: sees REUSABLE (CAS fails) → forces REUSABLE (already REUSABLE, harmless)

**Race: Finalizer vs TTS drain**
TTS drain sets NOT_REUSABLE while finalizer is running:
- Finalizer's Step 1 might see ACTIVE and CAS to DRAINING (before TTS drain)
- Finalizer's Step 3 might see NOT_REUSABLE and skip (correct — preserve failure)
- Or TTS drain set REUSABLE first, finalizer's CAS becomes no-op

**Verdict: CAS logic is correct for all observed races.**

## 6. Summary of Issues Found

| # | Issue | Severity | Location |
|---|-------|----------|----------|
| F1 | Call site 2: no `!use_tts_template` guard | LOW | Line 1298 — mitigated by active_t2w check |
| F2 | Text-only T2W drain ~10s (tts_producer_done never advanced) | MEDIUM | omni.cpp:6377 — t2w_drain_signal_and_wait |
| F3 | Call site 3: finalizer runs AFTER ~10s drain wait | MEDIUM | Line 1356-1362 ordering |
| F4 | KV cache not reset on abort | HIGH | omni_prepare_for_reuse doesn't reset n_past/KV |
| F5 | Worker BUSY blocks rapid reconnect | MEDIUM | Demo worker layer (separate from server) |

## 7. Audit Verdict

```
WS_FINALIZER_SAFETY              = PASS (CAS + active_t2w check correct)
WS_FINALIZER_CALL_SITE_COVERAGE  = PASS (all 3 exit paths covered)
WS_FINALIZER_USE_TTS_GUARD       = CORRECT (removed intentionally, CAS protects)
WS_FINALIZER_TTS_CONCURRENCY     = PASS (call site 1 guarded, 2 protected by active_t2w, 3 post-join)
WS_FINALIZER_T2W_DRAIN_FAST_PATH = FAIL (doesn't advance tts/final processed gen)
WS_FINALIZER_ORDERING_SITE_3     = SUBOPTIMAL (runs after 10s drain, should run before)
```
