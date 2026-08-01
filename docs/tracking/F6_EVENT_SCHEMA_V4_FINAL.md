# F6 Event Schema V4 Final — Enum ↔ Functional Event Reconciliation

**Date:** 2026-08-01
**Status:** DEFINITIVE — resolves enum count vs functional event count discrepancy

---

## Problem

- `E2EStage` enum has `STAGE_COUNT=20` entries (indices 0-19)
- User's V4 contract functional decomposition: R0 + D0-D2 + T0-T7 + A0-A1 + Q0-Q1 + F0-F1 + V0-V1 + W0-W1 = **22 functional events**
- Previous claim "20 events" was incorrect — confused enum size with functional count

---

## Enum ↔ Functional Event Mapping

| Enum Index | Enum Name | Functional Event | Phase | Status |
|-----------|-----------|-----------------|-------|--------|
| 0 | `STAGE_request_received` | **R0** | Request | ACTIVE |
| 1 | `STAGE_prompt_processing_start` | *(dead)* | — | **UNUSED** — never recorded |
| 2 | `STAGE_llm_first_token` | **D2** | Main LLM | ACTIVE (first LLM token) |
| 3 | `STAGE_speak_token` | **D2'** | Main LLM | ACTIVE (first SPEAK token; no once-guard) |
| 4 | `STAGE_talker_start` | **T4/G1** | Talker | ACTIVE |
| 5 | `STAGE_talker_first_audio_token` | **T6/G3** | Talker | ACTIVE (MISSING from FP16 profiles) |
| 6 | `STAGE_talker_token_28` | **T7/G4/G5** | Talker→T2W | ACTIVE (dual-use: TTS submit + T2W buffer threshold) |
| 7 | `STAGE_t2w_submit` | **Q0** | T2W Queue | ACTIVE (MISSING from FP16 profiles) |
| 8 | `STAGE_t2w_dequeue` | **Q0'** | T2W Queue | ACTIVE (dequeue side of Q0) |
| 9 | `STAGE_flow_start` | **F0** | Flow | ACTIVE (global fallback → C8 migration) |
| 10 | `STAGE_flow_end` | **F1** | Flow | ACTIVE (global fallback → C8 migration) |
| 11 | `STAGE_vocoder_start` | **V0** | Vocoder | ACTIVE (global fallback → C8 migration) |
| 12 | `STAGE_vocoder_end` | **V1** | Vocoder | ACTIVE (global fallback → C8 migration) |
| 13 | `STAGE_wav_ready` | **W0** | Waveform | ACTIVE |
| 14 | `STAGE_client_first_audio` | **W1** | Waveform | ACTIVE |
| 15 | `STAGE_request_done` | *(dead)* | — | **UNUSED** — never recorded |
| 16 | `STAGE_decode_loop_begin` | **D0** | Main LLM | ACTIVE |
| 17 | `STAGE_llm_first_decode_step` | **D1** | Main LLM | ACTIVE |
| 18 | `STAGE_tts_wake` | **T3/G0** | Talker | ACTIVE |
| 19 | `STAGE_tts_first_decode` | **T5/G2** | Talker | ACTIVE |

---

## Functional Event Inventory (22 total)

### Phase R: Request (1)
| # | Name | Enum | Status |
|---|------|------|--------|
| R0 | request_received | 0 | ACTIVE |

### Phase D: Main LLM Decode (3)
| # | Name | Enum | Status |
|---|------|------|--------|
| D0 | decode_loop_begin | 16 | ACTIVE |
| D1 | llm_first_decode_step | 17 | ACTIVE |
| D2 | llm_first_token | 2 | ACTIVE |

### Phase T: Talker / TTS (8)
| # | Name | Enum | Status |
|---|------|------|--------|
| T0 | *(tts_token_enqueue)* | — | **NOT INSTRUMENTED** — per-token push to TTS queue |
| T1 | *(tts_context_prepare)* | — | **NOT INSTRUMENTED** — pre-decode setup |
| T2 | *(tts_decode_begin)* | — | **NOT INSTRUMENTED** — first decode step |
| T3 | tts_wake | 18 | ACTIVE (G0) |
| T4 | talker_start | 4 | ACTIVE (G1) |
| T5 | tts_first_decode | 19 | ACTIVE (G2) |
| T6 | talker_first_audio_token | 5 | ACTIVE (G3, missing in FP16) |
| T7 | talker_token_28 / t2w_submit | 6/7 | ACTIVE (G4, missing in FP16) |

**Note:** T0-T2 are conceptual only — no enum entries exist for them. They are currently subsumed within the G0→G1 and G1→G2 gaps. Phase 3 TalkerStepBuffer can provide T0-T2 granularity via per-step records without new enum entries.

### Phase A: Audio Accumulation (2)
| # | Name | Enum | Status |
|---|------|------|--------|
| A0 | audio_accumulation_start | — | **RING BUFFER ONLY** — TalkerStepBuffer records first audio token, no single-timestamp stage needed |
| A1 | audio_accumulation_threshold | — | **RING BUFFER ONLY** — TalkerStepBuffer records threshold crossing via `steps_G3_to_threshold`, no single-timestamp stage needed |

**Design decision:** A0/A1 are tracked via TalkerStepBuffer per-step records, NOT as E2EStage enum entries. They are derived metrics computed from ring buffer data:
- A0 = first step where `is_audio_token == 1` (redundant with G3/talker_first_audio_token)
- A1 = A0 + 25 (accumulation count threshold)

### Phase Q: T2W Queue (2)
| # | Name | Enum | Status |
|---|------|------|--------|
| Q0 | t2w_dequeue | 8 | ACTIVE |
| Q1 | t2w_preprocess_end | **NEEDS NEW ENUM (20)** | **MISSING** — required for C8 decomposition |

### Phase F: Flow Matching (2)
| # | Name | Enum | Status |
|---|------|------|--------|
| F0 | flow_start | 9 | ACTIVE (global → C8 request-scoped) |
| F1 | flow_end | 10 | ACTIVE (global → C8 request-scoped) |

### Phase V: Vocoder (2)
| # | Name | Enum | Status |
|---|------|------|--------|
| V0 | vocoder_start | 11 | ACTIVE (global → C8 request-scoped) |
| V1 | vocoder_end | 12 | ACTIVE (global → C8 request-scoped) |

### Phase W: Waveform Output (2)
| # | Name | Enum | Status |
|---|------|------|--------|
| W0 | wav_ready | 13 | ACTIVE |
| W1 | client_first_audio | 14 | ACTIVE |

---

## Reconciliation Summary

```
Enum entries:         20 (STAGE_COUNT)
  - Dead (unused):     2 (prompt_processing_start=1, request_done=15)
  - Active:           18

Functional events:    22
  - Have enum entry:  19 (18 active enums + 1 needed: Q1)
  - Ring-buffer only:  2 (A0, A1 — via TalkerStepBuffer)
  - Not instrumented:  3 (T0, T1, T2 — conceptual gaps)

Gap: 22 functional - 19 enum-tracked - 2 ring-buffer - 1 Q1-missing = 0 ✓
```

---

## Required Action: Add STAGE_t2w_preprocess_end (Q1)

```cpp
// Add to E2EStage enum (before STAGE_COUNT):
STAGE_t2w_preprocess_end,  // 20 — Q1: T2W preprocessing complete, Flow about to begin
STAGE_COUNT                // → becomes 21
```

**Impact:**
- `STAGE_COUNT` increases from 20 → 21
- `timestamps_ns[21]` array (was 20, now 21)
- `stage_name()` switch: add case for STAGE_t2w_preprocess_end
- JSON schema: add "t2w_preprocess_end" to async stages
- Reset loop (0..STAGE_COUNT) automatically covers new entry
- enum values 0-19 unchanged (backward compatible)

---

## Array/Schema Consistency Checklist

| Component | Before | After | Action |
|-----------|--------|-------|--------|
| `E2EStage` enum | 0-19, STAGE_COUNT=20 | 0-20, STAGE_COUNT=21 | Add entry 20 |
| `stage_name()` switch | 20 cases | 21 cases | Add case 20 |
| `timestamps_ns[]` | `std::atomic<int64_t>[20]` | `[21]` | Auto (uses STAGE_COUNT) |
| `reset()` loop | `i < STAGE_COUNT` (20) | `i < STAGE_COUNT` (21) | Auto |
| JSON `e2e_profile_dump_json` | skips unknown | skips unknown | Auto |
| JSON `e2e_profile_dump_audio_json` async_stages | 7 entries | +1 (Q1) | Add STAGE_t2w_preprocess_end |
| CSV parser | N/A | N/A | No CSV output (JSON only) |
| `add_global_fallback` | flow/vocoder 4 stages | **REMOVED after C8** | Migrate to per-stage |
| `add_global_stage` | flow/vocoder 4 stages | **REMOVED after C8** | Migrate to per-stage |
| V4 contract doc | 18 events | 19 enum events + 3 conceptual | Update |

---

## Bitmask / Feature Flag

No bitmask is used for stage filtering. All stages are always recorded when profiling is enabled. The `enabled` flag on `E2EStageTiming` controls all-or-nothing recording.

---

## Verification After C8

```python
# After C8, for every request:
# - STAGE_t2w_preprocess_end (20) must be present
# - STAGE_flow_start (9), STAGE_flow_end (10) must be present (not global fallback)
# - STAGE_vocoder_start (11), STAGE_vocoder_end (12) must be present (not global fallback)
# - critical_missing count = 0
# - t2w_dequeue → wav_ready decomposes to:
#     Q0→Q1 + Q1→F0 + F0→F1 + F1→V0 + V0→V1 + V1→W0
```
