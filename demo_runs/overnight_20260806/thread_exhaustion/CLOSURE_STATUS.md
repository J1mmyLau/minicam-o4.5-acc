# F6 Internal Fix Phase — Closure Status

**Date:** 2026-08-06
**Phase:** INTERNAL_FIX → COMPETITION_MAINLINE transition

---

## Legacy Task Closure

```
TASK_382 (Strict A/B mode comparison):  CLOSED
  PROTOCOL_AB_EVIDENCE:  SUFFICIENT
  TEXT_MODE_ROOT_CAUSE:  SESSION_MODE_CONFIGURATION
  NO_FURTHER_ACTION
```

---

## Candidate Identity

```
SOURCE_BASE_SHA              = bdd4550
SOURCE_HEAD_SHA              = b0400d8
SESSION_FIX_COMMITS          = 4
  0021584 fix(ws_handler): unified session finalizer
  17d9542 fix(ws_handler): remove use_tts guard
  7fbf19a fix(ws_handler): KV cache isolation + T2W drain fast-path
  b0400d8 fix(server): expose session cleanup helpers
UNCOMMITTED_SOURCE_CHANGES   = demo_runs/, docs/fix/, submission/
SERVER_BINARY_SHA256         = 2bfb2e5028c4f0cf5b8a9e17b22c2cd071505db9e0baa9afc456c00bae84ceb4
RUNTIME_ARGS                 = -t 4, F16, die0, concurrency=1
THREADS_ARG                  = -t 4
VISIBLE_DIE                  = 0
MODEL_PRECISION              = F16 (server), Q4_K_M (model)
MODEL_SHA256                 = 1237a97ee081b8abebc47aa7dad565701e8f5f904cdc92f6723ac4281bbc0932
DEMO_PATH                    = /workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo
DEMO_COMMIT                  = ba7fa9c
ADAPTER_PATH                 = submission/adapters/ws_adapter.py
ADAPTER_COMMIT               = uncommitted (in submission/ directory)
```

---

## 109/109 Cumulative Session Attribution

```
CUMULATIVE_FUNCTIONAL_SUCCESS = 109/109

RUN_A:
  SESSION_COUNT       = 56 total (2 warmup + 54 measured)
  SERVER_PID          = NOT_RECORDED (PID file overwritten by RUN_B)
  BINARY_SHA256       = 2bfb2e50...
  RUNTIME_ARGS        = -t 4, F16, die0, concurrency=1
  SOURCE_HEAD         = b0400d8
  BASELINE_THREADS    = 641
  DURATION            = 60.9 min
  ERRORS              = 0
  REJECTIONS          = 0
  EVIDENCE            = stability_60min/summary.json, stability_60min/sessions.jsonl

RUN_B:
  SESSION_COUNT       = 55 total (0 warmup, all measured)
  SERVER_PID          = 1451083
  BINARY_SHA256       = 2bfb2e50...
  RUNTIME_ARGS        = -t 4, F16, die0, concurrency=1
  SOURCE_HEAD         = b0400d8
  BASELINE_THREADS    = 695
  DURATION            = 58.5 min
  ERRORS              = 0
  REJECTIONS          = 0
  EVIDENCE            = plateau_60min/plateau_report.json, plateau_60min/sessions.jsonl

NOTE: RUN_A and RUN_B were DIFFERENT server instances (baseline threads differ).
      Both used the SAME binary (2bfb2e50...) and SAME config (-t 4).
      They are NOT a single continuous 109-session run.
```

---

## Final Internal Phase Status

```
FUNCTIONAL_STABILITY           = PASS (109/109 cumulative)
THREAD_EXHAUSTION_MITIGATION   = PASS_WITH_-t_4
THREAD_COUNT_PLATEAU           = NO
PER_WORKER_OMP_RETENTION       = CONFIRMED
SHARED_CGROUP_PID_SAFETY       = NOT_PROVEN

DRAIN_FUNCTIONAL_GATE          = PASS
DRAIN_LOG_CLEANLINESS          = FAIL

WS_SESSION_E2E_RTF_F16_P50     = 6.65
WS_SESSION_E2E_RTF_F16_P90     = 11.41
OFFICIAL_SPEAK_TO_WAV_RTF      = NOT_PROVEN

RUNTIME_CONFIG_CANDIDATE       = YES_WITH_-t_4
SOURCE_RELEASE_CANDIDATE       = CONDITIONAL
OFFICIAL_COMPETITION_READY     = NO
```

---

## Next: Competition Mainline

1. Clean rebuild from b0400d8 with reproducibility check
2. Official accuracy gates: VideoMME, Daily-Omni, TTS-Seed ASV/WER
3. Demo gates D4-D12
4. Official SPEAK→WAV RTF spec alignment
