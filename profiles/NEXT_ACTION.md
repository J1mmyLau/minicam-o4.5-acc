# NEXT ACTION

**Date**: 2026-07-30
**Session**: GATE_RE-EVALUATION CHECKPOINT
**Current State**: RUNTIME_FIX_CHECKPOINT — 3 solid gates, 6+ requiring extended evidence
**HEAD**: 0828de2
**Tag**: cann-failfast-gates-pass-20260730 (RUNTIME_FIX_CHECKPOINT — NOT final benchmark candidate)

---

## IMMEDIATE (After Compact Recovery)

1. Read STATUS.md, HANDOFF.md, NEXT_ACTION.md, AUDIT.md
2. Verify git HEAD, branch, worktree
3. Check for running processes (llama-omni-server, benchmark, msprof)
4. Check NPU state (npu-smi info)
5. Verify binaries still exist and SHA256 matches

---

## EXECUTION ORDER (Autonomous — DO NOT ASK TO CONTINUE)

### C2: R11 Extended Resource Lifecycle Gate

```
Target: 110+ mixed requests in single FP16 clean-build server
Breakdown:
  - 20 text
  - 20 audio
  - 10 image
  - 10 video
  - 10 video+audio
  - 20 TTS
  - 10 client disconnect then recover
  - 10 error request then recover

Track per-request:
  request_id, modality, session_id, init, prefill, decode, done, reset/close
  backend state, context state, stream state, Graph state, T2W state
  CANN error, fallback, crash, deadlock
  RSS, HBM, FD, thread count

Resource lifecycle counters:
  backend create/destroy, context create/destroy, stream create/destroy
  graph create/destroy, T2W worker create/join, session create/destroy

Pass conditions:
  unexpected failure = 0, crash = 0, deadlock = 0
  CANN error = 0, CPU fallback = 0
  cross-sample contamination = 0
  no monotonic resource growth
  valid resource state transitions
```

### C3: R6 Extended Thread Context Gate

```
Use C2 pressure test data to verify:
  - T2W worker bound to correct CANN context before compute
  - context not freed by another thread prematurely
  - Flow/Vocoder not using destroyed stream
  - Graph capture/replay creates no lock cycle
  - reset does not wait on worker join (and vice versa)
  - deferred init runs expected count only

Enable deadlock watchdog:
  last_progress_time, thread_state, queue_depth, mutex_owner
```

### C4: Full 6×10 Multimodal Loop

```
10 text, 10 audio, 10 image, 10 video, 10 video+audio, 10 TTS
Same server process, single-flight, single protocol
Unique sample_id per sample, raw request/response saved
TTS: Voice A+X, Voice B+X, Voice A+X repeated
```

### C5-C7: Video + RTF + KV

```
C5: Controlled video A/B/C with frame/audio SHA256 evidence
C6: 30+ matched pairs, p50/p95/bootstrap CI
C7: OFF/MISS/HIT, A/B/C prefixes, targeted corruption
```

### C8-C10: Pilot + Data + Freeze

```
C8: Shallow benchmark pilot (Daily-Omni ≥3, Seed-TTS ≥2 ZH + 2 EN, Video-MME ≥3)
C9: Data/evaluator acquisition (ModelScope, shared drives, mirrors)
C10: New tag after all gates pass
```

---

## DO NOT

- Ask "是否继续" / "需要我继续吗"
- Call any gate PASS without sufficient evidence
- Enter Im2col optimization
- Call `cann-failfast-gates-pass-20260730` a final benchmark candidate
- Claim ALL_RUNTIME_GATES_PASS or FINAL_FP16_CANDIDATE_FROZEN
- Wait for user input unless externally blocked (credentials, URLs, hardware)
