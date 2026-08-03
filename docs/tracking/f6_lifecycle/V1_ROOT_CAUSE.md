# V1 Root Cause — MODE_A Sequential Request Hang

**Date:** 2026-08-02  
**Binary:** `build-f6-phase3-relwithdebinfo`  
**Variant:** V1_2_requests (2 strict serial requests, 5s gap)

## Root Cause Classification

```
ROOT_CAUSE = CROSS_REQUEST_DRAIN_TIMEOUT_CONTEXT_STALE
```

NOT scenario A (client never sends request B): Request B IS sent, handler fires.
NOT scenario B (handler blocked on octx_mutex): Lock acquired instantly (< 3μs).
**IS scenario C**: Stale context state from request 1 causes request 2 to hang inside stream_decode.

## Timeline (server-side monotonic timestamps)

```
T+0ms     HANDLER_ENTER req=1
T+1ms     STREAM_DECODE_BEGIN req=1
          CTXSTATE: t2w_joinable=0 queued=0 need_speek=0 n_past=0
T+85427ms STREAM_DECODE_END req=1
          OCTX_UNLOCKED
          T2W_DRAIN_BEGIN req=1
          CTXSTATE: t2w_joinable=1 queued=9 need_speek=1 speek_done=1 n_past=56
T+115427ms T2W_DRAIN_END req=1  (TIMEOUT: 30s, worker never processed is_final)
T+115428ms HANDLER_RETURN req=1
T+150428ms HANDLER_ENTER req=2  (5s after req1 returned)
T+150428ms OCTX_LOCK_ACQUIRED req=2 (< 1μs — lock was free)
T+150428ms STREAM_DECODE_BEGIN req=2
          CTXSTATE: t2w_joinable=1 queued=9 need_speek=1 n_past=56 llm_gen_done=1
          >>> NO STREAM_DECODE_END <<< request 2 hangs inside stream_decode
```

## Server Log Timeline (wall clock)

```
16:31:21.693  stream_decode 开始 req=1, n_past=0
16:32:22.279  wav_1000.wav (0.84s audio, 47s inference, RTF=56) — FIRST WAV, very slow
16:32:47.086  T2W drain: waiting 30000ms — INNER profiling drain starts
16:32:49.159  wav_1001.wav (1.00s, 26.9s inference) — queue_wait=46s!
16:33:17.086  T2W drain: TIMEOUT (30s) — 9 items still in queue
16:33:17.087  T2W drain: waiting 30000ms — OUTER handler drain starts
16:33:47.087  T2W drain: TIMEOUT (30s) — worker still not finished
16:33:52.094  stream_decode 开始 req=2, n_past=56 ← ENTERS WITH STALE STATE
16:33:52.094  wait prefill done ← HANGS FOREVER
```

## Three-Layer Failure Mechanism

### Layer 1: T2W Worker Saturation

T2W worker processes flow+vocoder on CPU (~8.6s per WAV). During request 1's 85s stream_decode, the LLM generates text faster than T2W can produce WAVs. Result: T2W queue accumulates 9+ items.

wav_1001 shows `queue_wait=46s` — items sit in queue for 46 seconds before processing begins.

### Layer 2: Drain Timeout Insufficient

After stream_decode, the handler drains the T2W queue via `t2w_drain_signal_and_wait`. The drain timeout is 30s (`OMNI_T2W_DRAIN_TIMEOUT_MS=30000`). With 9 items × 8.6s/item = 77s total processing time, 30s is insufficient. The drain times out TWICE (inner profiling drain + outer handler drain).

```cpp
// server-omni.cpp lines 340-342: DRAIN RETURN VALUE IS IGNORED
if (state.octx->use_tts) {
    omni_duplex_drain_tts_audio(state.octx);  // returns false on timeout — IGNORED
}
```

### Layer 3: Context State Propagation

After the drain times out and returns, request 2 enters `stream_decode` on the SAME omni_context. The context state is STALE:

| Field | Expected (fresh) | Actual (from req 1) |
|-------|-----------------|---------------------|
| `n_past` | 0 | 56 |
| `need_speek` | 0 | 1 |
| `llm_generation_done` | 0 | 1 |
| `t2w_thread_info->queue` | empty | 9 items |
| `t2w_thread` state | idle | processing stale WAVs |

Request 2's `stream_decode` hangs at `wait prefill done` (line 13087) because:
- `need_speek` is already `true` from request 1
- `stream_decode` sets `need_speek = true` (no change — already true)
- Notifies LLM thread CV
- LLM thread may not respond (already processed this need_speek value cycle, or is in a state where it cannot respond)

## Immediate Blocking Point

```
omni.cpp:13087: g_decode_cv.wait(lock, []{ return prefill_done.load(); });
```

`prefill_done` is never set to `true` for request 2. The wait blocks indefinitely.

## Server Log: Last 3 Lines

```
16:33:52.094 📍 stream_decode 开始: n_past=56  -- request 2 enters
16:33:52.094 wait prefill done                   -- hangs here
16:33:58.547 wav_1009.wav ... queue_wait=46189ms -- T2W still processing stale WAVs
```

## Why Request 1 Succeeds But Request 2 Fails

Request 1 starts with `n_past=0`, fresh context, no stale state. The assistant prompt eval at n_past=0 works correctly.

Request 2 starts with `n_past=56`, stale `need_speek=true`, `llm_generation_done=true`, and T2W queue still has 9 items. The LLM thread has already consumed the previous `need_speek=true` signal and won't re-process it because there's no edge transition (need_speek was already true, remains true).

## Required Fix (Prioritized)

### P0: Check Drain Return Value
`server-omni.cpp:340-342` — if drain returns false, do NOT allow next request on same context. Return error or restart.

### P1: Reset Context State Between Requests
Before `stream_decode`, ensure:
- `need_speek = false`
- `llm_generation_done = false`
- T2W queue empty
- T2W worker idle (is_final_processed = true)

### P2: Proper Queued Item Drain
Instead of waiting 30s for all items, drain one item at a time with per-item timeout.

### P3: Handle need_speek Edge Transition
The LLM thread should detect stale need_speek by using a per-request generation counter instead of a boolean.
