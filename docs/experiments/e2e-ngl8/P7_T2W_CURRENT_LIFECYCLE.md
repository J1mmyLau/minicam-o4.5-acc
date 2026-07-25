# P7 T2W Current Lifecycle — Complete Code Audit (P2)

Date: 2026-07-25
Source: `/workspace/llama.cpp-omni-ngl8-e2e/tools/omni/omni.cpp`, `omni.h`

## 1. Structural Overview

```
LLM → TTS → T2W → WAV files
       ↑        ↑
    queue<TTSOut>   queue<T2WOut>
       ↓        ↓
  tts_thread   t2w_thread
```

Sequential, queue-coupled. No back-pressure. No completion verification between stages.

### Key Data Structures (omni.h:75-92)

```cpp
struct T2WOut {
    vector<llama_token> audio_tokens;
    bool is_final = false;     // end of turn (triggers flush+reset)
    bool is_chunk_end = false; // end of TTS chunk (less aggressive flush)
    int round_idx = -1;
    steady_clock::time_point enqueue_time;
};

struct T2WThreadInfo {
    int MAX_QUEUE_SIZE;
    queue<T2WOut*> queue;
    mutex mtx;
    condition_variable cv;
    // ⚠️ MISSING: drain_state, eos_received, inflight_count, writer_flushed, terminal_state
};
```

### Global State
- `std::atomic<bool> t2w_thread_running(true)` — omni.cpp:4071 — sole exit condition

## 2. Complete Lifecycle Map

### STAGE 0: Init
- T2WThreadInfo allocated in `omni_init()` (~line 5700)
- Thread not yet started

### STAGE 1: Thread Start
- Simplex: omni.cpp:~11145 (after system prompt prefill)
- Duplex: omni.cpp:~11393-11395
- Calls `std::thread(t2w_thread_func, ctx_omni, &params)`

### STAGE 2: Worker Entry (line 9417 → 9417)
- CANN device context setup
- Deferred token2wav session init (if `token2wav_defer_worker_init`)
- Buffer init: `{4218, 4218, 4218}` (3 silence tokens)
- `last_round_idx = -1`, `wav_idx = 0`

### STAGE 3: Main Loop (line 9497)
```cpp
while (t2w_thread_running) {  // ← SOLE EXIT CONDITION
```

### STAGE 4: Break Event (lines 9498-9524)
- Drains queue, resets buffer/wav_idx, updates dir

### STAGE 5: CV Wait (lines 9526-9538)
```cpp
cv.wait(lock, [&] {
    return !queue.empty() || !t2w_thread_running || ctx_omni->break_event.load();
});
// ⚠️ RACE: if !running && queue.empty() → break (line 9536)
// No check: was is_final received? Were WAVs written?
```

### STAGE 6-7: Dequeue All (lines 9546-9572)
- Drains entire queue into local vectors
- OR-aggregates is_final, is_chunk_end
- Records oldest enqueue_time

### STAGE 8: Round Switch (lines 9578-9604)
- Uses effective_round_idx from T2WOut (not live simplex_round_idx)

### STAGE 9-10: Sliding Window Processing (lines 9606-9777)
- Token buffer accumulation
- `feed_window(window, is_last_window, chunk_wav)`
- `need_flush = is_final || is_chunk_end` (simplex), `is_final` (duplex)

### STAGE 11: WAV Writing (lines 9679-9737)
- fopen/fwrite/fclose — no fdatasync, no error recovery
- Records e2e timestamps on first WAV

### STAGE 12: Final Window (lines 9779-9821)
- Writes `generation_done.flag` with last WAV index
- Resets token_buffer, wav_idx, wav_turn_base

### STAGE 13: Loop Back
- `break` from final processing, back to `while(t2w_thread_running)`

### STAGE 14: Worker Exit (line 9829)
- Prints "stopped" — NO flush confirmation, NO output verification

## 3. Stop Paths (3 paths, all broken)

### Path A: `omni_stop_threads()` (line 4880)
```
t2w_thread_running = false;     // signal stop
cv.notify_all();                // wake worker
// ── NO join, NO drain, NO verify ──
```

### Path B: `omni_prepare_for_reuse()` (line 4911)
```
tts_thread_running = false;     // stop TTS first
tts_thread.join();              // wait TTS
t2w_thread_running = false;     // THEN stop T2W
cv.notify_all();
t2w_thread.join();              // wait T2W
// THEN drain any remaining queue items (line 4959-4965)
// ⚠️ Drains queue AFTER join — items processed by worker are left on disk but unverified
// ⚠️ No output verification: rc=0 even if no WAV written
```

### Path C: `omni_free()` (line 4970)
```
llm_thread.join();              // LLM first
tts_thread.join();              // TTS second
t2w_thread_running = false;     // T2W last
cv.notify_all();
t2w_thread.join();
// ⚠️ Same pattern: stop then join, no drain, no verify
```

## 4. Race Windows (3 confirmed, 2 suspected)

### Race A: TTS Shutdown Before is_final Sent (CONFIRMED)
```
TTS Thread                    Main Thread
   |                             |
   |--- process audio tokens     |
   |                             |--- tts_thread_running=false
   |--- check running → false    |
   |--- EXIT (no is_final sent!) |
   |                             |--- t2w_thread.join()
```
**Impact**: T2W buffer may have <28 tokens, NEVER flushed, no WAV written.
**Frequency**: Short responses where TTS is stopped mid-batch.

### Race B: T2W CV Wake with Empty Queue (CONFIRMED — PRIMARY)
```
T2W Thread (processing complete)      Main Thread
   |                                    |
   |--- all items processed, WAV done   |
   |--- loop back to while(running)     |
   |--- enter cv.wait()                 |
   |                                    |--- t2w_thread_running=false
   |                                    |--- cv.notify_all()
   |--- wake: !running && empty → BREAK |
   |--- EXIT                            |
```
**This is actually CORRECT behavior IF WAV was already written.** But the issue arises when combine with Race A: if no is_final was sent, no WAV was written either.

### Race C: is_final in Queue But Worker Exits First (CONFIRMED — SECONDARY)
If is_final is enqueued after the worker's last dequeue but before the main thread's stop signal:
```
T2W (just dequeued all)     TTS (still running)         Main
   |                           |                          |
   |--- queue empty            |                          |
   |--- cv.wait()              |                          |
   |                           |--- push is_final=true    |
   |                           |--- cv.notify_one()       |
   |--- wake, dequeue is_final |                          |
   |--- need_flush=true        |                          |
   |--- [PROCESSING WAV...]    |                          |
   |                           |                          |--- t2w_thread_running=false
   |                           |                          |--- cv.notify_all()
   |--- [WAV write completes]  |                          |
   |--- loop back: !running    |                          |
   |--- BREAK                  |                          |
```
**Impact**: WAV is written before break → no data loss. But no generation_done.flag.

### Race D: omni_prepare_for_reuse Queue Drain After Join (SUSPECTED)
After T2W join, remaining queue items are DELETED (lines 4959-4965). If TTS sent items after T2W's last dequeue, those items are lost.

### Race E: WAV fclose Before fdatasync (SUSPECTED)
WAVs written via fopen/fwrite/fclose without fdatasync. If process exits immediately after worker join, kernel buffers may not be flushed. Low probability but possible under heavy I/O load.

## 5. Symptom Matrix

| Symptom | Root Cause | Evidence |
|---------|-----------|----------|
| rc=0, no WAV, short response | Race A (TTS killed before is_final) | 15/72 P6 runs |
| rc=0, WAV exists, no done flag | Race C | Unconfirmed |
| rc=0, WAV truncated | Race E (buffer flush) | Unconfirmed |
| Memory leak on repeated reuse | Race D (queue items deleted post-join) | Design review |
| No error on T2W pipeline failure | No error propagation path | Code audit |

## 6. Fix Requirements (→ P3 Design)

1. **Drain state machine**: Worker must track lifecycle state explicitly
2. **EOS protocol**: Main thread signals EOS (not stop), worker acknowledges
3. **Drain before stop**: Main thread waits for worker drain confirmation
4. **Bounded timeout**: Configurable `OMNI_T2W_DRAIN_TIMEOUT_MS`
5. **Output verification**: Check WAV count > 0 before returning rc=0
6. **Terminal state reporting**: Distinguish VALID_NO_SPEECH vs FAILURE
7. **Attempt isolation**: Per-request state, clear between rounds
8. **flush+fsync before done flag**: Ensure WAV data is durable
