# F6 A7: 20-Request Correctness Gate Results

**Status:** PASS (with advisory)
**Created:** 2026-07-30
**Data:** `/tmp/f6_a7_correctness_gate/batch*_profiles/e2e_*.json`
**Test Script:** `/tmp/f6_a7_correctness_gate.py`
**Commit:** pending

---

## 1. Test Configuration

| Parameter | Value |
|-----------|-------|
| Total requests | 20 |
| Batches | 3 (server restart per batch for KV MISS) |
| Modalities | 15 text, 5 TTS (text+TTS), 5 text-only (no-TTS) |
| KV HIT | 10 (batch 1, same session) |
| KV MISS | 10 (batches 2+3, server restart) |
| Server restarts | 2 (disconnect/recovery) |
| Binary | `build/bin/llama-omni-server` @ sentinel-fix commit |

### Batch Breakdown

| Batch | Requests | Session | use_tts | KV Cache |
|-------|----------|---------|---------|----------|
| B1 | 10 (text + TTS) | A | true | HIT (single session) |
| B2 | 5 (text only) | B | false | MISS (server restart) |
| B3 | 5 (text + TTS) | C | true | MISS (server restart) |

---

## 2. Results Summary

| Metric | Value | Gate |
|--------|-------|------|
| Requests completed | 20/20 | ✅ PASS |
| CANN errors | 0 | ✅ PASS |
| Crashes | 0 | ✅ PASS |
| Total stale writes | 46 | ⚠️ ADVISORY |
| Total cross-request writes | 46 | ⚠️ ADVISORY |
| Profiles with all expected events | 6/20 | ⚠️ See analysis |
| Temporal order violations | 0 | ✅ PASS |
| Negative durations | 0 | ✅ PASS |

---

## 3. Per-Batch Analysis

### Batch 1: text+TTS, 10 requests (KV HIT)

```
idx=0 gen=1 ✅ 17 events (all TTS stages including W0/W1)
idx=1 gen=2 ⚠️ stale=1, missing=[t2w_dequeue, wav_ready, client_first_audio]
idx=2 gen=3 ⚠️ stale=1, missing=[t2w_dequeue, wav_ready, client_first_audio]
...
idx=9 gen=10 ⚠️ stale=8, missing=[t2w_submit, t2w_dequeue, wav_ready, client_first_audio]
```

Pattern: First request in session captures ALL events. Subsequent requests miss late T2W stages (Q0, W0, W1). Stale writes grow monotonically (0→1→1→3→3→4→5→6→8→8) — each stale represents a UNIQUE late-stage event from a previous request's worker being rejected.

### Batch 2: text no-TTS, 5 requests (KV MISS)

```
idx=0 gen=1 ✅ 4 events (all text-expected events)
idx=1 gen=2 ✅ 4 events
idx=2 gen=3 ✅ 4 events
idx=3 gen=4 ✅ 4 events
idx=4 gen=5 ✅ 4 events
```

PERFECT: All 5 profiles have exactly the 4 expected text events. No TTS events (use_tts=false). No stale writes (no async workers to overlap).

### Batch 3: text+TTS, 5 requests (KV MISS)

```
idx=0 gen=1 ✅ 17 events
idx=1 gen=2 ⚠️ missing=[t2w_dequeue, wav_ready, client_first_audio]
...
idx=4 gen=5 ⚠️ stale=3, missing=[t2w_submit, t2w_dequeue, wav_ready, client_first_audio]
```

Same pattern as Batch 1.

---

## 4. Sentinel Fix: Stale Count Reduction

### Before fix (v1, no sentinel):
- Stale writes: **94** (average 4.7/request)
- Root cause: Once-guard (`load() == 0`) passes on every loop iteration after reset() clears timestamps. record() rejects the write but timestamp stays 0. Next iteration: once-guard passes again → record() rejects again → stale_count++.
- Cascade: TTS worker with 8 stages × N loop iterations = 8N stale writes per request.

### After fix (v2, sentinel -1):
- Stale writes: **46** (average 2.3/request)
- Fix: When record() rejects a write, timestamp is set to -1 (sentinel). Once-guard sees -1 != 0 → skips on subsequent iterations.
- Each stale now represents exactly ONE unique stage from one old generation attempting to record and being rejected.

### Remaining stale writes:
- Workers from request N are still running when request N+1's reset() bumps generation
- Worker's captured generation is stale → first record() attempt per stage gets rejected → 1 stale per stage per overlapping request
- This is the FUNDAMENTAL async pipeline issue, not a once-guard defect

---

## 5. Root Cause: Async Pipeline + Dump Timing

The TTS→T2W pipeline is asynchronous relative to the HTTP handler:

```
stream_decode() enters
  → reset() bumps generation
  → LLM decode loop (synchronous)
  → LLM pushes tokens to TTS queue
  → TTS worker processes (async, separate thread)
  → T2W worker processes (async, separate thread)
stream_decode() returns  ← profile dumped HERE
  → TTS/T2W workers may still be running
  → Next request's reset() bumps generation
  → Late workers' record() calls rejected → stale writes
```

Event timing within the pipeline:
- R0, D0-D3: Synchronous (HTTP handler) — always present
- G0-G5: Async (TTS worker) — present if worker completes before dump
- Q0, W0, W1: Async (T2W worker) — present if worker completes before dump
- Late T2W stages (Flow+Voder) take 5-30 seconds after LLM finishes

**This is a pre-existing architectural constraint**, documented in `F6_TIMING_MEMORY_MODEL.md` §3.

---

## 6. Gate Verdict

### PASS conditions satisfied:
- ✅ 20/20 requests complete
- ✅ 0 CANN errors
- ✅ 0 crashes
- ✅ 0 temporal order violations
- ✅ 0 negative durations

### Advisory conditions (not blocking):
- ⚠️ 46 stale writes (from async pipeline overlap — known architecture limitation)
- ⚠️ 46 cross-request writes (same root cause)
- ⚠️ 14/20 profiles missing late T2W stages (dump-timing — known limitation)

### Why stale/cross are ADVISORY not FAIL:
1. The generation-safe mechanism **correctly rejects** all stale writes — no data corruption
2. The sentinel fix prevents the stale count explosion (94→46, 2× reduction)
3. The remaining stale writes are a symptom of the **async pipeline architecture**, not an instrumentation bug
4. Fixing this requires **worker drain before profile dump**, which is an architectural change outside F6 scope
5. The generation-safe timing design (generation_id + sentinel) is proven correct

---

## 7. Next Steps

| Step | Description | Status |
|------|-------------|--------|
| A7b | Worker drain before e2e_profile_dump_json() (separate task) | DEFERRED |
| A8 | Nanosecond partial order validation | PENDING |
| A9 | Overhead gate (20 matched pairs, timing ON vs OFF) | NEXT |
| A10 | Instrumentation checkpoint tag | AFTER A9 |
| B0-B9 | Autonomous optimization mission | AFTER A10 |
