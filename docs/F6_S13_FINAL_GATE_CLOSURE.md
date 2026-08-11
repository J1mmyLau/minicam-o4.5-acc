# F6 S13 — Final Gate Closure
## 2026-08-04 | COMPLETE

---

## Gate Matrix Summary

### Phase 1: Correctness & Lifecycle (Steps 2-6, from previous session)

| Gate | Status | Evidence |
|------|--------|----------|
| R7 CROSS_REQUEST_CONTAMINATION | **PASS** | Fix verified, no cross-request state leak |
| R9 C9_30_30 | **PASS** | 30/30 verified |
| S13_PILOT_5_5 | **PASS** | 5/5 clean |
| F6 LIFECYCLE_FIX | **PASS** | 3 sequential decode requests all succeeded, ctx stays valid |
| R12 POLLING_MEASUREMENT | **PASS** | ALL drains complete via CV notify; 500ms polling = safety net |
| R13 PER_GEN_ACTIVE | **PASS** | active_t2w_generation per-generation; 3/3 seq PASS |
| R13 OCTX_MUTEX | **PASS** | mutex_wait p50=0ms; correctness PASS |

### Phase 2: KV Cache Baseline (Step 7 — USE_TTS=False)

| Gate | Status | Key Data |
|------|--------|----------|
| R13_CANONICAL_KV_CACHE_AB | **PASS** | 30/30 PASS; FP16+CANN0; prefill 2.4× speedup (206→85ms p50) |
| R13_KV_CACHE_FUNCTIONAL | **PASS** | 62 reused tokens, cache_miss=0 |

### Phase 3: TTS E2E Baseline (Step 7 — USE_TTS=True)

| Gate | Status | Key Data |
|------|--------|----------|
| S13_STRICT_120 | **PASS** | 120/120 valid; 111 EOS + 9 MAX_TOKENS; 0 errors; 0 wall timeouts |
| S13_FROZEN_PROMPT_INTEGRITY | **PASS** | No prompt modifications; unmodified frozen prompts |
| S13_RUNAWAY_GENERATION | **PASS** | No sliding windows triggered; 0 runaway |
| S13_SERVER_EVIDENCE | **PASS** | Server log confirms all 120 requests |
| S13_STRICT_BASELINE | **PASS** | p50=17.0s p95=121.6s; TTS WAV confirmed |

### Phase 4: KV Cache with TTS (Step 8 — USE_TTS=True)

| Gate | Status | Key Data |
|------|--------|----------|
| R13_E2E_30_VALID_PAIRS | **PASS** | 30/30 server-log confirmed (30 SAVED + 30 HIT) |
| R13_E2E_PREFILL_SPEEDUP | **PASS** | Δp50=125ms, speedup 2.5× (MISS=210ms → HIT=86ms) |
| R13_E2E_FIRST_AUDIO_DELTA | **PASS** | Δp50=120ms, CI95 [37, 249]ms (HIT faster, small but real) |
| R13_E2E_KV_CACHE_INTEGRITY | **PASS** | 0 CPU fallback, 0 NOT_REUSABLE, 130 tokens reused |
| R13_E2E_BOOTSTRAP_CI95 | **PASS** | [37, 249] ms |
| R13_E2E_COMPLETE | **PASS** | ALL GATES CLOSED |

---

## Overall Conclusion

**ALL GATES PASSED. KV Cache is production-ready for simplex USE_TTS=True workloads on Ascend 910C.**

### Key Quantitative Results:

| Metric | Without KV Cache | With KV Cache | Improvement |
|--------|-----------------|---------------|-------------|
| Prefill time (p50) | 210ms | 86ms | **2.5× speedup** |
| Prefill time (p95) | 244ms | 103ms | 2.4× |
| First-audio W0 (p50) | 4693ms | 4590ms | Δ=120ms (2.6%) |
| First-audio W0 (p95) | 5174ms | 5063ms | Δ=111ms |
| Total request (p50) | ~17.0s | ~16.9s | ~0.6% |
| KV cache size | — | 18.3 MB | Fixed |
| Cache key | 0ff6e4094311a89e | Same | 1 unique key per ref_audio |

### Interpretation:

1. **Prefill is the primary beneficiary**: KV cache reduces prefill from ~210ms to ~86ms (2.5×). This is the saved cost of not re-computing the 130-token system prompt on every request.

2. **First-audio W0 is essentially unchanged**: The TTS generation pipeline dominates end-to-end latency. KV cache saves ~120ms in prefill but this is <3% of total first-audio latency.

3. **Correctness is solid**: 30 consecutive MISS→SAVED+HIT→LOADED cycles with zero CPU fallbacks and zero NOT_REUSABLE events. The KV cache mechanism correctly invalidates and reloads between requests.

4. **The 30-pair A/B shows consistency**: Δprefill p50=125ms with tight distribution (p95=153ms). The first pair showed the highest delta (482ms) due to first-run CANN graph compilation — subsequent pairs settle at a stable 100-150ms delta.

---

## Artifacts

| Artifact | Path |
|----------|------|
| Step 7 baseline results | `/tmp/f6_s13_step7_results/` |
| Step 8 A/B results | `/tmp/f6_s13_step8_results/step8_r13_e2e_first_audio_ab_v6.json` |
| Step 8 test script | `/workspace/llama.cpp-omni-f6/scripts/f6_s13_step8_r13_e2e_first_audio_ab.py` |
| Server log (Step 7) | `/tmp/f6_s13_step7_v3_srv.log` |
| Server log (Step 8) | `/tmp/f6_s13_step8_v6_srv.log` |
| KV cache files | `/tmp/omni-kvcache/omni_kvcache_0ff6e4094311a89e.bin` (18.3 MB) |

---

## Recommendations

1. **DEFAULT_ON for simplex TTS workloads**: The KV cache provides a consistent 2.5× prefill speedup with zero correctness regressions.

2. **First-audio optimization requires TTS pipeline work**: Since TTS generation dominates W0, further latency improvements must come from TTS/T2W acceleration (NPU offload, batching, streaming).

3. **Cache key coverage**: Currently 1 unique key for all test cases (same ref_audio). Multi-voice deployments with different ref_audio files will generate additional cache entries (~18.3 MB each).

4. **Log buffering**: The test script encountered intermittent KV parse failures due to server stderr buffering. Consider adding `setvbuf(stderr, NULL, _IONBF, 0)` to the server for real-time log availability.

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
