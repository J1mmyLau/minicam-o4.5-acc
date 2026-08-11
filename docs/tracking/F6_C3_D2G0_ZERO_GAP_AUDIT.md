# F6 C3: D2→G0 Zero-Gap Audit

**Date:** 2026-08-01
**Source:** 120 paired raw JSON profiles from `/tmp/f6_fp16_w10/`

---

## Raw Data

```
D2 = llm_first_token (stages_ms)
G0 = tts_wake (stages_ms)
D2→G0 = G0 - D2
```

### Full Distribution

| Config | n | D2→G0 = 0ms | D2→G0 = 1ms | D2→G0 > 1ms | p50 | p95 |
|--------|---|-------------|-------------|-------------|-----|-----|
| OFF | 120 | 87 (72.5%) | 5 (4.2%) | 28 (23.3%) | 0ms | 222ms |
| ON | 120 | 92 (76.7%) | 6 (5.0%) | 22 (18.3%) | 0ms | 98ms |

### Large-Gap Values

| Config | Cluster | Count | Mean | Notes |
|--------|---------|-------|------|-------|
| OFF | 220-229ms | 28 | 222ms | TTS wake delayed ~221ms after first token |
| ON | 97-103ms | 22 | 98ms | B6b reduces delay to ~98ms |

---

## Bimodal Pattern

D2→G0 is NOT always 0ms. It follows a bimodal distribution:

**Mode 1 (72% of requests): D2→G0 ≈ 0ms**
- TTS thread is already awake/waiting when first LLM token arrives
- `tts_wake` recorded in same ms as `llm_first_token`
- No scheduling gap

**Mode 2 (23% of OFF, 18% of ON): Large gap**
- TTS thread is idle/sleeping when first LLM token arrives
- OFF: ~221ms wake latency
- ON: ~98ms wake latency (B6b reduces by ~123ms or 55%)

### B6b Effect When Gap Exists

```
OFF gap: p50 = 222ms (n=28)
ON  gap: p50 = 98ms  (n=22)
Reduction: 124ms (55.9%)
Ratio OFF/ON: 2.3x
```

B6b provides substantial benefit WHEN a scheduling gap exists. However:
- Gap occurs in only ~21% of all requests (pooled)
- 72% of requests have 0ms gap regardless of B6b
- Median delta across ALL 120 pairs = 0ms (bootstrap CI95 [0,0])

---

## Gap Occurrence Pattern

Gaps appear to cluster in specific ABBA blocks. Not purely "first request after restart":

| Position | Total | With Gap > 1ms |
|----------|-------|-----------------|
| A1 (OFF, 1st in block) | 60 | 13 (21.7%) |
| A2 (OFF, 4th in block) | 60 | 15 (25.0%) |
| B1 (ON, 2nd in block) | 60 | 13 (21.7%) |
| B2 (ON, 3rd in block) | 60 | 9 (15.0%) |

Gaps appear in all positions at similar rates. Not explained by cold-start alone.

Some blocks show gap on OFF but not ON (e.g., block_0006: A2 gap=222ms, B2 no gap). Others show gap on ON but not OFF (e.g., block_0011: B1 gap=98ms, A1 no gap). This suggests the gap is workload/timing dependent, not purely a function of server state.

---

## Callsite Audit

### D2: `llm_first_token`
- **Source:** `tools/omni/omni.cpp:13073-13075`
- **Function:** main decode loop (`llama_decode_loop` or equivalent)
- **Thread:** main thread
- **Once guard:** `llm_first_token_logged` boolean
- **Clock:** `ggml_time_ms()` → integer ms
- **Scope:** request-scoped (per-request e2e_stage)

### G0: `tts_wake`
- **Source:** `tools/omni/omni.cpp:7944-7945` and `8662-8663` (two callsites)
- **Function:** TTS worker thread wake point
- **Thread:** TTS thread
- **Once guard:** atomic compare-exchange on `timestamps_ns[STAGE_tts_wake]` (note: field name says `_ns` but stored as ms)
- **Clock:** `ggml_time_ms()` → integer ms
- **Scope:** request-scoped with generation_id guard

### Two G0 callsites

The code records `tts_wake` at TWO locations (7944 and 8662), both guarded by the same atomic once-guard. The second is a fallback for a different wake path. Both use `tts_thread_generation` for scoping.

**Risk:** If the once-guard fails (race condition) or uses a stale generation_id, G0 could be:
1. Recorded from a previous request's wake → stale
2. Recorded from a global fallback → not request-scoped
3. Never recorded → 0ms (default), which would be indistinguishable from "woke at t=0"

But the bimodal pattern (0ms vs ~221ms) argues AGAINST a simple stale-write explanation. If G0 were global/fallback, we'd see random values, not two tight clusters.

---

## Interpretation

The ~221ms OFF gap and ~98ms ON gap likely represent:

**When TTS worker is already waiting on cv:** D2→G0 ≈ 0ms (instant notify→wake in same ms)

**When TTS worker is idle (not waiting):** 
- OFF: TTS worker takes ~221ms to wake, process the token, and start TTS
- ON: With B6b, the earlier token arrival (at 5 vs 10) reduces this to ~98ms

The 221ms/98ms values are very consistent (std dev < 3ms within each cluster), suggesting a deterministic mechanism — possibly:
- TTS worker sleep interval / polling period
- Token accumulation buffer fill time
- CV wait timeout

---

## Corrected Statement

Replace:
```
"D2→G0 = 0ms" or "no scheduling gap in FP16+CANN"
```

With:
```
D2→G0 is BIMODAL:
- Mode 1 (72%): 0ms — TTS worker already waiting, instant wake
- Mode 2 (28% OFF): ~221ms — TTS worker idle wake latency  
- Mode 2 (18% ON): ~98ms — B6b reduces idle wake latency by ~55%
- Median: 0ms (bootstrap CI95 [0,0])
- B6b provides ~124ms benefit in the 21% of requests where gap exists
- Gap mechanism is deterministic (tight value clusters) but source unknown
  (possibly TTS worker polling interval or token accumulation)
```

---

## P9 Prerequisite

The bimodal D2→G0 pattern is one component of the undecomposed G0→T2W dequeue region (~621ms). Without G3 (talker_first_audio_token) and G4 (t2w_submit), we cannot determine:

1. Whether the 221ms/98ms gap is TTS worker wake latency or token accumulation time
2. How many Talker steps occur between G0 and first audio token
3. What fraction of the 621ms is compute vs policy wait vs queue
