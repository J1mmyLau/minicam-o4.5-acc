# F6 EVENT SCHEMA V3

**Status:** AUTHORITATIVE (replaces V1 and V2)
**Created:** 2026-07-30
**Event count:** 16

---

## 1. Canonical Event List (exactly 16)

| # | Event ID | Neutral Name | E2EStage Enum | Enum Value | Thread | Implementation Status |
|---|----------|-------------|---------------|------------|--------|----------------------|
| 0 | R0 | request_enter_decode | STAGE_request_received | 0 | HTTP handler | EXISTS (no guard — overwrites each request) |
| 1 | P0 | prefill_submit | — | — | HTTP handler | MISSING — LLM thread signaled at line 12574-12576 |
| 2 | P1 | prefill_complete | — | — | HTTP handler | MISSING — g_decode_cv.wait returns at line 12579 |
| 3 | D0 | decode_loop_begin | STAGE_decode_loop_begin | 16 | HTTP handler | NEW (S9) — recorded at line 12581 |
| 4 | D1 | llm_first_decode_step | STAGE_llm_first_decode_step | 17 | HTTP handler | NEW (S9) — before first llama_loop call |
| 5 | D2 | llm_first_token | STAGE_llm_first_token | 2 | HTTP handler | EXISTS — guarded by llm_first_token_logged |
| 6 | D3 | llm_first_speak_token | STAGE_speak_token | 3 | HTTP handler | EXISTS — S9 added once-guard |
| 7 | G0 | tts_wake | STAGE_tts_wake | 18 | TTS thread | NEW (S9) — after cv.wait returns |
| 8 | G1 | tts_chunk_start | STAGE_talker_start | 4 | TTS thread | EXISTS — load==0 guard, now reset-safe |
| 9 | G2 | tts_first_decode | STAGE_tts_first_decode | 19 | TTS thread | NEW (S9) — before first TTS llama_decode |
| 10 | G3 | tts_first_audio_token | STAGE_talker_first_audio_token | 5 | TTS thread | EXISTS — load==0 guard, now reset-safe |
| 11 | G4 | tts_token_28 | STAGE_talker_token_28 | 6 | T2W thread | EXISTS — load==0 guard, now reset-safe |
| 12 | G5 | tts_submit_to_t2w | STAGE_t2w_submit | 7 | TTS thread | EXISTS — load==0 guard, now reset-safe |
| 13 | Q0 | t2w_dequeue | STAGE_t2w_dequeue | 8 | T2W thread | EXISTS — load==0 guard, now reset-safe |
| 14 | W0 | wav_ready | STAGE_wav_ready | 13 | T2W thread | EXISTS — load==0 guard, now reset-safe |
| 15 | W1 | client_first_audio | STAGE_client_first_audio | 14 | T2W thread | EXISTS — guarded by wav_idx==0 |

**Total: 16 events. 12 implemented, 2 missing (P0, P1), 2 pending guard fix (A3 generation_id).**

---

## 2. Dead Enum Values (present in E2EStage but NOT part of the 16 events)

| Enum Value | Enum Name | Reason Excluded |
|------------|-----------|----------------|
| 1 | STAGE_prompt_processing_start | Never instrumented; superseded by P0/P1 |
| 9 | STAGE_flow_start | Uses separate global atomic (g_e2e_flow_start_ns); dead — never written |
| 10 | STAGE_flow_end | Same as above |
| 11 | STAGE_vocoder_start | Same as above |
| 12 | STAGE_vocoder_end | Same as above |
| 15 | STAGE_request_done | Never instrumented |

These 6 enum values exist in the enumeration for backward compatibility but are NOT part of the 16-event neutral contract. They may appear in JSON output with value 0 (not recorded).

---

## 3. JSON Output Schema

```json
{
  "request_index": 0,
  "generation_id": 1,
  "prompt_id": "",
  "seed": 0,
  "talker_token_count": 0,
  "no_speech": false,
  "cann_error": 0,
  "crash": 0,
  "stale_write_count": 0,
  "cross_request_write_count": 0,
  "stages_ms": {
    "request_received": 0,
    "decode_loop_begin": 0,
    "llm_first_decode_step": 28,
    "llm_first_token": 65,
    "speak_token": null,
    "tts_wake": 285,
    "talker_start": 389,
    "tts_first_decode": 389,
    "talker_first_audio_token": 433,
    "talker_token_28": 687,
    "t2w_submit": 687,
    "t2w_dequeue": 687,
    "wav_ready": null,
    "client_first_audio": null
  }
}
```

### Rules

1. **16 canonical event names** in `stages_ms` (14 implemented + 2 placeholder for P0/P1 when added)
2. **Absent = not recorded** (null or omitted). 0 = recorded at t0.
3. **Dead enum values** (prompt_processing_start, flow_start, flow_end, vocoder_start, vocoder_end, request_done) are NOT part of the canonical 16 and may be omitted from output.
4. **generation_id**: monotonically incrementing per-request counter for stale-write detection.
5. **stale_write_count**: number of record() calls rejected due to generation_id mismatch.
6. **cross_request_write_count**: number of stale writes from a DIFFERENT request's generation.

---

## 4. Bitmask Convention

```cpp
// 16 events → 16-bit mask
uint16_t event_mask;

#define MASK_R0  (1 << 0)
#define MASK_P0  (1 << 1)
#define MASK_P1  (1 << 2)
#define MASK_D0  (1 << 3)
#define MASK_D1  (1 << 4)
#define MASK_D2  (1 << 5)
#define MASK_D3  (1 << 6)
#define MASK_G0  (1 << 7)
#define MASK_G1  (1 << 8)
#define MASK_G2  (1 << 9)
#define MASK_G3  (1 << 10)
#define MASK_G4  (1 << 11)
#define MASK_G5  (1 << 12)
#define MASK_Q0  (1 << 13)
#define MASK_W0  (1 << 14)
#define MASK_W1  (1 << 15)
```

Per-request masks:
- **recorded_mask**: events that were successfully recorded
- **missing_mask**: expected but not recorded
- **duplicate_mask**: recorded more than once
- **stale_mask**: rejected due to generation_id mismatch
- **out_of_order_mask**: recorded in wrong temporal order

---

## 5. Temporal Partial Order

```
R0 ≤ D0          (same thread, sequential)
D0 ≤ D1          (same thread, sequential)
D1 ≤ D2          (same thread, sequential)
D2 ≤ D3          (same thread, sequential, D3 optional)
D3 ≤ G0          (causal: SPEAK token → TTS wake via queue+CV)
G0 ≤ G1          (same thread, sequential)
G1 ≤ G2          (same thread, sequential)
G2 ≤ G3          (same thread, sequential)
G3 ≤ G4          (causal: audio tokens accumulate → buffer fills)
G4 ≤ G5          (causal: buffer full → push to T2W queue)
G5 ≤ Q0          (causal: queue push → dequeue via CV)
Q0 ≤ W0          (same thread, sequential)
W0 ≤ W1          (same thread, sequential)
```

Cross-thread pairs (D3→G0, G3→G4, G4→G5, G5→Q0) are causal (producer-consumer via mutex/CV) but NOT strictly simultaneous. A small positive delta is expected due to scheduling latency.

---

## 6. Column Mapping (CSV output)

```
request_index, generation_id, modality, cache_status,
R0_ns, P0_ns, P1_ns, D0_ns, D1_ns, D2_ns, D3_ns,
G0_ns, G1_ns, G2_ns, G3_ns, G4_ns, G5_ns,
Q0_ns, W0_ns, W1_ns,
recorded_mask, missing_mask, duplicate_mask, stale_mask, out_of_order_mask,
stale_write_count, cross_request_write_count,
audio_valid, cann_error, crash
```

Exactly 16 timestamp columns. All timestamps in nanoseconds (raw), with derived ms columns optionally appended.

---

## 7. Validation Checklist

- [ ] 16 events in enum/name array/output schema/CSV/documentation ALL match
- [ ] No document claims 14 or 15 events
- [ ] P0/P1 flagged as MISSING in implementation status
- [ ] Dead enum values excluded from canonical 16
- [ ] generation_id present in struct, output, and stale-write detection
- [ ] stale_write_count and cross_request_write_count in output
- [ ] Bitmask definitions match event ordering
- [ ] Temporal partial order documented with thread/causal annotations
