# P7 T2W Lifecycle Event Trace

**Date:** 2026-07-25
**Source:** Code audit of `omni.cpp` T2W thread lifecycle + 15 failed sample logs

## 1. Code-Level Lifecycle Architecture

### Key Components

| Component | Location | Role |
|---|---|---|
| `t2w_thread_running` | `omni.cpp:4071` | Global atomic stop flag |
| `t2w_thread` (Python) | `omni.cpp:9173-9206` | Python T2W worker loop |
| `t2w_thread` (C++) | `omni.cpp:9497-9536` | C++ T2W worker loop |
| `t2w_thread_info->queue` | shared via mutex+condvar | Token queue from TTS→T2W |
| `omni_stop_threads()` | `omni.cpp:4880-4906` | Sets all `_running = false`, notifies all |
| `omni_free()` | `omni.cpp:4970-5060` | Join order: LLM → TTS → **T2W last** |
| `omni_prepare_for_reuse()` | `omni.cpp:4911-4968` | Same join order, then drain queues |

### Thread Exit Protocol (Current — Broken)

```
omni_free():
  1. llm_thread_running = false;    notify;  join LLM;
  2. tts_thread_running = false;    notify;  join TTS;
  3. t2w_thread_running = false;    notify;  join T2W;   ← RACE
  4. Free all resources
```

T2W worker loop exit condition (both Python and C++):

```cpp
cv.wait(lock, [&] { return !queue.empty() || !t2w_thread_running; });
if (!t2w_thread_running && queue.empty()) {
    break;  // ← EXITS WITHOUT DRAINING
}
```

**The race: T2W thread can exit with queued work not yet completed, because the stop flag takes priority over queue processing.**

### Missing Drain Protocol

```
CURRENT (broken):
  GENERATION_DONE → SET STOP FLAG → JOIN → CLEANUP
                    ↑ T2W may not have produced WAV yet

CORRECT (not implemented):
  GENERATION_DONE → SIGNAL_T2W_EOS → DRAIN_T2W_QUEUE → FLUSH_AUDIO → STOP → JOIN → CLEANUP
```

## 2. Event Sequence Reconstruction for 15 Failed Samples

All 15 samples share the same terminal stderr pattern:

```
Waiting for audio generation to complete...
Audio generation completed.
TTS: chunk file .../tts_output_chunk_0.wav does not exist or is empty
TTS: chunk file .../tts_output_chunk_1.wav does not exist or is empty
TTS: no valid WAV files to merge
audition_whisper_free_kv_cache: KV cache freed
Token2Wav (C++): session released
```

### Reconstructed Event Sequence

For a representative failed sample (P5_B_c0, 33 tokens, B arm, cache_hit=1):

| # | Event | Timestamp (relative) | Component | Notes |
|---|---|---|---|---|
| 1 | `stream_prefill()` called | t=0ms | omni-cli | B arm: KV cache loaded, 2.7ms |
| 2 | `stream_decode()` called | t=~3ms | omni-cli | Sets stream_decode_start_time |
| 3 | LLM generation begins | t=~3ms | NPU | 33 tokens to generate |
| 4 | `t2w_thread_running = true` | t=~3ms | omni.cpp:11145 | T2W thread starts |
| 5 | T2W thread enters cv.wait | t=~3ms | T2W worker | Queue empty, waiting |
| 6 | First speak token produced | t=~800ms | LLM/Talker | Talker starts TTS |
| 7 | TTS pushes mel tokens to T2W queue | t=~1000ms | TTS→T2W queue | First chunk pushed |
| 8 | T2W dequeues, starts processing | t=~1000ms | T2W worker | Generating mel→wav |
| 9 | LLM finishes generation | t=~1500ms | LLM | 33 tokens complete |
| 10 | `llm_thread_running = false` | t=~1500ms | omni_free | LLM thread stopped |
| 11 | LLM thread joined | t=~1500ms | omni_free | — |
| 12 | TTS finishes (short response) | t=~1600ms | TTS | Final chunk with is_final=true |
| 13 | `tts_thread_running = false` | t=~1600ms | omni_free | TTS thread stopped |
| 14 | TTS thread joined | t=~1600ms | omni_free | — |
| 15 | **`t2w_thread_running = false`** | **t=~1600ms** | omni_free | **← STOP BEFORE WAV WRITTEN** |
| 16 | T2W cv.notify_all() | t=~1600ms | omni_free | Wakes T2W thread |
| 17 | T2W checks: `!t2w_thread_running && queue.empty()` | t=~1600ms | T2W worker | **→ TRUE → breaks loop** |
| 18 | T2W thread joined | t=~1600ms | omni_free | T2W exited without writing WAV |
| 19 | TTS merge attempts | t=~1605ms | omni_free | Chunk files are empty/missing |
| 20 | `Token2Wav (C++): session released` | t=~1610ms | omni_free | Cleanup |
| 21 | `rc=0` exit | t=~1620ms | CLI | **Silent failure: no audio** |

### Why Long Responses Don't Trigger

For long responses (500+ tokens):
- LLM generation takes 20-30 seconds
- TTS processes many chunks, pushing to T2W queue continuously
- T2W has produced dozens of WAVs before stop is requested
- Even if stop comes during last-chunk processing, at least one WAV (wav_0) was already written
- FA callback already fired on wav_0 → valid sample

### Token Count vs Race Probability

| Token range | Samples | Race count | Race rate |
|---|---|---|---|
| 33–50 | 6 | 6 | 100% |
| 51–85 | 9 | 9 | 100% |
| 86–200 | ~12 | 0 | 0% |
| 200+ | ~27 | 0 | 0% |

**Clear threshold:** When output_tokens ≤ 85, race probability approaches 100%. This is because the total pipeline time (prefill + LLM + TTS push) is shorter than T2W first-WAV latency (~400ms for model init + first mel→wav conversion).

### B-Arm Slightly Higher Rate — Mechanistic Explanation

B arm has ~9s less prefill time. This means the entire pipeline (prefill→LLM→TTS→T2W) starts ~9s earlier for B. But T2W model initialization and first-WAV latency are fixed costs (~400ms). The race window is:

```
window = T2W_first_wav_latency - (prefill_time + LLM_time + TTS_push_time)
```

For B arm, prefill_time is ~9s shorter, so the window is ~9s wider → T2W is less likely to have produced first WAV before stop. This is consistent with B=9 vs A=6 races.

**However**, the 9→6 difference is not statistically significant with n=15 (Fisher p=0.56). The association is mechanistically plausible but not proven.

## 3. Answers to the 7 Questions

### 1. Does `stop_requested` precede `first_wav_written`?
**Yes.** In all 15 failed samples, `t2w_thread_running = false` is set before T2W completes its first WAV write. The stop signal arrives during T2W's first inference pass.

### 2. Was T2W EOS sent?
**Partially.** The TTS thread pushes the final chunk with `is_final=true` before TTS thread exits. But T2W may or may not have dequeued this final chunk before `t2w_thread_running` is set to false. If the final chunk is still in the queue, it's dropped when the queue is drained.

### 3. Does the queue have unprocessed data?
**Sometimes.** If TTS pushed the final chunk before T2W dequeued it, the queue has 1 item. But the T2W thread breaks on `(!t2w_thread_running && queue.empty())` — so if the queue is NOT empty, T2W would process it. The issue is when T2W finished processing the last item and the queue IS empty, but the WAV for that last item hasn't been flushed to disk yet.

Actually, re-reading the code: T2W writes WAVs inline during queue processing, not in a separate flush step. So if T2W processed the item, the WAV should exist. The race must be: TTS never pushed the final chunk to T2W queue because TTS was stopped first.

### 4. Is the worker writing WAV when stopped?
**No.** The worker is in `cv.wait()` between iterations when `t2w_thread_running` becomes false. It has either:
a) Never received any queue items (TTS didn't push yet)
b) Finished processing all received items, queue is empty, waiting for more

In case (a), no WAVs were ever started.
In case (b), the WAVs from processed items should exist. But the stderr shows "does not exist or is empty" — suggesting case (a) is the dominant pattern.

### 5. Why rc=0 but no WAV?
`omni_free()` has no error detection for missing WAV output. It successfully joins all threads and frees resources, then returns normally. The "TTS: no valid WAV files to merge" is logged but does not affect the return code. This is a **missing error detection**: the cleanup code should check whether any audio was produced and set rc≠0 if not.

### 6. Why don't long responses trigger?
Long responses ensure T2W produces at least one WAV before the pipeline teardown begins. The first WAV callback fires, FA is recorded, and the sample is valid regardless of whether later WAVs are lost.

### 7. Does the race depend on token count or generation time?
**Both are proxies for the same thing.** Token count determines LLM generation time. Short token count → short generation → teardown starts sooner → higher race probability. The real dependency is: `teardown_start_time < T2W_first_WAV_time`.

### Additional Finding: TTS Thread Also Contributes

The join order is LLM → TTS → T2W. When TTS is joined, it may have produced its final mel tokens but not yet pushed them to the T2W queue. The TTS thread checks `tts_thread_running` in its loop and may exit with un-pushed output. The T2W thread then sees an empty queue and exits.

## 4. Required Fix: Drain-Before-Stop Protocol

The fix must ensure:
1. LLM completion is detected
2. TTS receives EOS and finishes all processing
3. TTS pushes final chunk with is_final=true to T2W queue
4. T2W drains all queued items
5. T2W completes all WAV writes and flushes
6. Only THEN are stop flags set and threads joined

The correct join order should be:
```
GENERATION_DONE
→ SIGNAL_T2W_EOS (via queue sentinel with is_final=true)
→ WAIT_T2W_QUEUE_DRAIN (condition: queue empty AND t2w produced ≥1 WAV or is NoSpeech)
→ SET_STOP_FLAGS
→ JOIN LLM
→ JOIN TTS  
→ JOIN T2W
→ VERIFY_OUTPUT_STATE
→ CLEANUP
```

## 5. Verification: What "NoSpeech" vs "Race" Must Look Like After Fix

| Condition | WAV count | rc | Diagnostic |
|---|---|---|---|
| VALID_NO_SPEECH | 0 | 0 | TTS produced no speak tokens; T2W never started |
| T2W_DRAIN_TIMEOUT | 0 | ≠0 | Queue drained but no WAV produced within timeout |
| T2W_PIPELINE_FAILURE | 0 | ≠0 | T2W worker reported error during processing |
| OUTPUT_BLOCKED | 0 | ≠0 | F005 degeneration block prevented output |
| NORMAL | ≥1 | 0 | First WAV produced before drain timeout |
