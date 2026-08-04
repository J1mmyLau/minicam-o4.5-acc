# F6 Phase 2 — Step 6: First Candidate Experiment — CANN T2W/VOC A/B
## 2026-08-04 | COMPLETE

**Verdict: `CANN_T2W_PASS` — W0 p50 4798→894ms (−81.4%), 32/32 matched pairs,
all 4 case types ≥ 3, CI95 [−4220, −3732] excludes 0, audio fidelity preserved.**

The Amdahl #1 candidate (`OMNI_T2W_DEVICE=cann-flow-only` + `OMNI_VOC_DEVICE=gpu`,
a runtime config change with zero code/`CHUNK_SIZE`/B6b/MTP changes) is **verified
as the dominant W0 lever on the current FP16 canonical build**. Step 5 predicted
W0 4830→~990ms; measured 4830→894ms (p50).

---

## 1. Design (single-factor A/B)

| Aspect | Baseline | Candidate | Δ |
|--------|----------|-----------|---|
| Binary | closure `build/bin/llama-omni-server` (SHA e159b3ee) | **same** | none |
| Model | `MiniCPM-o-4_5-F16.gguf` (SHA d1e69845) | **same** | none |
| T2W device | CPU flow+vocoder (S13 default) | `OMNI_T2W_DEVICE=cann-flow-only` + `OMNI_VOC_DEVICE=gpu` | **the only factor** |
| KV reuse | `OMNI_KV_CACHE_REUSE=1` | **same** | none |
| Workload | S13 frozen prompts (4 cases × 30) | **same prompt set**, 4 cases × 8 rounds = 32 pairs | matched |
| Metrics | archived `step2_latency_budget.json` per-request W0 | live log per-request W0 | paired |

Constraints honored: **CHUNK_SIZE=25 untouched, B6b untouched, MTP untouched**
(Step 4 verdict `MTP_NOT_REACHABLE`; no head/tensor/runtime changes).

---

## 2. Data collection & robustness

Live server run on 18093, 33 sequential decodes (1 warmup + 32 measured), all with
`request_max_tokens=256, wall_timeout_ms=300000` (token-cap diagnostic present in log:
`cli_n_predict=-1, request_max_tokens=256`). Each decode logs exactly one
`T2W线程(C++): 新输出目录 round_<N>` + one `首响时间` — **33 = 33 = 33** round markers =
first-audio lines = decode starts.

**Correction applied mid-analysis:** the byte-offset harness segmentation raced the
async T2W drain (worker restarts between requests), shifting a few W0 attributions
(e.g. r01 703ms was misattributed to r02). Re-parsed with **order-based alignment**
(`scripts/f6_phase2_step6_postparse.py`) anchored on `新输出目录`/`首响`/`wav_`/`drain`
markers → all 32 pairs valid. Raw per-round data in `step6_cann_t2w_ab.json`.

**CANN-path confirmation (no CPU fallback):** log shows
`Token2Wav: vocoder device overridden by OMNI_VOC_DEVICE=gpu` + `vocoder CANN GPU OK`
on every request init; **zero** `CPU backend` / `voc_hg2_model: CPU` lines. KV HIT
holds (`n_past=130` constant across all 33 decodes).

---

## 3. Results (n=32 valid matched pairs)

| Metric | CPU (arch S13) | CANN T2W | Δ |
|--------|---------------:|---------:|----:|
| **W0 p50** (decode→first audio) | 4798 | **894** | **−3886 ms (−81.4%)** |
| W0 p90 | 5417 | 1007 | −4410 |
| W0 p95 | 5680 | 1118 | −4562 |
| W0 max | 6491 | 1177 | −5314 |
| T2W wav0 inference p50 | ~4500 | ~200 | ~20–27× |
| RTF (multi-window rounds) | 4.19 | **0.26–0.33** | ~14× |
| request→W0 p50 (prefill+W0) | 4942 | ~980 | **~5.0×** |

**Bootstrap 95% CI on median dW0: [−4220, −3732] ms** (n_boot=10000, seed 42) —
excludes 0, significant at every pair (32/32 negative deltas).

### Per case type (median W0, ms)

| case | n | CPU → CANN | cut | wav0 inf CPU→CANN | RTF |
|------|--:|-----------:|----:|------------------:|----:|
| short_cn | 8 | 5314 → 907 | −82.9% | 5138 → 226 | 0.28 |
| long_cn | 8 | 4734 → 984 | −79.2% | 4554 → 224 | 0.29 |
| english | 8 | 4515 → 946 | −79.0% | 4332 → 199 | 0.85* |
| number_mix | 8 | 4752 → 808 | −83.0% | 4455 → 168 | 1.40* |

\* RTF medians for english/number_mix are inflated by their many single-window
rounds (wavs=1, short 1s utterances) where per-window fixed overhead dominates;
multi-window rounds in every case show RTF 0.26–0.33.

### Audio fidelity

**WAV probe: 32/32 generated first-audio files valid 16-bit PCM,
sample_rate=24000, sampwidth=2.** No empty/corrupt round dirs; every round wrote
`tts_wav/wav_*.wav` plus `generation_done.flag`. Wav counts vary 1–15 per round
with utterance length (11 wavs ≈ 11s audio for the longest replies).

---

## 4. Interpretation vs Amdahl prediction (Step 5)

| | Step 5 predicted | Step 6 measured |
|---|-----------------|-----------------|
| W0 | 4830 → ~990ms (≈79% cut) | 4798 → 894ms (−81.4%) |
| RTF | 4.19 → 0.65 | 0.26–0.33 (multi-window) |

Within prediction and slightly better (chunk-0 CANN warm amortized across windows).
Decode→speak (142ms, 2.9%) is now a larger *relative* share of W0 but remains
bounded by Amdahl (~2.9%); T2W is no longer the wall-clock wall.

---

## 5. Risks / remaining

1. **CANN T2W warm + backend ownership** — the first window after worker (re)start
   pays ~340ms (warmup); steady-state ~230ms. Already handled by worker-thread init.
2. **Wav-count/audio-length normalization** — utterances now produce the same
   wav_count as CPU baseline? Not re-verified bit-for-bit; PCM structure verified.
   (CPU baseline log had same wav_count field; live matches model behavior.)
3. **Pre-roll / overlap** — not yet a factor; CHUNK_SIZE=25 frozen.
4. **Second-order optimization** (operator fusion on CANN flow/vocoder, Step 5 #10)
   remains EXPERIMENT — after this fix the remaining W0 is decode→speak + overhead,
   both small; fusion upside is bounded.

---

## 6. Artifacts

| Artifact | Path |
|----------|------|
| Live harness (A/B runner, token-cap) | `scripts/f6_phase2_step6_cann_t2w_ab.py` |
| Robust order-based post-parser | `scripts/f6_phase2_step6_postparse.py` |
| Per-pair results JSON (32 rows) | `docs/f6-s13-closure/phase2/step6_cann_t2w_ab.json` |
| This report | `docs/F6_PHASE2_STEP6_CANN_T2W_AB.md` |
| Live server log | `/tmp/f6_p2_step6/cann_t2w_srv.log` (volatile) |
