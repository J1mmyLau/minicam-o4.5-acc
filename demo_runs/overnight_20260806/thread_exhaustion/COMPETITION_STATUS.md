# F6 Competition Phase — Initial Status

**Date:** 2026-08-06
**Phase:** INTERNAL_FIX_CLOSED → COMPETITION_MAINLINE

---

## 1. Clean Rebuild

```
SOURCE_HEAD              = b0400d8
TARGET                   = llama-omni-server
BUILD_RESULT             = PASS
BUILD_TOOLCHAIN          = CMake Release, CANN 9.1.0-beta.1

OLD_BINARY_SHA256        = 2bfb2e5028c4f0cf5b8a9e17b22c2cd071505db9e0baa9afc456c00bae84ceb4  (Aug 5 build)
OLD_BINARY_SIZE          = 1,186,672 bytes
NEW_BINARY_SHA256        = f23bbedbbeb3cc2fa910c44986c04a107e874ffc68c950fe5be172ec3349a0da  (unstripped)
NEW_BINARY_SHA256_STRIP  = b4a51fbd6b8b9085bfa77753a8c909f7a056ba2666803c2df7c86e040e0d035a  (stripped)
NEW_BINARY_SIZE          = 10,140,928 bytes (unstripped) / 8,286,360 bytes (stripped)

REPRODUCIBLE_BINARY      = FAIL
  SHA256 differs. Old binary (1.2MB) vs new (8.3MB stripped) suggests different
  build configuration (possibly BUILD_SHARED_LIBS differed). Exact old build flags
  not recorded.

FUNCTIONAL_SMOKE         = PASS
  Server starts, health check returns {"status":"ok"}, responds on port 8081.
  Graceful shutdown via SIGTERM confirmed.
```

---

## 2. Accuracy Gates — BLOCKED

```
OFFICIAL_ACCURACY_GATE   = NOT_RUN

Reason: ALL four benchmarks blocked by missing official starter kit.

Dry-run output:
  VideoMME:   missing_official_assets=YES, MODEL_PATH unset, OFFICIAL_SCRIPT unset → exit 2
  Daily-Omni: missing_official_assets=YES, MODEL_PATH unset, OFFICIAL_SCRIPT unset → exit 2
  TTS-Seed:   missing_official_assets=YES, MODEL_PATH unset, OFFICIAL_SCRIPT unset → exit 2

benchmark.yaml confirms:
  daily_omni:  BLOCKED_BY_OFFICIAL_STARTER_KIT
  tts_seed:    BLOCKED_BY_OFFICIAL_STARTER_KIT
  video_mme:   BLOCKED_BY_OFFICIAL_STARTER_KIT

Datasets present:
  /workspace/benchmarks/Video-MME/     (25MB)
  /workspace/benchmarks/Daily-Omni/    (166MB) — includes qa.json, test_model/
  /workspace/benchmarks/seed-tts-eval/ (15MB) — includes run_wer.py, cal_wer.sh

Infrastructure present but unusable without OFFICIAL_SCRIPT:
  /workspace/llama.cpp-omni-operator/competition/adapters/:
    adapter_video_mme.py    (tag: ee22811 — WRONG version)
    adapter_daily_omni.py   (tag: ee22811 — WRONG version)
    adapter_tts_seed.py     (tag: ee22811 — WRONG version)
    llama_omni_adapter.py   (tag: ee22811 — WRONG version)

  /workspace/llama.cpp-omni-f6/submission/scripts/:
    run_video_mme.sh        (requires OFFICIAL_SCRIPT)
    run_daily_omni.sh       (requires OFFICIAL_SCRIPT)
    run_tts_seed.sh         (requires OFFICIAL_SCRIPT)

NOTE: Operator adapters reference tag "ee22811" — a DIFFERENT server version
      from our candidate b0400d8. Cannot use without adaptation.

OFFICIAL_ACCURACY_GATE     = BLOCKED_BY_OFFICIAL_STARTER_KIT
```

---

## 3. Demo Gates

```
Demo source:   /workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo @ ba7fa9c
Demo scripts:  /workspace/llama.cpp-omni-f6/submission/scripts/run_demo_gate.sh

D1-D3 (Text):  PASS  (previously verified, see f6-demo-d1-d3-text-pass.md)
D4-D12:        NOT_RUN

Demo test infrastructure exists:
  /workspace/llama.cpp-omni-f6/third_party/MiniCPM-o-Demo/tests/
    test_api.py, test_chat.py, test_e2e.py, test_duplex.py,
    test_integration.py, test_runtime_media.py, test_runtime_protocol.py,
    bench_duplex_ws.py, e2e_realtime.py, run_all_tests.sh

OFFICIAL_DEMO_GATE         = NOT_RUN
```

---

## 4. Updated Candidate Identity

```
SOURCE_BASE_SHA              = bdd4550
SOURCE_HEAD_SHA              = b0400d8
SESSION_FIX_COMMITS          = 4 (on top of bdd4550)
UNCOMMITTED_SOURCE_CHANGES   = demo_runs/, docs/fix/, submission/
SERVER_BINARY_SHA256         = f23bbedbbeb3cc2fa910c44986c04a107e874ffc68c950fe5be172ec3349a0da  (NEW, unstripped)
SERVER_BINARY_SHA256_STRIP   = b4a51fbd6b8b9085bfa77753a8c909f7a056ba2666803c2df7c86e040e0d035a  (NEW, stripped)
  NOTE: Old binary (2bfb2e50...) was overwritten by clean rebuild.
        SHA256 differs — REPRODUCIBLE_BINARY=FAIL.
        This is expected without reproducible build toolchain configuration.

RUNTIME_ARGS                 = -m <MODEL> --host 0.0.0.0 --port 8080 -ngl 99 --ctx-size 2048 --batch-size 512 --ubatch-size 512 -t 4
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

## 5. Current Blockers

| Item | Status | Details |
|------|--------|---------|
| Clean rebuild | PASS | Binary functional but not reproducible |
| Accuracy VideoMME | BLOCKED | No official harness |
| Accuracy Daily-Omni | BLOCKED | No official harness |
| Accuracy TTS-Seed ASV | BLOCKED | No official harness |
| Accuracy TTS-Seed WER | BLOCKED | No official harness |
| Demo D4-D12 | NOT_RUN | Demo infrastructure exists, not executed |
| Official RTF spec | NOT_PROVEN | All provisional per METRIC_CONTRACT.md |
| Official starter kit | NOT_ARRIVED | Root blocker for accuracy + RTF |

---

## 6. Final Status

```
FUNCTIONAL_STABILITY           = PASS (109/109 cumulative)
THREAD_EXHAUSTION_MITIGATION   = PASS_WITH_-t_4
THREAD_COUNT_PLATEAU           = NO
SHARED_CGROUP_PID_SAFETY       = NOT_PROVEN

DRAIN_FUNCTIONAL_GATE          = PASS
DRAIN_LOG_CLEANLINESS          = FAIL

WS_SESSION_E2E_RTF_F16_P50     = 6.65
WS_SESSION_E2E_RTF_F16_P90     = 11.41
OFFICIAL_SPEAK_TO_WAV_RTF      = NOT_PROVEN

CLEAN_REBUILD                  = PASS
REPRODUCIBLE_BINARY            = FAIL

OFFICIAL_ACCURACY_GATE         = BLOCKED_BY_OFFICIAL_STARTER_KIT
OFFICIAL_DEMO_GATE             = NOT_RUN

RUNTIME_CONFIG_CANDIDATE       = YES_WITH_-t_4
SOURCE_RELEASE_CANDIDATE       = CONDITIONAL
OFFICIAL_COMPETITION_READY     = NO
```
