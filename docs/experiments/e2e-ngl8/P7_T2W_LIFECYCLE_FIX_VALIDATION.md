# P7 T2W Lifecycle Fix Validation Report

**Date:** 2026-07-25  
**Commit:** `91e5674` fix(t2w): defer T2W drain to omni_free — TTS must finish first  

## Test Configuration

- Binary: `build/bin/llama-omni-cli` (SHA256: `764a706a2e888b9423dc1a90fee47b350cc9f27dbe3de1478515ca78d48b78d3`)
- Model: `MiniCPM-o-4_5-Q4_K_M.gguf`
- Backend: GGML_CANN (Ascend 910 ×2)
- Env: `OMNI_T2W_DEVICE=cann-flow-only OMP_NUM_THREADS=8 OMNI_T2W_DRAIN_TIMEOUT_MS=10000`
- Script: `scripts/run_t2w_regression_par.sh`

## Regression Results

| Metric | Value |
|---|---|
| Total requests | 150 |
| Passes | 50 passes × 3 cases (0, 1, 3) |
| AUDIO_SUCCESS | 150 (100%) |
| VALID_NO_SPEECH | 0 |
| **rc0_without_audio** | **0** (critical gate) |
| DRAIN_TIMEOUT | 0 |
| PIPELINE_FAILURE | 0 |
| Non-zero rc | 12 (all rc=124 from process timeout on long responses; all produced audio) |

### Per-Case Breakdown

| Case | Total | Audio | No Speech | Avg WAVs |
|---|---|---|---|---|
| 0 (short prompt) | 50 | 50 | 0 | 16.1 |
| 1 (medium prompt) | 50 | 50 | 0 | 20.6 |
| 3 (long prompt) | 50 | 50 | 0 | 22.3 |

### WAV Distribution

| Stat | Value |
|---|---|
| Min | 1 |
| Max | 73 |
| Mean | 19.7 |
| Total WAVs generated | 2948 |

## Two-Phase Stop Protocol (Verified)

```
TTS generation complete
→ TTS join
→ T2W EOS signal (cv.notify_all)
→ Worker processes EOS: force-flush buffer → feed_window(is_final=true) → is_final_processed.store(true)
→ drain_cv.wait_for(timeout, predicate: is_final_processed) → drain complete
→ T2W thread_running = false
→ T2W join
→ Output verification (wav_count, terminal_output classification)
```

## Condition Variable Audit

- **Predicate:** `is_final_processed.load(std::memory_order_acquire)` ✓
- **Spurious wakeup:** Handled by predicate re-check ✓
- **Bounded timeout:** `OMNI_T2W_DRAIN_TIMEOUT_MS` (default 5000ms, regression used 10000ms) ✓
- **Timeout path:** Returns `DRAIN_TIMEOUT`, non-zero behavior, structured error ✓
- **Shutdown idempotency:** `is_final already processed` early-return (line 4942) ✓
- **No sleep-based drain:** Confirmed — zero sleep/usleep/nanosleep in drain paths ✓
- **No double join:** `joinable()` check before every `join()` ✓

## Source References

- `tools/omni/omni.cpp:4934` — `t2w_drain_signal_and_wait()`: EOS signal + CV wait with predicate
- `tools/omni/omni.cpp:4884` — `omni_stop_threads()`: Does NOT touch T2W (TTS join happens later)
- `tools/omni/omni.cpp:5033-5053` — `omni_free()`: TTS.join → drain → T2W.stop → T2W.join
- `tools/omni/omni.cpp:5095-5117` — `omni_prepare_for_reuse()`: Same protocol
- `tools/omni/omni.h:75-92` — `T2WDrainState`, `T2WTerminalOutput` enums
- `tools/omni/omni.cpp:9640-9665` — Worker CV wait with `eos_received` wake condition
- `tools/omni/omni-cli.cpp` — `request_start_time` set before `stream_prefill()`

## Gate Verdict

**GATE_PASSED.** T2W lifecycle is stable. rc0_without_audio = 0 across 150 requests.
All drain paths use condition variables with predicate and bounded timeout.
No fixed sleeps, no double joins, no use-after-free.

## Data

- CSV: `/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/p7_3-regression/regression_par.csv`
- Logs: `/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/p7_3-regression/logs/`
- Runner log: `/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/p7_3-regression/runner_par.log`
