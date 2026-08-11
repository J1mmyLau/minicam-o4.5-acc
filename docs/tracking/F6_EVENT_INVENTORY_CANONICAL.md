# F6 Phase 3 — Canonical Event Inventory (S2)

**Date:** 2026-08-01
**HEAD:** `13aab91`
**Verdict:** 21 enum entries = 21 stage_names = 21 timestamps_ns[] slots. **No 22nd functional event.**

## Resolution of 21/22 Ambiguity

The claim of "22 functional events" in the previous session was a **miscount**.
It likely arose from one of these errors:

1. **Counting 4 global atomics as separate events**: `g_e2e_flow_start_ns` etc. duplicate
   enum entries `STAGE_flow_start` etc. — they store the same timestamp, just in a different
   memory location. They are NOT independent events.
2. **Counting dead enum entries as functional**: `STAGE_prompt_processing_start` (1) and
   `STAGE_request_done` (15) exist in the enum but are NEVER recorded by any code path.
3. **Double-counting stages that appear in both `stages_ms` and `async_stages_ms`**:
   The same events appear in different JSON sections but refer to the same timestamps.

## Canonical Inventory: 21 Entries

| # | Enum Entry | Idx | Recorded? | Writer Thread | Storage | JSON: stages_ms | JSON: async_stages_ms | JSON: audio profile |
|---|-----------|-----|-----------|---------------|---------|-----------------|----------------------|---------------------|
| 0 | request_received | 0 | YES | HTTP handler | timestamps_ns[0] | ✓ | | sync |
| 1 | prompt_processing_start | 1 | **NO** | — | — | (dead) | | |
| 2 | llm_first_token | 2 | YES | TTS thread | timestamps_ns[2] | ✓ | | sync |
| 3 | speak_token | 3 | YES | TTS thread | timestamps_ns[3] | ✓ | | sync |
| 4 | talker_start | 4 | YES | TTS thread | timestamps_ns[4] | ✓ | | sync |
| 5 | talker_first_audio_token | 5 | YES | TTS thread | timestamps_ns[5] | ✓ | | sync |
| 6 | talker_token_28 | 6 | YES | T2W thread | timestamps_ns[6] | ✓ | | sync |
| 7 | t2w_submit (Q0) | 7 | YES | TTS thread | timestamps_ns[7] | ✓ | | sync |
| 8 | t2w_dequeue (Q1) | 8 | YES | T2W thread | timestamps_ns[8] | ✓ | ✓ | audio |
| 9 | flow_start (F0) | 9 | YES | T2W thread | timestamps_ns[9] + g_e2e_flow_start_ns | ✓ | ✓ | audio |
| 10 | flow_end (F1) | 10 | YES | T2W thread | timestamps_ns[10] + g_e2e_flow_end_ns | ✓ | ✓ | audio |
| 11 | vocoder_start (V0) | 11 | YES | T2W thread | timestamps_ns[11] + g_e2e_vocoder_start_ns | ✓ | ✓ | audio |
| 12 | vocoder_end (V1) | 12 | YES | T2W thread | timestamps_ns[12] + g_e2e_vocoder_end_ns | ✓ | ✓ | audio |
| 13 | wav_ready (W0) | 13 | YES | T2W thread | timestamps_ns[13] (+wav_ready_ns fallback) | ✓ | ✓ | audio |
| 14 | client_first_audio (C0) | 14 | YES | T2W thread | timestamps_ns[14] | ✓ | ✓ | audio |
| 15 | request_done | 15 | **NO** | — | — | (dead) | | |
| 16 | decode_loop_begin (D0) | 16 | YES | TTS thread | timestamps_ns[16] | ✓ | | sync |
| 17 | llm_first_decode_step (D1) | 17 | YES | TTS thread | timestamps_ns[17] | ✓ | | sync |
| 18 | tts_wake (G0) | 18 | YES | TTS thread | timestamps_ns[18] | ✓ | | sync |
| 19 | tts_first_decode (G2) | 19 | YES | TTS thread | timestamps_ns[19] | ✓ | | sync |
| 20 | t2w_preprocess_end (Q2) | 20 | YES | T2W thread | timestamps_ns[20] | ✓ | ✓ | audio |

**Summary:**
- **21 enum entries total**
- **19 actively recorded** (2 dead: prompt_processing_start, request_done)
- **4 have dual storage** (flow_start/end, vocoder_start/end: both enum slot + global atomic)
- **8 async stages** (Q1, Q2, F0, F1, V0, V1, W0, C0) emitted in async_stages_ms
- **2 JSON profiles**: sync (e2e_XXXX.json at decode return) and audio (e2e_XXXX_audio.json at first WAV)

## JSON Output Reconciliation

### `stages_ms` section (in e2e_XXXX.json)

Iterates `timestamps_ns[0..20]` → emits 19 non-zero keys.
Then `add_global_stage` adds flow_start/flow_end/vocoder_start/vocoder_end from globals.

**Post-C8 (N5): these 4 keys may appear twice** (once from timestamps_ns[] via C8 mirror,
once from global atomics via add_global_stage). Both have the same value — functionally
correct, technically a duplicate-key JSON spec violation. This is a known quirk, not a bug.

### `async_stages_ms` section (in e2e_XXXX_audio.json)

8 entries in fixed order:
```
t2w_dequeue, t2w_preprocess_end, flow_start, flow_end,
vocoder_start, vocoder_end, wav_ready, client_first_audio
```

### `talker_step_summary` section (in e2e_XXXX.json, gated by F6_PHASE3_TALKER_STATS=1)

Per-step timing (not per-stage). Steps are TTS decode iterations, not E2E stages.
Includes rejection counters: late_write_rejected, write_after_finalize, invalid_generation_write.

## Conclusion

| Claim | Status |
|-------|--------|
| "21 stages" | **CORRECT** — 21 enum entries = STAGE_COUNT=21 |
| "22 functional events" | **FALSE** — miscount; no independent 22nd event exists |
| "19 functional + 2 legacy" | **CORRECT** — 19 recorded, 2 dead enum entries |
| "Flow/Vocoder are separate functional events" | **FALSE** — they are already in the 21 enum entries |
| "4 global atomics are additional events" | **FALSE** — they duplicate enum entries 9-12 |

The canonical count is **21 stages, 19 actively recorded, 8 async**.
No further ambiguity.
