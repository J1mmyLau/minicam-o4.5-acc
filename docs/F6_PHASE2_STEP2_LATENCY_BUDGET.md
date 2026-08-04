# F6 Phase 2 — Step 2: First-Audio Latency Budget
## 2026-08-04 | COMPLETE

Source: `docs/f6-s13-closure/raw-data/step7/s13_step7_full_server.log` (S13 strict 120, USE_TTS=True, CPU flow/vocoder, KV-cache HIT config). n=119 valid requests (1 anomalous 256-token short_cn request excluded from some stats by W0 outliers).

---

## Core Question Answered

> **"4.59 秒首音里，LLM Decode → Speak Token 到底占多少"**

**Answer: LLM Decode → first speak-token commit = 142ms p50 = 2.9% of W0 (4830ms).**
**The dominant cost is T2W inference — CPU flow_matching + vocoder for the first 25-token window = 4490ms = 93.0% of W0.**

The decode→speak path (the Phase 2 working hypothesis) is NOT the bottleneck. The TTS/T2W audio-synthesis pipeline is.

---

## Request→W0 Decomposition (pooled, p50)

| Stage | p50 (ms) | % of W0 | p90 | p95 | p99 | max |
|-------|---------:|--------:|----:|----:|----:|----:|
| prefill (KV HIT) | 102 | 2.1% (of req→W0) | 110 | 116 | 120 | 151 |
| **LLM→speak** (decode D0 → first "LLM->TTS:" commit) | **142** | **2.9%** | 162 | 167 | 223 | 695 |
| **T2W_inference** (first window: flow+vocoder) | **4490** | **93.0%** | 5130 | 5368 | 5835 | 6034 |
| overhead (TTS audio-gen + queue + flow setup + WAV write) | 320 | 6.6% | 497 | 843 | 5387 | 5423 |
| **W0** (decode→first audio) | **4830** | 100% | 5680 | 6451 | 10321 | 10528 |

- **request→W0 = prefill + W0 = 102 + 4830 = 4932ms** p50.
- wav_count p50 = 2 (few requests finish first audio in 1 window), p90 = 13, max = 52.

### By case type (p50)

| cat | prefill | LLM→speak | T2W_inf | overhead | W0 |
|-----|--------:|----------:|--------:|---------:|----:|
| short_cn (0000) | 106 | 144 | 4749 | 380 | **5202** |
| long_cn (0002) | 102 | 141 | 4520 | 1 | **4785** |
| english (0004) | 101 | 102 | 4343 | 145 | **4584** |
| number_mix (0006) | 101 | 142 | 4413 | 324 | **4778** |

All four categories agree: T2W_inf is 88–93% of W0 in every case.

---

## Interpretation

1. **The 142ms LLM→speak segment is nearly invisible in W0.** Even if decode→speak were reduced to zero, W0 would drop at most 142ms (2.9%) — an Amdahl cap. The user's Phase 2 hypothesis (decode→speak dominates) is refuted by data.

2. **T2W inference on CPU is the entire game.** The first window of 25 audio tokens passes through `token2wav_session->feed_window()`: flow_matching (semantic→mel, CPU) + voc_hg2 (mel→waveform, 8 CPU threads). Log confirms `flow_matching暂用CPU` / `voc_hg2_model: CPU backend using 8 threads`.

3. **A validated CANN acceleration path already exists** in this repo (commit `3fc0ed5`, worker-thread CANN flow backend): First Audio **5921→1754ms (3.4×)**, per-window **4194→648ms (6.5×)**, RTF **4.19→0.65**. The S13 baseline simply did NOT set `OMNI_T2W_DEVICE` / `OMNI_VOC_DEVICE`, so it ran the CPU fallback. This is the obvious first candidate (Step 6).

4. **Overhead p99 = 5387ms** comes from the 2 anomalous 256-token short_cn requests (max W0 = 10528ms) where the audio-dump path serializes all windows — a tail issue, not the p50 story.

---

## Artifacts

| Artifact | Path |
|----------|------|
| Budget script | `scripts/f6_phase2_latency_budget.py` |
| Per-request budget JSON (120 rows) | `docs/f6-s13-closure/phase2/step2_latency_budget.json` |
| Source log | `docs/f6-s13-closure/raw-data/step7/s13_step7_full_server.log` |
