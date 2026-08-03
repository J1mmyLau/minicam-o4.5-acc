# L1 Server Call Chain Audit — omni_init/omni_free Per Request

**Date:** 2026-08-02  
**Binary:** `build-f6-phase3-relwithdebinfo/bin/llama-omni-server`

## Server Configuration

```cpp
// server-omni.cpp line 120, 437
httplib::Server svr;                    // default multi-threaded (thread-per-request)
svr.listen("0.0.0.0", params.port);    // default listen, no explicit thread pool config
```

httplib default model: each HTTP request is dispatched to a new thread. Multiple requests can be processed concurrently.

## API Endpoints

| Endpoint | Method | Calls omni_init? | Calls omni_free? | Notes |
|----------|--------|-----------------|------------------|-------|
| `/health` | GET | No | No | Read-only |
| `/v1/health` | GET | No | No | Read-only |
| `/v1/stream/omni_init` | POST | **YES** | **YES** (old ctx) | Creates new omni_context, destroys old |
| `/v1/stream/prefill` | POST | No | No | Uses existing ctx via stream_prefill |
| `/v1/stream/decode` | POST | No | No | Uses existing ctx via stream_decode |

## omni_init Handler (lines 138-221)

```cpp
// Always destroys old context before creating new one
{
    std::lock_guard<std::mutex> lock(state.octx_mutex);
    if (state.octx) {
        omni_free(state.octx);       // DESTROYS old context
        state.octx = nullptr;
    }
}
omni_context * octx = omni_init(&params, ..., nullptr, nullptr, ...);
{
    std::lock_guard<std::mutex> lock(state.octx_mutex);
    state.octx = octx;
}
```

## stream_decode Handler (lines 264-310, non-stream path)

```cpp
{
    std::lock_guard<std::mutex> lock(state.octx_mutex);
    ok = stream_decode(state.octx, debug_dir, round_idx);
} // lock released
// DRAIN OUTSIDE LOCK
if (state.octx->use_tts) {
    omni_duplex_drain_tts_audio(state.octx);   // may block up to 120s
}
```

## L1 Questions and Answers

### Q1: Server启动时omni_init调用几次?
**A: 0.** omni_init is only called by the `/v1/stream/omni_init` POST handler. The server starts without any omni_context.

### Q2: 每个请求是否调用omni_init?
**A: NO (for /v1/stream/decode).** The decode handler only calls `stream_decode` on the existing context. It does NOT call omni_init or omni_free.

The test script `f6_sequential_repro.py` calls omni_init ONCE at startup, then calls decode 10 times. There is NO omni_init between decode requests.

### Q3: 每个请求是否调用omni_free?
**A: NO.** omni_free is only called from the omni_init handler (to destroy old context before creating new) and from the WebSocket close handler.

### Q4: Voice切换是否触发context重建?
**A: NO (in current implementation).** The `voice_audio` parameter is set via omni_init. Voice switch requires a new omni_init call (which destroys old context).

### Q5: KV HIT/MISS是否触发context重建?
**A: NO.** KV cache is managed within stream_decode. HIT/MISS is a cache lookup decision, not a context lifecycle event.

### Q6: session.init是否触发context重建?
**A: N/A.** There is no `/v1/stream/session/init` endpoint. The only context management endpoints are omni_init (create/destroy) and decode (use).

### Q7: 请求结束是否销毁context?
**A: NO.** stream_decode returns to the handler, which drains T2W and returns. The context persists across requests.

### Q8: Server退出时才销毁，还是请求间销毁?
**A:** Context persists across requests. It is only destroyed by:
1. Explicit omni_init call (destroys old, creates new)
2. WebSocket session close
3. Server shutdown (destructors)

## Critical Finding

**The test script `f6_sequential_repro.py` does NOT trigger omni_init/omni_free between requests.** It is MODE_A (context reuse), not MODE_B (context rebuild).

**The hypothesis "omni_init destroys old context while T2W worker still running" does NOT apply to this test.** The issue observed in RUN_001 is a MODE_A issue: same context, same server, sequential decode requests.

## Two Independent Failure Modes

### Mode A: Context Reuse (what the test actually tests)
- One omni_init, N × stream_decode
- stream_decode for request 2 hangs with zero server log activity
- Root cause: unknown (not omni_init/omni_free conflict)

### Mode B: Context Rebuild (hypothesis about lifecycle)
- omni_init → omni_free → omni_init between requests
- Potential: T2W worker accessing freed context
- NOT yet tested or reproduced

## What RUN_001 Actually Tests

```
MODE A: Same omni_context, sequential decode requests, no omni_init between.
```

The hypothesis "omni_init destroys old context" is about MODE B. The script is testing MODE A. These are two different failure modes.

## Next Steps

1. Create MODE_A reproduction harness (context reuse) — clean, with proper logging
2. Create MODE_B reproduction harness (context rebuild) — explicit omni_init between requests  
3. Run both, with lifecycle event instrumentation
4. Determine which mode(s) fail and why
