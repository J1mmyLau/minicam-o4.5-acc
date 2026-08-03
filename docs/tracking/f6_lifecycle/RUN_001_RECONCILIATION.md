# RUN_001 Reconciliation — Persistent Server Sequential Requests

**Date:** 2026-08-02  
**Script:** `scripts/f6_sequential_repro.py`  
**Binary:** `build-f6-phase3-relwithdebinfo/bin/llama-omni-server`  
**libomni.so:** `9f25d2f7` @ c1d9418  
**Status:** `INVALID_MANUAL_TERMINATION` — cannot be used as stability/failure evidence

## Runner Summary

| Field | Value |
|-------|-------|
| Runner PID | Not recorded (script does not log self-PID) |
| Server PID | 2145552 |
| Server started | Yes |
| Server healthy | Yes |
| omni_init | 3.7s OK |
| Requests completed | 1/10 |
| Last successful request | Request 1 (37.6s) |
| First failed request | Request 2 (600.1s TIMEOUT) |
| Server alive at end | True (poll() returned None) |
| Drain timeouts in log | 0 |
| Manual kill executed | `kill -9 2145552` + `pkill -f "llama-omni-server.*18081"` |

## Per-Request Analysis

| Req | Elapsed | Status | Details |
|-----|---------|--------|---------|
| 1 | 37.6s | OK | Text: "This is the original image.", 0 WAVs generated |
| 2 | 600.1s | TIMEOUT | **Zero server log activity.** No stream_decode print. |
| 3 | 83.6s | Connection closed | Remote end closed connection without response |
| 4-10 | 0.0s | Connection refused | Server not accepting connections |

## Server Log Analysis

### Request 1 Timeline

| Time | Event |
|------|-------|
| 15:57:15.160 | omni_init start |
| 15:57:18.839 | omni_init success, ctx_llama=0xfffddca0f390 |
| 15:57:18.840 | stream_decode start, n_past=0 |
| 15:57:18.841 | TTS + T2W threads created |
| 15:57:21.477 | assistant prompt complete, n_past=10 |
| 15:57:31.178 | First LLM chunk: "This is the original image" (5 tokens) |
| 15:57:35.077 | LLM end token detected, n_past=17 |
| 15:57:35.077 | stream_decode cleanup (round boundary, response unit, F005 stats) |
| 15:57:35.077 | **Server log ENDS** — no drain log, no request 2 log |

### Key Observations

1. **Request 2 has ZERO server log activity.** Not even the `stream_decode 开始` diagnostic at line 13024 of omni.cpp. This is the primary anomaly.

2. **Drain log missing.** The HTTP handler calls `omni_duplex_drain_tts_audio` after `stream_decode`. This function calls `t2w_drain_signal_and_wait` which prints `"T2W drain: waiting up to %dms..."`. This print is NOT in the log — the drain either hung before the print or the print was buffered.

3. **0 WAVs for request 1.** TTS generated audio tokens (3 tokens for chunk 0) and pushed them to the T2W queue. But T2W produced no WAV files. TTS merge step found zero valid chunks.

4. **Server alive but unresponsive.** After request 2 timeout, server process existed (poll()=None) but refused connections. This is a HANG state, not a crash.

5. **F005 stats printed** — confirms `stream_decode` completed normally for request 1.

## Contamination Events

| Event | When | Impact |
|-------|------|--------|
| `kill -9 2145552` | During/after run | Killed server process |
| `kill $(pgrep -f "llama-omni-server.*18081")` | During/after run | May have matched other processes |

These make the run INVALID as stability evidence. The 600s timeout of request 2 is real (it happened before manual kill), but requests 3-10 failures could be due to manual kill, not the server issue.

## Classification

```
RUN_001 = INVALID_MANUAL_TERMINATION
```

- Request 2 hang: **genuine signal** (600s timeout, zero server activity)
- Requests 3-10: **contaminated** (manual kill may have killed server)
- Cannot be used as stability/failure reproduction evidence for requests 3-10

## Open Questions

1. **Why does request 2 produce zero server log activity?** Possible causes:
   - HTTP handler blocked on `octx_mutex` (if request 1's drain holds it — BUT drain doesn't hold the mutex)
   - httplib single-threaded → request 2 handler not called until request 1 handler returns
   - Drain hangs before printing (if T2W worker is stuck)
   
2. **Why does the drain produce no log output?** `t2w_drain_signal_and_wait` prints immediately at entry but this print is absent.

3. **Why 0 WAVs for request 1?** T2W received audio tokens (push to queue) but produced no output files.

4. **Why does server become unresponsive after request 2 timeout?** Process alive but refusing connections.

## Hypothesis

The httplib server is **single-threaded**. After request 1's `stream_decode` returns, the handler calls `omni_duplex_drain_tts_audio` → `t2w_drain_signal_and_wait`. This drain signals EOS to the T2W worker and waits up to 30s (OMNI_T2W_DRAIN_TIMEOUT_MS=30000). 

If the T2W worker is stuck (not responding to the EOS signal), the drain hangs for 30s. Then it times out and the handler returns. But then request 2 should start.

But request 2 gets ZERO log output and times out at 600s... This suggests the drain might hang INDEFINITELY (not 30s timeout), or the httplib handler thread itself is deadlocked.

**Need to verify**: httplib threading model (`svr.new_task_queue` or `svr.listen_after_bind`), and the exact drain timeout behavior.
