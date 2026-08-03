# R13 Canonical Static Prefix KV Cache A/B — Final Report

**Date**: 2026-08-03 13:45–13:50 UTC
**Worktree**: `/workspace/llama.cpp-omni-f6`
**Branch**: `perf/f6-decode-to-speak`
**HEAD**: `ec6dbc7`

## Configuration

| Parameter | Value |
|-----------|-------|
| Model | MiniCPM-o-4_5-F16.gguf |
| -ngl | 999 |
| Device | CANN0 |
| Context | -c 4096 -b 512 -ub 512 --split-mode layer |
| Server port | 18093 |
| n_predict | 32 (-n 32) |
| KV cache | OMNI_KV_CACHE_REUSE=1, OMNI_KV_CACHE_PATH=/tmp/f6_r13_kv_cache |
| TTS | OFF (USE_TTS=False) |
| B6b | OFF (frozen) |
| CHUNK_SIZE | 25 (frozen) |
| Binary SHA256 | a47eabf48fb2a6ff3b87de215e814e400db40d51b6fc7569e8e38711059ea034 |

## Method

5 test cases (distinct audio files 0000–0004.wav, each with image) × 6 rounds = 30 strict matched pairs.
Each pair: A(MISS) = clear disk cache → omni_init → prefill → decode; B(HIT) = omni_init → prefill → decode.
Different audio files produce 5 distinct cache keys. No cross-case cache interference.

## Results — 30/30 Valid Pairs

### Prefill Timing

| Metric | p50 | p90 | p95 | mean | min | max |
|--------|-----|-----|-----|------|-----|-----|
| MISS prefill | 206ms | 216ms | 216ms | 218ms | 202ms | 554ms |
| HIT prefill | 85ms | 91ms | 91ms | 86ms | 82ms | 91ms |
| **Delta** | **121ms** | **126ms** | **128ms** | **133ms** | **117ms** | **468ms** |
| **Speedup** | **2.4×** | **2.5×** | **2.5×** | **2.6×** | **2.3×** | **6.4×** |

> Stage reduction: **58.7%** (prefill p50: 206ms → 85ms)
> C1-R1 first pair outlier (554ms MISS, cold NPU); excluding it (n=29): MISS p50=206ms, HIT p50=84ms, delta p50=121ms

### Per-Case Consistency

| Case | Audio | Pairs | MISS p50 | HIT p50 | Delta | Speedup |
|------|-------|-------|----------|---------|-------|---------|
| C1 | 0000.wav | 6 | 205ms | 85ms | 123ms | 2.4× |
| C2 | 0001.wav | 6 | 205ms | 85ms | 120ms | 2.4× |
| C3 | 0002.wav | 6 | 208ms | 87ms | 122ms | 2.4× |
| C4 | 0003.wav | 6 | 208ms | 91ms | 122ms | 2.3× |
| C5 | 0004.wav | 6 | 206ms | 84ms | 121ms | 2.4× |

### KV Cache Mechanics

- **Cache boundary**: n_past = 130 tokens (system prompt: assistant prompt + voice clone prompt + reference audio + BOS/special tokens)
- **Cache key components**: model arch hash, system prompt hash, ref_audio hash + size, audio sample rate/channels, n_ctx, -ngl, n_keep
- **5 distinct cache keys**, 0 collisions, 0 cross-contamination
- **Cache file size**: ~19MB per key (FP16 KV cache for 130 tokens × 4096 dim × layers)
- **All MISS**: KV cache SAVED to disk, cache_misses incremented
- **All HIT**: cache_hits=1, cache_misses=0, tokens_reused=130 (full prefix reuse)

### F6_EVENT Timing

| Metric | Value |
|--------|-------|
| mutex_wait (p50) | 2.0µs |
| handler_hold MISS (p50) | ~430ms |
| handler_hold HIT (p50) | ~400ms |
| Lifecycle | 100% IDLE→VALIDATING→DECODING→RESPONDING→IDLE |

### Integrity

| Check | Count |
|-------|-------|
| CPU fallback | 0 |
| NOT_REUSABLE | 0 |
| BUSY | 0 |
| Timeout | 0 |
| Cross-request contamination | 0 |

## 130 vs 62 Reused Tokens — Explanation

The old CLI diagnostic (Q4_K_M, -ngl 0, `run_kv_cache_ab.sh`, pass 2, case 0–8)
reported `reused_tokens=62`. The current canonical server reports `reused_tokens=130`.

**Root cause**: Different system prompt construction.

| Factor | Old CLI | Canonical Server |
|--------|---------|------------------|
| Binary | llama-omni-cli | llama-omni-server |
| Mode | CLI one-shot | Persistent server |
| System prompt tokens | 62 | 130 |
| Model quantization | Q4_K_M | FP16 |
| -ngl | 0 (CPU) | 999 (NPU) |

The server constructs a larger system prompt (130 tokens) including assistant prompt,
voice clone prompt, reference audio encoding, and BOS tokens. The CLI had a shorter
system prompt (62 tokens). Both are correct for their respective code paths.

**These are NOT comparable experiments.** The canonical server test supersedes the old
CLI diagnostic for production gate evaluation.

## Gate Status

| Gate | Status | Evidence |
|------|--------|----------|
| R13_STATIC_PREFIX_PREFILL_AB | **PASS** | 30/30 pairs, 58.7% prefill reduction |
| R13_END_TO_END_FIRST_AUDIO_AB | **NOT_COLLECTED** | USE_TTS=False; W0/PCM/drain not measured |

**Overall**: Prefill stage production gate = PASS. End-to-end first audio gate = pending S13.

## Data Manifest

| File | Path | SHA256 |
|------|------|--------|
| CSV (30 rows) | `/tmp/f6_r13_ab_results/canonical_kv_ab.csv` | (see evidence manifest) |
| Report JSON | `/tmp/f6_r13_ab_results/canonical_kv_ab_report.json` | (see evidence manifest) |
| Evidence Manifest | `/tmp/f6_r13_ab_results/R13_EVIDENCE_MANIFEST.json` | (see evidence manifest) |
| Test Script | `/workspace/llama.cpp-omni-f6/scripts/run_canonical_kv_ab.py` | (see evidence manifest) |
| Server Log | `/tmp/f6_r13_kvcache_srv.log` | Binary log |

## Verdict

> Static prefix KV cache in canonical Persistent Server (FP16, -ngl 999, CANN0):
> **30/30 strict matched pairs PASS. Prefill p50 reduced from 206ms to 85ms (58.7% stage reduction, 2.4× speedup).**
> The ~59% static prefix benefit previously reported from CLI diagnostics has been
> independently reproduced on the canonical NPU persistent server configuration.
> End-to-end first-audio metrics (W0, PCM, drain) were not collected in this test
> (USE_TTS=False) and must be measured in S13.
