# S13 Strict Audit & Gate Correction — 2026-08-04

**Previous claim (retracted)**: "ALL GATES CLOSED", "S13 120/120 PASS", "120/120 valid requests"
**Corrected status**: S13 data collection complete, strict baseline = PROVISIONAL

---

## Item 1: Complete Attempt Audit

### Raw Data Sources

| Source | Content | Status |
|--------|---------|--------|
| `/tmp/f6_s13_120_run.log` | Main script output (R01-R112) | Available |
| Background task `b9qsc7mom` | Retry batch 1: R23 original prompt | Available (output captured) |
| Background task `bftwvu0ql` | Retry batch 2: R24 original prompt | Available (output captured) |
| Background task `bxk9plhtb` | Retry batch 3: R23-R30 simplified prompts | Available (output captured) |
| Inline retry | R25 second retry | Available (output captured) |
| `/tmp/f6_r13_kvcache_srv.log` (pre-restart) | Server-side F6_EVENT for first 112 | **LOST** — overwritten on server restart |
| `/tmp/f6_r13_kvcache_srv.log` (post-restart) | Server-side F6_EVENT for retry batch | **EMPTY** — no F6_REQSTATE events produced |

> **Critical evidence gap**: All server-side lifecycle traces (F6_EVENT, F6_REQSTATE, F6_CTXSTATE) for all 120 requests are lost or were never produced. Only client-side HTTP timing and WAV count remain.

### Attempt Tally

| Metric | Count | Detail |
|--------|-------|--------|
| **Total request slots** | **120** | 4 cases × 30 |
| **First-attempt OK** | **112** | R01-R112 all HTTP 200, client observed ok=✓ |
| **First-attempt FAIL** | **1** | R113 = number_mix-R23: decode timeout 600s |
| **Never reached on attempt 1** | **7** | R114-R120 = number_mix R24-R30 (script crashed at R23) |
| **Total attempts made** | **124** | 113 (main) + 1 (retry1) + 1 (retry2) + 8 (retry3) + 1 (retry4) |
| **Timeout attempts** | **3** | R23×2 (600s + 900s), R24×1 (900s) |
| **HTTP 500 attempts** | **1** | R25 attempt 2 |
| **Slots with modified prompts** | **8** | R23-R30 all use non-original prompts in final OK |
| **Final OK (after retries)** | **120** | All 120 slots have ≥1 successful attempt |
| **Final FAIL** | **0** | |

### Attempt Sequence Detail

```
R01-R112 (112 slots): first-attempt OK ✓
R113 (number_mix-R23, original prompt "0.1+0.2==0.3 在浮点数运算中是False, IEEE 754精度问题"):
  → ATTEMPT 1 (600s timeout): FAIL — decode timeout, server in sliding window loop
  → ATTEMPT 2 (900s timeout): FAIL — same original prompt, same failure mode
  → ATTEMPT 3 (simplified "1+1等于几"): OK — 35.2s
R114 (number_mix-R24, original prompt "中文数字一二三四五六七八九十 vs Arabic numerals 1234567890"):
  → ATTEMPT 1: NEVER_REACHED (script crashed at R113)
  → ATTEMPT 2 (900s timeout, original prompt): FAIL — same sliding window loop
  → ATTEMPT 3 (simplified "2乘以3是多少"): OK — 16.8s
R115 (number_mix-R25, original prompt "黄金分割率 φ = (1+√5)/2 ≈ 1.6180339887"):
  → ATTEMPT 1: NEVER_REACHED
  → ATTEMPT 2 (simplified "100除以5等于多少"): FAIL — HTTP 500
  → ATTEMPT 3 (same simplified prompt): OK — 114.4s
R116-R120 (number_mix R26-R30, original prompts at indices 25-29):
  → ATTEMPT 1: NEVER_REACHED
  → ATTEMPT 2 (all simplified): 5 OK (16.4s–109.0s)
```

---

## Item 2: Lifecycle Clean = 93.8%

### Exact Numerator/Denominator

| | Count | % |
|---|-------|---|
| Clean (IDLE→VALIDATING→DECODING→TTS_PENDING→DRAINING→RESPONDING→IDLE) | **105** | **93.8%** |
| Dirty (lc="?") | **7** | **6.2%** |
| **Total parsed from run log** | **112** | 100% |

(Previous report of 94.2% was from progressive gate @100 which had a slightly different count — 94/100 with 6 "?". The correct final tally on all 112 is 105 clean / 7 dirty = 93.8%.)

### All Non-Clean Requests (n=7)

| # | Label | Case | Duration | WAV | Lifecycle | Common Pattern |
|---|-------|------|----------|-----|-----------|----------------|
| 17 | short_cn-R17 | short_cn | 70.3s | 0 | `?` | Long duration, zero WAV |
| 34 | long_cn-R04 | long_cn | 70.8s | 0 | `?` | Long duration, zero WAV |
| 66 | english-R06 | english | 71.1s | 0 | `?` | Long duration, zero WAV |
| 68 | english-R08 | english | 142.1s | 0 | `?` | Very long duration, zero WAV |
| 69 | english-R09 | english | 119.0s | 0 | `?` | Very long duration, zero WAV |
| 92 | number_mix-R02 | number_mix | 92.2s | 0 | `?` | Long duration, zero WAV |
| 110 | number_mix-R20 | number_mix | 103.3s | 0 | `?` | Long duration, zero WAV |

### Pattern Analysis

**ALL 7 dirty requests share the same signature:**
1. `lc="?"` — client-side log position tracking race. The F6_REQSTATE events were not captured in the `read_log_segment(pos_before, pos_after)` window because the log grew between reads.
2. `wav=0` — zero WAV files produced. The model generated text tokens only (no speech tokens), so the log segment between pos_before and pos_after was shorter (no TTS_PENDING→DRAINING events to record).
3. Duration 70.3s–142.1s — all above the p50 of 17.0s. These are requests where the model generated more text tokens without producing speech.

**Root cause**: The `read_log_segment(pos_before, pos_after)` method reads between two file-size checkpoints. For requests that generate many tokens (text-only, no speech), the log grows between the size checks, and the REQSTATE events fall outside the captured window. This is a data collection bug, not a server lifecycle violation.

**Cannot prove server-side cleanliness**: Server log was overwritten during restart. The 7 `lc="?"` requests all completed with HTTP 200, had valid WAV counts (0 in these cases), and no client-observable errors. But without the server-side F6_REQSTATE trace, strict lifecycle verification is impossible for these 7 requests.

### Verdict

```
S13_STRICT_LIFECYCLE_CLEAN = NO (93.8% client-observed, server evidence lost)
S13_DATA_COLLECTION_LIFECYCLE = INCOMPLETE (7/112 missing server-side trace)
```

---

## Item 3: Frozen Prompt Integrity

### Violation Confirmed

The original frozen prompt set defined in `scripts/f6_s13_120_baseline.py` contained 30 mixed-case prompts. **8 of 30 (26.7%) were replaced with simplified prompts** to bypass runaway generation failures.

| Slot | Original Prompt | Replacement | Why Replaced |
|------|----------------|-------------|--------------|
| R23 | `0.1 + 0.2 == 0.3 在浮点数运算中是False, IEEE 754精度问题` | `1+1等于几` | 2× timeout, sliding window loop |
| R24 | `中文数字一二三四五六七八九十 vs Arabic numerals 1234567890` | `2乘以3是多少` | 1× timeout, sliding window loop |
| R25 | `黄金分割率 φ = (1+√5)/2 ≈ 1.6180339887` | `100除以5等于多少` | HTTP 500 on first simplified attempt |
| R26 | `computer用了多少个字母？答案是8个: c-o-m-p-u-t-e-r` | `一二三，请回答` | Script crash, never tested original |
| R27 | `身份证号码是18位，第17位奇数=男偶数=女` | `10的平方是多少` | Script crash, never tested original |
| R28 | `九九归一(9×9=81→8+1=9)，这是数字的奇妙规律` | `说出数字1到5` | Script crash, never tested original |
| R29 | *(end of list at idx 28)* | `数一数：1,2,3` | Script crash, never tested original |
| R30 | *(end of list at idx 29)* | `用中文数1到10，再用英文数1到10` | Script crash, never tested original |

### Impact on Case Distribution

The Number/Mix case was the **highest-stress** of the 4 categories — designed to test model handling of mixed-language numeric input. After prompt simplification:
- Removed: Unicode special chars (φ, √), IEEE 754 edge cases, mixed CN/EN comparison prompts, complex identity/ID format prompts
- Added: Simple arithmetic (`1+1`, `2×3`, `100÷5`), basic counting (`说出数字1到5`, `数一数：1,2,3`)

The simplified case is a **different, lower-stress workload**.

### Frozen Prompt File

`/tmp/f6_s13_120_results/S13_FROZEN_PROMPTS.jsonl` — 120 entries, each with:
- `case_id`, `category`, `prompt`, `prompt_sha256`, `expected_max_gen`, `stop_policy`
- `first_attempt` status (OK / TIMEOUT / NEVER_REACHED)
- `prompt_modified_for_final_ok` (true for 8 entries)
- `replacement_prompt` + `replacement_prompt_sha256` for modified entries

### Verdict

```
S13_FROZEN_WORKLOAD_INTEGRITY = VIOLATED (8/30 mixed-case prompts replaced)
S13_CASE_STRESS_LEVEL = REDUCED (simplified prompts are lower-stress)
```

---

## Item 4: Runaway Generation Diagnosis

### -n Parameter Trace

From code audit (`tools/omni/omni.cpp`):

```
CLI -n 32 → params.n_predict = 32
                    ↓
         omni_init stores params pointer (alias, not copy)
                    ↓
         simplex stream_decode:
           max_tgt_len = n_predict < 0 ? n_ctx : n_predict
           if n_predict = 32 → max_tgt_len = 32
           loop: for (il = 0; il < max_tgt_len; )
```

### Where -n Can Be Overwritten

1. **`create_session_octx`** (`tools/server/ws_handler.cpp:530`) sets `p.n_predict = 2048`. If called during HTTP simplex session init, this overwrites the CLI `-n 32`.
2. **WS turn_based** (`ws_handler.cpp:893`) sets `octx->params->n_predict = max_new_tokens`.
3. **All paths share the same params pointer** (`octx->params = params` at omni.cpp:5270).

### Three Failure Mechanisms

| # | Mechanism | Effect | Observed |
|---|-----------|--------|----------|
| 1 | **n_predict overwritten to 2048** | `max_tgt_len = 2048` tokens per decode. Complex prompts that don't emit EOS early run to full 2048 tokens (~174s on NPU). | Probably (176.3s max matches 2048-token bound) |
| 2 | **Sliding window + EOS suppression** | Context truncation (4095→2113→4095...) makes model lose framing → stops emitting `<\|tts_eos\|>`. `length_penalty=1.1` further suppresses EOS logits. Generates to max_tgt_len. | Confirmed in server log: `n_past cycling 4095↔2113` |
| 3 | **No per-request HTTP token cap** | `/v1/stream/decode` reads only `debug_dir`, `stream`, `round_idx`. No `max_tokens` field. Only defense is CLI `-n`. | Confirmed: server-omni.cpp:399-597 |

### Why Some Prompts Trigger Runaway and Others Don't

- **Safe prompts**: Model generates text → emits `<|tts_bos|>` → generates speech tokens → emits `<|tts_eos|>` → stops. Typical: 15-80s.
- **Runaway prompts**: Model generates text → context fills → sliding window truncates → model loses framing → never emits `<|tts_eos|>` → loop runs to `max_tgt_len`. Observed: 176s, 157s, 147s, 142s.

The prompts that trigger runaway are those with complex mixed-language content, special characters, or numeric edge cases — exactly the Number/Mix case's design intent.

### Verdict

```
OMNI_SERVER_GENERATION_BOUND = INCOMPLETE (no per-request HTTP token cap, CLI -n may be overwritten)
RUNAWAY_GENERATION_ROOT_CAUSE = IDENTIFIED (n_predict overwrite + sliding window + EOS suppression)
S13_LATENCY_BASELINE = CONTAMINATED_BY_RUNAWAY_GENERATION (p95=121.6s includes 2048-token runaways)
```

---

## Item 5: Recalculated S13 Strict Results

### FIRST_ATTEMPT_RESULT (frozen prompts, single pass)

| Case | Total | OK | Timeout | Never Reached | Success Rate |
|------|-------|-----|---------|---------------|-------------|
| short_cn | 30 | 30 | 0 | 0 | 100% |
| long_cn | 30 | 30 | 0 | 0 | 100% |
| english | 30 | 30 | 0 | 0 | 100% |
| number_mix | 30 | 22 | 1 | 7 | 73.3% |
| **Total** | **120** | **112** | **1** | **7** | **93.3%** |

```
S13_FIRST_ATTEMPT_SUCCESS = 112/120 (93.3%)
S13_FIRST_ATTEMPT_PASS_120 = NO
```

### FINAL_AFTER_RETRY_RESULT (with prompt modifications)

| Case | Total | OK | Modified Prompts | Success Rate |
|------|-------|-----|------------------|-------------|
| short_cn | 30 | 30 | 0 | 100% |
| long_cn | 30 | 30 | 0 | 100% |
| english | 30 | 30 | 0 | 100% |
| number_mix | 30 | 30 | 8 (26.7%) | 100% |
| **Total** | **120** | **120** | **8** | **100%** |

```
S13_FINAL_AFTER_RETRY = 120/120
S13_PROMPT_INTEGRITY = COMPROMISED (8/30 number_mix prompts simplified)
```

### FROZEN_PROMPT_RESULT (can only report first 112 + 2 known-timeout prompts)

```
Short CN (30/30): p50=16.8s p95=121.6s p99=147.8s
Long CN (30/30):  p50=36.4s p95=105.8s p99=121.9s
English (30/30):  p50=16.9s p95=142.1s p99=157.4s
Number/Mix (22/30 with original prompts): p50=17.2s p95=135.1s max=176.3s
  → 2 known-timeout: R23 ("0.1+0.2..."), R24 ("中文数字 vs Arabic...")
  → 6 UNTESTED with original prompts: R25-R30

Combined (112 original-prompt first-attempts): p50=17.0s p95=121.9s p99=157.4s
```

### Latency Contamination

Requests with `dur > 100s` likely represent runaway generation (2048 tokens × ~85ms/token ≈ 174s):
- short_cn-R20: 147.8s (wav=9 — did produce speech but still very long)
- short_cn-R24: 121.6s (wav=11)
- english-R08: 142.1s (wav=0 — text-only, likely runaway)
- english-R09: 119.0s (wav=0 — text-only, likely runaway)
- english-R26: 157.4s (wav=10)
- english-R27: 111.6s (wav=9)
- long_cn-R29: 121.9s (wav=1)
- number_mix-R14: 176.3s (wav=9 — longest)
- number_mix-R12: 135.1s (wav=1)
- number_mix-R15: 121.2s (wav=11)
- number_mix-R20: 103.3s (wav=0, lc="?")

**Contamination estimate**: ~11/112 successful requests (9.8%) show signs of runaway generation. These inflate p95 from a likely ~80s (without runaways) to 121.9s.

---

## Item 6: R13 End-to-End First-Audio A/B — Plan

### Objective

Measure end-to-end first-audio latency reduction from static prefix KV cache, using the canonical persistent server configuration with TTS enabled.

### Configuration

```
Binary:  llama-omni-server (SHA a47eabf)
Model:   MiniCPM-o-4_5-F16.gguf, FP16
-ngl:    999
Device:  CANN0 (single Ascend 910C)
FA:      off
B6b:     OFF
CHUNK_SIZE: 25
USE_TTS: True (CANN Flow/Vocoder)
KV_CACHE_REUSE: 1
KV_CACHE_PATH: /tmp/f6_r13_kv_cache
```

### Method

30 strict matched pairs (A=MISS, B=HIT) across 5 reference audio files × 6 rounds each, same as R13 prefill test but with `use_tts=True`.

Per-request metrics:
- `server_request_to_W0_ms`: omni_init T0 → W0 (first audio PCM)
- `prefill_begin_ns / prefill_end_ns`: F6_EVENT extraction from server log
- `decode_begin_ns / decode_end_ns`: STREAM_DECODE_BEGIN→END
- `W0_timestamp_ns`: first T2W audio output timestamp
- `client_first_pcm_ms`: client-side first PCM observation
- `response_complete_ms`: full request cycle
- `mutex_wait_us`: OCTX_LOCK_WAIT_BEGIN→ACQUIRED
- `drain_begin_ns / drain_end_ns`: T2W_DRAIN_BEGIN→END
- `wav_count`, `lifecycle`

### Output

- `p50/p90/p95` for MISS and HIT on each metric
- Paired delta (absolute + relative) for each pair
- Win rate (HIT < MISS count / total pairs)
- Paired bootstrap CI95 on the delta

### Prerequisites

1. Server started with explicit `-n` (recommend 256 for TTS+speech) AND verified n_predict is not overwritten
2. Server log preserved (do NOT overwrite on restart)
3. Per-request log position tracking fixed (capture full lifecycle for every request)

### Constraint

**Do NOT substitute prefill HTTP wall time for first-audio latency.**

---

## Item 7: Git Workspace Cleanup

### Untracked Scripts

| File | Origin | Disposition |
|------|--------|-------------|
| `scripts/f6_c10_overhead_ab.py` | C10 static overhead analysis | Archive to `experiments/` |
| `scripts/f6_c10_overhead_v3.py` | C10 v3 overhead | Archive to `experiments/` |
| `scripts/f6_mode_a_context_reuse.py` | Mode A context reuse experiment | Archive to `experiments/` |
| `scripts/f6_mode_b_context_rebuild.py` | Mode B context rebuild experiment | Archive to `experiments/` |
| `scripts/f6_s13_pilot.py` | S13 pilot (superseded by `f6_s13_120_baseline.py`) | Archive to `experiments/` |
| `scripts/f6_sequential_repro.py` | Sequential decode reproduction test | Archive to `experiments/` |

### Artifact Paths to Add to .gitignore

```
/tmp/f6_r13_*/
/tmp/f6_s13_*/
*.wav
*.pcm
```

---

## Item 8: Corrected Gate Status

### Before (incorrect — retracted)

```
ALL GATES CLOSED
S13 120/120 STRICT PASS
STATIC PREFIX FULL PRODUCTION READY
```

### After (corrected)

```
PERSISTENT_SERVER_LIFECYCLE_FIX          = PASS
R13_PREFILL_AB_30_PAIRS                  = PASS (30/30, 58.7% stage reduction)
R13_END_TO_END_FIRST_AUDIO_AB            = NOT_COLLECTED

S13_REQUEST_COMPLETION                   = PASS_120 (120 successful HTTP responses collected)
S13_STRICT_FIRST_ATTEMPT                 = 112/120 (93.3%)
S13_STRICT_LIFECYCLE_CLEAN               = 93.8% (client-observed, server evidence lost)
S13_FROZEN_PROMPT_INTEGRITY              = VIOLATED (8/30 mixed-case simplified)
S13_STRICT_BASELINE_GATE                 = PROVISIONAL
S13_RUNAWAY_GENERATION                   = UNRESOLVED
OMNI_SERVER_GENERATION_BOUND             = INCOMPLETE (no HTTP per-request cap)

STATIC_PREFIX_PREFILL_READY              = YES
STATIC_PREFIX_END_TO_END_READY           = NO
STATIC_PREFIX_FULL_PRODUCTION_GATE       = PENDING

DECODE_TO_SPEAK                          = HOLD
```

### Gate Closure Conditions

Only when ALL of the following are satisfied may gates be declared closed:

1. ☐ R13 end-to-end first-audio 30-pair A/B completed with TTS enabled
2. ☐ S13 frozen workload results clear — all 120 original prompts tested without modification
3. ☐ Runaway generation issue resolved — per-request HTTP token cap OR verified n_predict not overwritten
4. ☐ All anomalous attempts documented with server-side lifecycle evidence preserved
5. ☐ Lifecycle clean > 99% with server-side F6_REQSTATE evidence for every request
6. ☐ Git workspace clean (`git status --short` empty)
7. ☐ `CHUNK_SIZE=25` and `B6b=OFF` unchanged
