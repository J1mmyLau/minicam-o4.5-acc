# F6 Phase 2 — Step 3: Decode→Speak Segment Breakdown
## 2026-08-04 | COMPLETE

Source: S13 strict 120 log. Decomposes the speak path using the markers the S13 build actually logs. n=120 requests aligned to final JSON.

---

## Speck-Path Segments (pooled p50)

| Segment | p50 (ms) | p90 | p95 | p99 | max | n |
|---------|---------:|----:|----:|----:|----:|--:|
| **prep** (D0 → "assistant prompt 完成") | 28 | 29 | 30 | 33 | 34 | 120 |
| **decode→speak commit** (D0 → first "LLM->TTS:") | **142** | 162 | 167 | 223 | 695 | 119 |
| speak→TTS audio start (first "Phase1: token 1") | 97 | 209 | 557 | 987 | 987 | 64 |
| TTS audio-gen (Phase1 token1 → "yield 25 tokens 到 T2W") | 318 | 526 | 605 | 5219 | 5219 | 64 |
| queue→T2W dequeued | ~0 | 0 | 1 | 5344 | 5344 | 64 |
| T2W inference (chunk0, from budget script n=119) | **4490** | 5130 | 5368 | 5835 | 6034 | 119 |
| **W0** (decode→first audio) | **4830** | 5680 | 6451 | 10321 | 10528 | 119 |

### By case type (p50, ms)

| cat | prep | decode→spk | spk→aud | aud-gen | q→t2w | W0 |
|-----|-----:|-----------:|--------:|--------:|------:|----:|
| short_cn | 29 | 144 | 127 | 291 | 0 | 5202 |
| long_cn | 28 | 141 | 88 | 374 | 0 | 4785 |
| english | 28 | 102 | 102 | 314 | 0 | 4584 |
| number_mix | 28 | 141 | 86 | 361 | 0 | 4778 |

---

## Findings

1. **The Phase-2 target segment (decode→speak commit) is 142ms p50 = 2.9% of W0.**
   Amdahl cap: even at zero cost, the entire LLM decode→speak-token path frees at most **142ms** of the 4830ms W0. It is bounded and small.

2. **The full speak→audio-ready path is ~557ms** (142 + 97 + 318): decode→speak commit, TTS queue/sampler setup, and generating the first 25 audio tokens. This is the "overhead" bucket from Step 2 plus the decode segment. Still only ~11.5% of W0; **T2W inference (93%) remains the dominant cost by an order of magnitude.**

3. **The 12 internal decode-loop categories are NOT in the S13 log.** No per-token records (MAIN_LLM_FORWARD / LOGITS / SAMPLING / TOKEN_COMMIT / STOP_CHECK / TALKER_TRIGGER_CHECK / THREAD_WAKE / QUEUE_WAIT / CV_WAIT / STREAM_SYNC / ALLOCATION / UNKNOWN) are emitted by the S13 build. Obtaining them requires adding instrumentation inside the LLM decode loop and a focused re-run.

4. **Per Amdahl, per-step decode-loop instrumentation is DEFER.** It could reveal at most 142ms (2.9%) of W0. The marginal value of that breakdown — while useful for pure decode-loop work — is small next to the 4490ms T2W target. (Verdict also recorded in Step 5 ranking.)

5. **`prep` = 28ms** is the LLM pre-decode work: assistant-prompt append + KV-reuse hand-off. It is *not* a re-prefill (KV HIT config, Step 8/9 closure: prefill 86ms happens before D0).

---

## Artifacts

| Artifact | Path |
|----------|------|
| Breakdown script | `scripts/f6_phase2_step3_decode_speak_breakdown.py` |
| Per-request JSON (120 rows) | `docs/f6-s13-closure/phase2/step3_decode_speak_breakdown.json` |
