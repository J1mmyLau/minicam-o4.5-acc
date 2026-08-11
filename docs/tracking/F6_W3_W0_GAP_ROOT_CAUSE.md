# F6 W3: W0 Gap Root Cause

**Date:** 2026-07-31
**Data:** `F6_W3_64_PROFILE_RECONCILIATION.csv` (64 profiles from R3 single-request measurement)

---

## Profile Classification

| Classification | Baseline (step=10) | Candidate (step=5) | Total |
|---------------|-------------------|-------------------|-------|
| VALID_W0 | 0 | 1 | 1 |
| W0_NOT_REACHED_FLOW_STARTED_BUT_NOT_COMPLETED | 1 | 0 | 1 |
| W0_NOT_REACHED_T2W_NEVER_DEQUEUED | 0 | 16 | 16 |
| W0_NOT_REACHED_DEQUEUED_BUT_FLOW_NOT_STARTED | 0 | 0 | 0 |
| W0_NOT_REACHED_TALKER_TOKEN_BUT_NO_T2W_SUBMIT | 11 | 5 | 16 |
| W0_NOT_REACHED_TTS_WOKE_BUT_NO_AUDIO_TOKEN | 24 | 5 | 29 |
| W0_NOT_REACHED_LLM_TOKEN_BUT_NO_TTS_WAKE | 0 | 1 | 1 |
| **Total** | **36** | **28** | **64** |

## Detailed Findings

### 1. VALID_W0: 1/64 (1.6%) — Candidate Warmup Only

```
candidate, req_idx=0, gen=1, W0=4878ms
  G4=636ms, Q0=636ms
  flow_start=636ms, flow_end=4482ms
  vocoder_start=4482ms, vocoder_end=4878ms
  client_first_audio=4878ms
```

This is the only complete profile. It's the warmup request which had 120s drain before the next request, allowing the full async pipeline to complete before `reset()` was called again.

### 2. FLOW_STARTED_BUT_NOT_COMPLETED: 1/64

```
baseline, req_idx=0, gen=1, W0=0
  G4=668ms, Q0=668ms
  flow_start=668ms, flow_end=0 (never completed)
```

Baseline warmup: Flow started at 668ms but never completed before the next request's `reset()` cleared the global atomics. With step=10, the Talker takes longer to accumulate 25 tokens, so G4 is later (668ms vs 636ms for candidate), and the 120s drain wasn't enough for Flow to complete? 

Actually, this is more likely a timing issue: the profile JSON was dumped at decode return time, before Flow completed. The 120s drain happens AFTER the JSON is already dumped. The `flow_start` was already set (it's a global atomic set by the T2W thread as soon as Flow begins), but `flow_end` was still 0 when the JSON was written.

Wait — this suggests the warmup decode returns BEFORE 120s drain. Let me re-check. The script does:
1. Send prefill + decode for warmup (blocks until decode returns)
2. `time.sleep(120)` — drain
3. Start sending real requests

So the warmup profile JSON is dumped at decode return time (step 1), then the 120s drain happens (step 2), then subsequent requests start (step 3). 

During step 2, the T2W/Flow/Vocoder pipeline runs and potentially completes. But the JSON was already written! W0 is missed because:
- For baseline warmup: Flow started (668ms) but didn't complete before JSON dump
- For candidate warmup: Flow+Vocoder completed (4878ms) before JSON dump — meaning the decode response BLOCKED until audio was ready

The candidate warmup having W0 suggests that with step=5, the server's first decode blocks until first audio is produced (special initialization path). The baseline with step=10 doesn't block long enough for Flow to complete.

### 3. T2W_NEVER_DEQUEUED: 16/28 (Candidate Only)

All 16 are in the candidate session. This means G4 (t2w_submit) was recorded but the T2W thread never dequeued the tokens. The T2W queue push happened, but:
- The T2W thread was busy processing previous request's audio
- Or the T2W thread hadn't started its next cv.wait cycle
- By the time T2W dequeued, `reset()` had already been called for the next request

This only affects candidate because with step=5, G4 happens much faster (earlier TTS wake → faster 25-token accumulation). The T2W thread can't keep up.

### 4. TALKER_TOKEN_BUT_NO_T2W_SUBMIT: 16/64

These profiles have G3 (first audio token) but not G4 (T2W submit). The Talker produced at least one audio token, but 25-token accumulation didn't complete before:
- The Talker was preempted by the next request (simplex mode)
- Or the buffer never reached CHUNK_SIZE=25

Baseline (11): With step=10, the Talker starts later, fewer tokens generated before next request
Candidate (5): With step=5, better but still not always enough

### 5. TTS_WOKE_BUT_NO_AUDIO_TOKEN: 29/64 (Largest Category)

These profiles have G0 (tts_wake) but not G3. The TTS worker woke up, but the Talker didn't produce a first audio token. This is the stale write pattern: the TTS worker's events from request N are rejected because `active_generation_id` has advanced to N+1 by the time the Talker loop runs. The `record()` call returns false, the once-guard (`load() == 0`) is defeated by the sentinel (-1), and G3 is never recorded.

## Failure Mode Analysis

```
                    Baseline (36)   Candidate (28)
                    ─────────────   ──────────────
VALID_W0                    0 (0%)         1 (4%)
Flow incomplete             1 (3%)         0 (0%)
T2W backlog                 0 (0%)        16 (57%)  ← Candidate-specific: faster G4 overwhelms T2W
Stale TTS events           24 (67%)        5 (18%)  ← Baseline-specific: slower Talker → more stale
25-token not reached       11 (31%)        5 (18%)
Other                       0 (0%)         1 (4%)
```

### Baseline Failure Chain (step=10):
```
D2→G0 (TTS wake): ~290ms — late wake
  → Talker starts late
  → G3 frequently rejected as stale (67% — next request already started)
  → When G3 succeeds, 25-token accumulation cuts into next request window
  → Only 1/36 reaches G4 (Flow started but JSON already dumped)
  → 0/36 reaches W0
```

### Candidate Failure Chain (step=5):
```
D2→G0 (TTS wake): ~115ms — early wake (B6b benefit)
  → Talker starts earlier → G3 succeeds more often (79% vs 33%)
  → G4 also succeeds more often (61% vs 3%)
  → BUT: T2W thread can't keep up with faster TTS → 57% T2W backlog
  → Even when T2W dequeues, profile JSON already dumped
  → Only warmup (1/28) gets W0
```

## The First Determined Lifecycle Breakpoint

The profile JSON dump at `omni.cpp:13355` is the **first concrete breakpoint** where W0 is lost:

```
BEFORE DUMP (synchronous path):
  D0 ✓ D2 ✓ G0 ✓ G3 ✓ G4 ✓  ← All recorded before dump

AFTER DUMP (async path):
  Q0 ✗ Flow ✗ Vocoder ✗ W0 ✗  ← None recorded before dump
```

The JSON is dumped when `stream_decode()` returns. At that point, the T2W worker hasn't even dequeued yet (for back-to-back requests). The entire Flow+Vocoder pipeline (~4.2s) happens AFTER the profile is finalized.

## Verdict

```
W0_GAP_ROOT_CAUSE = PROFILE_DUMP_BEFORE_ASYNC_PIPELINE_COMPLETION

PRIMARY BREAKPOINT:
  e2e_profile_dump_json() at omni.cpp:13355
  Called synchronously at stream_decode() return
  T2W/Flow/Vocoder have not started or are still running
  W0 is ALWAYS 0 at dump time (except when server blocks on first audio)

SECONDARY BREAKPOINT:
  e2e_stage.reset() at omni.cpp:12608
  Called at next request start
  Clears all per-stage timestamps (including G0/G3/G4 from previous request)
  Bumps active_generation_id, causing T2W thread's W0 record() to be rejected

TERTIARY BREAKPOINT:
  Global flow/vocoder atomics (L12611-12614)
  Cleared by each reset()
  Even if Flow/Vocoder complete during drain, values wiped by next request

NOT SIMPLY "async pipeline limitation":
  It's a specific lifecycle ordering bug:
  1. Profile finalized BEFORE async pipeline completes
  2. Generation bumped BEFORE async events recorded
  3. Global atomics cleared BEFORE async events complete
```
