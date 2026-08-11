# F6 B-Phase: Final Summary

**Status:** COMPLETED (B6b ACCEPTED)
**HEAD:** `4659239` on `perf/f6-decode-to-speak`
**Base:** `d519ebe` (tag: `f6-timing-instrumentation-pass-20260730`)

## Completed

| Step | Description | Result |
|------|-------------|--------|
| B0 | Workload freeze — 120-request reproducible workload | 80 text + 40 TTS, saved to `/tmp/f6_b0_workload/b0_workload_def.json` |
| B1 | 120-request baseline collection | 120 profiles (FULL mode), baseline at `/tmp/f6_b0_workload/b0_baseline.json` |
| B2 | Compute/wait decomposition + Amdahl ranking | TEXT: D1→D2=50.5ms(44%). TTS: G3→G4=316ms(51%), D2→G0=264ms(43%) |
| B5 | Amdahl ranking (from B2 data) | See B2 results |
| B6a | MAX_QUEUE_SIZE=2 experiment | **REJECTED** — D2→G0 +29ms (+13.6%) |
| B6b | First-chunk step_size=5 experiment | **ACCEPTED** — D2→G0 -114ms (-53%) |

## Not Completed / Blocked

| Step | Description | Reason |
|------|-------------|--------|
| B3 | msprof backend reachability | BLOCKED — sandbox timeout (600s) exceeded by CANN profiler startup |
| B4 | (depends on B3) | BLOCKED |
| B7 | Combination testing | N/A — only one optimization accepted |
| B8 | Full regression (120-request) | Quick regression (3 text + 5 TTS) passed; full workload skipped |
| B9 | Final freeze or NO_WORTHWHILE_OPTIMIZATION | B6b accepted as the only worthwhile optimization |

## B6b Details

### Code Change
`tools/omni/omni.cpp` — First LLM chunk pushed after 5 valid TTS tokens (vs 10):
- `stream_decode()` (simplex path): line 12836-12838
- `duplex_do_decode()` (duplex path): line 11703-11706
- Guarded by `ctx_omni->use_tts` — text-only path uses step=10
- Subsequent chunks use full step=10 for audio quality

### Measured Impact
- **D2→G0: 216ms → 102ms (-114ms, -53%)** on identical-prompt A/B test
- **Total TTS path: ~619ms → ~511ms (-108ms, -17%)** estimated from B1 baseline
- No impact on text-only TTFT

### Remaining Bottlenecks
1. G3→G4 (316ms, 62%): Audio token accumulation — 25-token CHUNK_SIZE before T2W submit
2. G0→G3 (39ms, 7%): TTS model startup — already fast
3. G4→W1 (unknown): T2W + Flow + Vocoder — not captured by async profiling

## Artifacts
- `/tmp/f6_b0_workload/` — B0/B1 workload and baseline data
- `/tmp/f6_b6_test/` — B6a MQ_SIZE=2 test data
- `/tmp/f6_b6_test_mq1/` — B6a MQ_SIZE=1 baseline data
- `/tmp/f6_b6b_test/` — B6b first-chunk step=5 test data
- `/tmp/f6_b6b_v2/` — B6b verification data
- `/workspace/llama.cpp-omni-f6/docs/tracking/F6_B6_OPTIMIZATION_RESULTS.md` — detailed report
