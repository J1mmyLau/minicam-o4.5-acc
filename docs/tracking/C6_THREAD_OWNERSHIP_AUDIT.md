# C6: Thread Ownership Audit

**Date:** 2026-07-30
**Source:** omni.cpp (HEAD 0828de2, branch perf/flow-chunk-rtf)
**Method:** Static code audit — all thread creation, join, and state-variable sites enumerated

---

## 1. Thread Inventory

| Thread | Type | Field | Creation Sites | Join Sites |
|---|---|---|---|---|
| LLM (simplex) | `llm_thread_func` | `ctx_omni->llm_thread` | 1 site (line 11916) | 2 sites (line 5530, 5601) |
| TTS (simplex) | `tts_thread_func` | `ctx_omni->tts_thread` | **2 sites** (lines 11925/11928, 12161/12164) | 2 sites (line 5538, 5608) |
| T2W | `t2w_thread_func` | `ctx_omni->t2w_thread` | **2 sites** (lines 11936, 12170) | 2 sites (line 5557, 5617) |
| Duplex Encoder | `duplex_encoder_thread_func` | `dup->encoder_thread` | 1 site (line 10657) | duplex_stop_threads |
| Duplex LLM | `duplex_llm_thread_func` | `dup->llm_thread` | 1 site (line 10661) | duplex_stop_threads |
| Duplex Prefill Worker | `duplex_session_prefill_worker_func` | `sess->prefill_worker` | 1 site (line 13009) | session end |
| Duplex Decode Worker | `duplex_session_decode_worker_func` | `sess->decode_worker` | 1 site (line 13010) | session end |

---

## 2. Creation Site Analysis

### 2.1 LLM Thread — SINGLE OWNER ✅

**Creation:** Only at `stream_prefill` line 11916:
```cpp
if (!ctx_omni->llm_thread.joinable()) {
    llm_thread_running = true;
    ctx_omni->llm_thread = std::thread(llm_thread_func, ctx_omni, ctx_omni->params);
}
```
- Guard: `!joinable()` — prevents double-create
- State flag: `llm_thread_running` set BEFORE thread start
- Context: Inside `if (ctx_omni->async)` block, AFTER `kv_cache_system_prompt_done:` label
- Control flow: Reached on both MISS and HIT paths (since fix-2 moved label before threads)

**Verdict: Single owner confirmed.** LLM thread creation is correctly placed.

### 2.2 TTS Thread — DUAL OWNER ❌

**Creation site 1:** `stream_prefill` lines 11925/11928:
```cpp
if (ctx_omni->use_tts && !ctx_omni->tts_thread.joinable()) {
    tts_thread_running = true;
    ctx_omni->tts_thread = std::thread(tts_thread_func_duplex, ...);  // or tts_thread_func
}
```

**Creation site 2:** `stream_decode` lines 12161/12164:
```cpp
// 🔧 确保线程已启动（如果 prefill 是同步模式执行的，线程可能还没启动）
if (!ctx_omni->tts_thread.joinable() && ctx_omni->use_tts) {
    tts_thread_running = true;
    ctx_omni->tts_thread = std::thread(tts_thread_func_duplex, ...);  // or tts_thread_func
}
```

**Analysis:**
- The comment reveals the design intent: "ensure thread is started (in case prefill ran in sync mode)"
- This violates the single-owner principle — if prefill runs synchronously (`ctx_omni->async = false`), the thread is never created in `stream_prefill` (it's inside the `if (ctx_omni->async)` block), so `stream_decode` catches it
- However, with the current code: `ctx_omni->async` is unconditionally `true` at line 5258, so site 2 is **dead code for the server path**
- Risk: If a CLI path or future code path sets `ctx_omni->async = false`, site 2 activates — creating a thread in `stream_decode` while the SSE callback holds no mutex (see server-omni.cpp decode handler which releases mutex before SSE)

**Verdict: Dual owner — but site 2 is dead code in current server configuration.** Still violates single-owner principle.

### 2.3 T2W Thread — DUAL OWNER ❌

**Creation site 1:** `stream_prefill` line 11936:
```cpp
if (ctx_omni->use_tts && ctx_omni->t2w_thread_info && !ctx_omni->t2w_thread.joinable()) {
    t2w_thread_running = true;
    ctx_omni->t2w_thread = std::thread(t2w_thread_func, ctx_omni, ctx_omni->params);
}
```

**Creation site 2:** `stream_decode` line 12170:
```cpp
if (!ctx_omni->t2w_thread.joinable() && ctx_omni->use_tts && ctx_omni->t2w_thread_info) {
    t2w_thread_running = true;
    ctx_omni->t2w_thread = std::thread(t2w_thread_func, ctx_omni, ctx_omni->params);
}
```

**Same pattern as TTS — dual owner, site 2 is dead code in server mode.**

---

## 3. State Variable Audit

### 3.1 Global State Variables

| Variable | Type | Line | Initialized | Written By | Read By |
|---|---|---|---|---|---|
| `prefill_done` | **`bool` (NOT atomic!)** | 4498 | `true` | LLM thread (5834, 5987), stream_decode (12180) | stream_decode (12179 via g_decode_cv) |
| `llm_thread_running` | `std::atomic<bool>` | 4504 | `true` | stream_prefill (11914), omni_stop_threads (5397), omni_prepare_for_reuse (5525), omni_free (5598) | LLM thread wait (5812, 5816) |
| `tts_thread_running` | `std::atomic<bool>` | 4505 | `true` | stream_prefill (11921-11930 area), stream_decode (12159-12166 area), omni_stop_threads (5398), omni_prepare_for_reuse (5533), omni_free (5605) | TTS thread wait |
| `t2w_thread_running` | `std::atomic<bool>` | 4506 | `true` | stream_prefill (11935), stream_decode (12169), omni_prepare_for_reuse (5552), omni_free (5616) | T2W thread wait |

### 3.2 Critical Finding: `prefill_done` is NOT atomic

```cpp
bool prefill_done = true;  // line 4498 — PLAIN bool, NOT std::atomic<bool>
```

**Writers:**
- LLM thread sets to `false` at line 5834 (prefill continuing)
- LLM thread sets to `true` at line 5987 (prefill complete, need_speek)
- `stream_decode` sets to `false` at line 12180 (after wait returns)

**Reader:**
- `stream_decode` at line 12179 via `g_decode_cv.wait(lock, []{ return prefill_done; })`

**Protection analysis:**
- The `g_decode_cv.wait` holds `ctx_omni->llm_thread_info->mtx` during the check
- But the LLM thread writes to `prefill_done` WITHOUT holding that mutex
- A `bool` read/write is typically atomic on most architectures, but this is not guaranteed by the C++ standard
- Recommendation: Change to `std::atomic<bool>` with appropriate memory ordering

---

## 4. Join Lifecycle Audit

### 4.1 Join Sites

| Function | LLM Join | TTS Join | T2W Join | Notes |
|---|---|---|---|---|
| `omni_prepare_for_reuse` (line 5520-5582) | line 5530 | line 5538 | line 5557 | Guarded by `joinable()`. Drains queues AFTER joins. |
| `omni_free` (line 5585-5640) | line 5601 | line 5608 | line 5617 | Guarded by `joinable()`. Drains queues after joins. |

### 4.2 Join Order

In both `omni_prepare_for_reuse` and `omni_free`:
```
1. duplex_stop_threads(ctx_omni)        — duplex encoder + LLM
2. llm_thread_running = false; join LLM
3. tts_thread_running = false; join TTS
4. T2W drain (signal EOS, wait)
5. t2w_thread_running = false; join T2W
```

**Join order analysis:**
- LLM joined first — correct, because TTS consumes LLM output
- TTS joined before T2W — correct, because T2W consumes TTS output
- `duplex_stop_threads` called before all joins — correct, duplex threads are upstream of simplex threads
- `joinable()` guard on every join — prevents double-join

**Verdict: Join order is correct. Double-join prevented by `joinable()` checks.**

---

## 5. Thread Start Guard Analysis

### 5.1 Current Guards

All thread creation sites use `!ctx_omni->X_thread.joinable()` as the guard:
```cpp
if (!ctx_omni->X_thread.joinable()) {
    // create thread
}
```

**This is a weak guard:**
- `joinable()` returns `true` if the thread object is associated with an active thread
- It returns `false` if: never created (`default-constructed`), already joined, or moved-from
- The guard works correctly for double-start prevention because:
  1. First call: `joinable() == false` → creates thread → `joinable() == true`
  2. Second call: `joinable() == true` → skips creation ✓

**But:** After `join()`, `joinable()` returns `false` again. If `stream_prefill` is called after a join (e.g., in `omni_prepare_for_reuse` → new `omni_init`), the guard correctly allows re-creation.

**Verdict: `joinable()` guard is sufficient for double-start prevention**, though a formal state enum would be more explicit and debuggable.

---

## 6. Double-Owner Risk Assessment

### 6.1 TTS Thread — Risk Scenario

```
Path A (async=true, normal server):
  stream_prefill creates TTS → stream_decode sees joinable()==true → skips ✓

Path B (async=false, CLI or modified):
  stream_prefill skips TTS → stream_decode sees joinable()==false → creates TTS
  This works, but: stream_decode runs in SSE callback thread with NO mutex on ctx_omni
  If omni_free is called concurrently from omni_init handler → race on tts_thread
```

### 6.2 Current Mitigation

In practice, `ctx_omni->async` is unconditionally `true` (line 5258), so site 2 is dead code for all current paths. **This is an accidental safety property**, not a designed one.

---

## 7. Proposed State Machine (as specified by user)

```
                 ┌──────────────────────────────────────────────┐
                 │         THREAD STATE MACHINE                  │
                 │  (per thread: LLM / TTS / T2W)                │
                 └──────────────────────────────────────────────┘

  NOT_STARTED ──→ STARTING ──→ READY ──→ RUNNING ──→ DRAINING ──→ JOINED
       │              │           │          │            │            │
       │              │           │          │            │            │
       └─ initial     └─ thread   └─ thread  └─ normal   └─ stop     └─ after
          state           obj         func       op        signal       join()
                         created      entered              sent, queue
                                                            draining

  Transitions:
    NOT_STARTED → STARTING : single owner calls create_thread()
    STARTING    → READY    : thread_func confirms init complete
    READY       → RUNNING  : first work item dequeued
    RUNNING     → DRAINING : llm_thread_running = false
    DRAINING    → JOINED   : thread.join() returns

  Enforced rules:
    - NOT_STARTED → STARTING: exactly ONE call site (single owner)
    - STARTING guard: must check state == NOT_STARTED (not joinable())
    - DRAINING → JOINED: must happen after thread_func returns
    - JOINED → NOT_STARTED: only allowed via omni_free + omni_init cycle
```

---

## 8. Findings Summary

| Finding | Severity | Status |
|---|---|---|
| **LLM thread has single owner** | — | ✅ CONFIRMED |
| **TTS thread has dual owner** (stream_prefill + stream_decode) | MEDIUM | ❌ Site 2 is dead code in server mode but violates principle |
| **T2W thread has dual owner** (stream_prefill + stream_decode) | MEDIUM | ❌ Same as TTS |
| **Duplex threads have single owner** | — | ✅ CONFIRMED |
| **`prefill_done` is plain bool, not atomic** | LOW | ⚠️ Works in practice but violates C++ standard |
| **`joinable()` guard prevents double-start** | — | ✅ Sufficient but implicit |
| **Join order is correct** (LLM→TTS→T2W) | — | ✅ CONFIRMED |
| **Double-join prevented** by `joinable()` checks | — | ✅ CONFIRMED |
| **No formal thread state machine** | LOW | ⚠️ Would improve debuggability |

---

## 9. Recommendations

### Immediate (safe, no behavioral change):
1. **Change `prefill_done` to `std::atomic<bool>`** with `std::memory_order_acquire/release`
2. **Remove dead TTS/T2W creation sites from `stream_decode`** — they are unreachable with `ctx_omni->async = true` and create confusion

### Deferred (requires testing):
3. **Define formal thread state enum** per the state machine above
4. **Add `assert(state == NOT_STARTED)` before thread creation** as defense-in-depth
5. **Add thread startup logging** with state transitions for debugging

### NOT Recommended:
- Moving thread start back after the label — fix-2 already correctly places thread start AFTER save+label, ensuring both MISS and HIT paths create threads
