# F6 S13 Closure Archive

Frozen Phase 1 (static-prefix KV cache production) evidence. **DO NOT MODIFY.**

## Status

```text
PERSISTENT_SERVER_LIFECYCLE       = PASS
HTTP_TOKEN_CAP                    = PASS
S13_STRICT_BASELINE               = PASS_120_OF_120
RUNAWAY_GENERATION                = FIXED
FROZEN_WORKLOAD_INTEGRITY         = PASS

STATIC_PREFIX_PREFILL_AB          = PASS        (prefill p50 210→86ms, 2.5×)
STATIC_PREFIX_E2E_FIRST_AUDIO_AB  = PASS        (request→W0 4.69s→4.59s)
STATIC_PREFIX_E2E_DELTA_P50       = -120ms
STATIC_PREFIX_E2E_RELATIVE_GAIN   ≈ 2.6%
STATIC_PREFIX_KV                  = INTERNAL_PRODUCTION_READY / DEFAULT_OFF / SIMPLEX_USE_TTS_ONLY
OFFICIAL_BENCHMARK_PASS           = NOT_CLAIMED
```

Production scope (validated only):
- simplex, USE_TTS=true, single Ascend 910C, FP16 model, current canonical config.
- NOT extended to: duplex, multi-concurrency, other models.

## Layout

```
docs/f6-s13-closure/
├── README.md                    ← this file
├── manifests/
│   └── SHA256SUMS               ← binary + model + data + script hashes
├── raw-data/
│   ├── step7/                   ← S13 strict 120 baseline (final + 120 incremental + server log)
│   └── step8/                   ← R13 E2E 30-pair A/B (final + 30 incremental + server log)
└── scripts/                     ← analysis scripts (copies for reproducibility)
```

## Key Numbers

| Metric | MISS | HIT | Delta |
|--------|-----:|----:|------:|
| Prefill p50 | 210 ms | 86 ms | −125 ms (2.5×) |
| Request→W0 p50 | 4.69 s | 4.59 s | −120 ms |
| First-audio relative | — | — | ≈ 2.6% |
| 95% CI | — | — | [37, 249] ms |

Correctness: 30 SAVED / 30 HIT / 130 tokens reused / CPU fallback=0 / NOT_REUSABLE=0 / timeout=0 / cross-request contamination=0.

## Verification

```bash
# Check binary + model integrity
cd /workspace/llama.cpp-omni-f6
sha256sum -c docs/f6-s13-closure/manifests/SHA256SUMS --ignore-missing 2>/dev/null | grep -E "OK|FAIL" | head -20
```
