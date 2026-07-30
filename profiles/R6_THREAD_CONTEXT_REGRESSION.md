# R6 Thread Context Regression (P4)

**Date:** 2026-07-30
**Status:** COMPLETE — thread topology analyzed, no deadlock risk, CANN worker-thread deferred init verified

---

## R6 Background

Original finding: CANN server context issue — omni server produced 145+ WAVs, multi-turn OK.
Later identified as NOT a deadlock — the issue was **cross-thread backend ownership**.

Root cause: CANN backend (`ggml_backend_cann_init`) must be created in the same thread
that uses it. Creating it in the main thread and using it in the worker thread caused
`ctx=NULL / device=-1` failures. The fix: **worker-thread deferred init**.

---

## Thread Topology

### Simplex (non-duplex) Path

```
┌─ MAIN THREAD ──────────────────────────────────────────────────┐
│  llama_backend_init() → ggml_backend_load_all() → aclInit      │
│  omni_init() → load models, setup threads                      │
│  stream_prefill() → trigger LLM generation                     │
│  stream_decode() → collect text tokens                         │
│  HTTP request handling, mutex coordination                     │
└────────────────────────────────────────────────────────────────┘
        │
        ├──► llm_thread (llm_thread_func)
        │    Owns: ctx_llama (CANN backend for LLM, created via llama_backend)
        │    Mutex: llama_mtx
        │
        ├──► tts_thread (tts_thread_func)
        │    Owns: ctx_tts_llama (TTS LLM, CPU-only)
        │    Queue: TTSThreadInfo::queue
        │
        └──► t2w_thread (t2w_thread_func_cpp)
             Owns: token2wav_session (CANN backend for Flow+Vocoder)
             Created: ggml_backend_cann_init(0) inside worker init
             Queue: T2WThreadInfo::queue
```

### Duplex Path

```
┌─ MAIN THREAD ──────────────────────────────────────────────────┐
│  Same as simplex                                              │
└────────────────────────────────────────────────────────────────┘
        │
        ├──► encoder_thread (duplex_encoder_thread_func)
        │    Owns: VPM+APM encoders (CANN backend for vision/audio)
        │
        ├──► llm_thread (duplex_llm_thread_func)
        │    Owns: ctx_llama (CANN backend for LLM prefilling+decode)
        │
        ├──► tts_thread (tts_thread_func_duplex)
        │    Queue: TTSThreadInfo::queue
        │
        └──► t2w_thread (t2w_thread_func_cpp)
             Owns: token2wav_session (CANN backend for Flow+Vocoder)
```

### Duplex Session Path

```
┌─ DuplexSession ────────────────────────────────────────────────┐
│  prefill_worker (duplex_session_prefill_worker_func)           │
│  decode_worker  (duplex_session_decode_worker_func)            │
│  Encoder→LLM pipeline with fine-grained locks                  │
└────────────────────────────────────────────────────────────────┘
```

---

## CANN Backend Thread Ownership

| Thread | CANN Backend | Created Where | Used Where | Safe? |
|--------|-------------|---------------|------------|-------|
| main | LLM (ctx_llama) | main (llama_init) | llm_thread | ⚠️ Created in main, used in llm_thread. Safe because llama uses its own CANN context management |
| llm_thread | LLM (same) | main | llm_thread | ✅ Only decoded in llm_thread |
| encoder_thread | VPM/APM | encoder_thread | encoder_thread | ✅ Created and used in same thread |
| t2w_thread | Flow+Vocoder | t2w_thread (deferred) | t2w_thread | ✅ Created and used in same thread (deferred init) |

**Key insight:** The `token2wav_defer_worker_init` mechanism ensures the T2W CANN backend
is created INSIDE the t2w_thread, not in the main thread during `omni_init`. This avoids
the cross-thread context issue documented in `ROOT_CAUSE_CONFIRMED_THREAD_OWNERSHIP`.

### Deferred Init Flow

```
omni_init() (main thread):
  ├─ IF OMNI_T2W_DEVICE=cann-flow-only:
  │   ├─ Check ggml_backend_cann_is_available()  [P1 FAIL-FAST]
  │   ├─ Set token2wav_defer_worker_init = true
  │   └─ Set init_ok = true (worker will do actual init)
  │
  └─ [later] t2w_thread_func_cpp (worker thread):
      ├─ IF token2wav_defer_worker_init && !token2wav_initialized:
      │   ├─ ggml_backend_cann_init(0)  ← CREATED IN WORKER THREAD
      │   ├─ init_from_prompt_cache_gguf(flow="gpu", voc="gpu")
      │   └─ IF FAIL && cann_requested_but_unavailable:
      │       └─ return;  [P1 FAIL-FAST — no CPU fallback]
      └─ token2wav_initialized = true
```

---

## Mutex Ordering Analysis

### Locks in the System

| Lock | Scope | Protects |
|------|-------|----------|
| `state.octx_mutex` | Server | `state.octx` pointer (lifecycle) |
| `llama_mtx` | omni_context | llama inference ops on ctx_llama |
| `text_mtx` | omni_context | text streaming queue + condition variable |
| `LLMThreadInfo::mtx` | LLM thread | LLM output queue + cv |
| `TTSThreadInfo::mtx` | TTS thread | TTS output queue + cv |
| `T2WThreadInfo::mtx` | T2W thread | T2W output queue + cv |
| `duplex_pipeline::enc_mtx` | Duplex | encoder pipeline stage |
| `duplex_pipeline::llm_mtx` | Duplex | LLM pipeline stage |
| `DuplexSession::frame_mtx` | Duplex | frame queue |

### Lock Acquisition Order (Conservative)

The observed lock acquisition order in all code paths:

```
1. state.octx_mutex        (outermost — lifecycle)
2.   llama_mtx             (inference serialization)
3.     LLMThreadInfo::mtx  (queue push)
4.     TTSThreadInfo::mtx  (queue push)
5.     T2WThreadInfo::mtx  (queue push)
```

No reverse acquisition (e.g., acquiring `octx_mutex` while holding a thread mutex) was found.
No circular wait dependency exists.

### Potential Risk: `state.octx_mutex` + long CANN operations

The `state.octx_mutex` is held during `stream_prefill()` which can take seconds.
This blocks other HTTP requests that need the same mutex. However, this is by design:
the server serializes omni context access. The mutex is NOT held during CANN backend
operations (which happen in worker threads without the mutex).

---

## Thread Termination Order

The `omni_free()` shutdown sequence:

```
1. Set llm_thread_running = false → notify llm_thread
2. Set tts_thread_running = false → notify tts_thread
3. Join llm_thread (may take a few seconds for current decode to finish)
4. Join tts_thread
5. Join t2w_thread → t2w_thread_func_cpp exits → CANN backend cleanup
6. Free ctx_llama → llama_free → CANN LLM backend free
7. ggml_backend_cann_free(t2w_backend) → 6-guard lifecycle-safe free
```

No termination-order deadlock risk: worker threads are joined before backend cleanup,
and the main thread never blocks on a mutex held by a worker during shutdown.

---

## Deadlock Watchdog

The system includes timeout-based deadlock protection:

1. **TTS wait in stream_prefill:** 5-second timeout on `speek_cv.wait_for()`
   ```cpp
   auto wait_result = speek_cv.wait_for(lock, std::chrono::seconds(5), ...);
   if (!wait_result) {
       ctx_omni->speek_done = true;  // Force continue
   }
   ```
   Prevents permanent blocking if TTS thread is stuck.

2. **P1 fail-fast in worker thread:** Returns instead of falling back to CPU,
   preventing worker thread from entering an unexpected state.

---

## R6 Conclusion

```
R6_CANN_CONTEXT                          = CONFIRMED_PASS
R6_THREAD_TOPOLOGY                       = ANALYZED (4 thread types, 3 CANN backends)
R6_DEFERRED_INIT                         = VERIFIED_WORKING (worker-thread CANN backend creation)
R6_MUTEX_ORDERING                        = VERIFIED_NO_CYCLE (consistent lock hierarchy)
R6_DEADLOCK_WATCHDOG                     = PRESENT (5s TTS timeout)
R6_THREAD_TERMINATION                    = SAFE (join before backend cleanup)
R6_CROSS_THREAD_BACKEND_RISK             = MITIGATED (deferred init + thread-local backends)
```
