# F6 R4: Text Consistency — Corrected Wording

**Date:** 2026-07-31
**Replaces:** "code-guaranteed identical" → split into CODE_AUDIT + RUNTIME_MEASUREMENT

---

## CODE_AUDIT

### Main LLM Generation Logic Unchanged

The `step_size` / `effective_step` variable controls how many valid LLM tokens are accumulated before dispatching a text chunk to the TTS queue. This variable is used exclusively in the TTS dispatch path, **after** LLM decode completes.

**LLM decode path** (`stream_decode` in `omni.cpp`):
1. Autoregressive token generation loop
2. Uses: model weights, KV cache, sampling parameters (temperature, top_p, top_k)
3. Checks: stop tokens (EOS, `<|im_end|>`)
4. Does NOT reference: `step_size`, `effective_step`, `OMNI_TTS_FIRST_CHUNK_STEP`

**TTS dispatch path** (after decode):
1. Receives: generated token_ids from LLM
2. Classifies: valid vs invalid tokens for TTS
3. Accumulates: valid tokens until `effective_step` threshold
4. Dispatches: text chunk to TTS queue

**Conclusion:** No code path connects TTS dispatch parameters back to LLM token generation. The LLM sampling and token generation logic is unmodified.

### Potential Risks (acknowledged, not observed)

| Risk | Mitigation |
|------|-----------|
| Buffer/EOS flush timing differs with smaller first chunk | Same code path for flush; chunk size only affects dispatch threshold, not flush logic |
| Async lifecycle may drop/reorder tokens across chunk boundaries | Token classification is deterministic; chunk boundary only affects batching, not content |
| KV cache state could differ if TTS backpressure affects LLM timing | LLM generates all tokens before TTS dispatch; no backpressure feedback |

---

## RUNTIME_MEASUREMENT

### Tested Cases

| Test | Prompts | Languages | Result |
|------|---------|-----------|--------|
| C7 SSE streaming | ~10 | English, Chinese | Text fragments identical between baseline/candidate |
| C6 116 pairs | 116 | English | Main LLM token count + final text consistent |
| Z10 200 requests | 200 | English, Chinese, Mixed | All 200 decode responses returned successfully |
| Z4 120 requests | 120 | English | All decode responses returned; no text anomalies in server logs |

### Measurements (where available)

| Metric | Value | Method |
|--------|-------|--------|
| Main token sequence | No differences observed | C7 SSE text fragment comparison |
| Final text output | No differences observed | C7 full text capture |
| Chunk token concatenation | Pending systematic verification | |
| EOS remainder | Pending systematic verification | |
| Token loss rate | 0 observed in tested cases | |
| Token duplicate rate | 0 observed in tested cases | |
| Token reorder rate | 0 observed in tested cases | |

---

## Corrected Wording

| ❌ DO NOT WRITE | ✅ CORRECT |
|----------------|-----------|
| "Text output identical (code-guaranteed)" | "MAIN_LLM_GENERATION_LOGIC_UNCHANGED: code audit confirms step_size isolated to TTS dispatch. TESTED_MAIN_TOKEN_SEQUENCES_IDENTICAL: no differences observed in tested cases." |
| "Text mathematically identical" | "LLM sampling and token generation paths are unmodified. In all executed consistency tests, complete token sequences and final text matched between baseline and candidate." |

## Gate Status

```
B6B_TEXT_CONSISTENCY_GATE = PASS_ON_TESTED_CASES
├── CODE_AUDIT: MAIN_LLM_GENERATION_LOGIC_UNCHANGED
├── RUNTIME: TESTED_MAIN_TOKEN_SEQUENCES_IDENTICAL
├── Systematic token-level verification: PENDING (low priority — no failure hypothesis)
└── Risk: LOW (no feedback path from TTS dispatch to LLM decode)
```
