# R13 Canonical Static Prefix KV Cache A/B — Raw Data Manifest

**Date**: 2026-08-03 13:45–13:50 UTC
**Gate**: R13_STATIC_PREFIX_PREFILL_AB = PASS

## Environment

| Item | Value |
|------|-------|
| Host | Linux 5.10.0-216.0.0.115.oe2203sp4.aarch64 |
| CANN | /usr/local/Ascend/cann-9.1.0-beta.1 |
| NPU | Ascend910C (dual-die, 2× Ascend910 chips) |
| Server PID | 18026 |
| Server port | 18093 |

## Binary SHAs

```
a47eabf48fb2a6ff3b87de215e814e400db40d51b6fc7569e8e38711059ea034  build-f6-phase3-relwithdebinfo/bin/llama-omni-server
eca859f1176f686985bcf4320e1ef968646f749692f5582189331f8b3c3cc40d  build-f6-phase3-relwithdebinfo/bin/libomni.so
```

## Model SHA

```
d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de  /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf
```

## Git

```
HEAD: ec6dbc7a1050732cd43fe12f1407780f82ed4d49
Branch: perf/f6-decode-to-speak
Worktree: /workspace/llama.cpp-omni-f6
Build dir: build-f6-phase3-relwithdebinfo
```

## Server Config

```
Cmd: ./build-f6-phase3-relwithdebinfo/bin/llama-omni-server -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf -ngl 999 --device CANN0 -c 4096 -b 512 -ub 512 --split-mode layer --port 18093 --host 127.0.0.1 -n 32
Env:
  OMNI_KV_CACHE_REUSE=1
  OMNI_KV_CACHE_PATH=/tmp/f6_r13_kv_cache
```

## Data Files

| File | Path | SHA256 | Size |
|------|------|--------|------|
| CSV (30 rows) | `/tmp/f6_r13_ab_results/canonical_kv_ab.csv` | `f77fcd96c724e8357c93d47d36baa75405533f9ad6c37df178d63cdf25853f3b` | 7633 |
| Report JSON | `/tmp/f6_r13_ab_results/canonical_kv_ab_report.json` | `2cdf2e9cd709032c46498b57d4b5e3e01f64fae5140313980cadf28e388849d1` | 1892 |
| Evidence Manifest | `/tmp/f6_r13_ab_results/R13_EVIDENCE_MANIFEST.json` | (self-referential) | — |
| Server Log | `/tmp/f6_r13_kvcache_srv.log` | Binary log | — |

## Script SHA

```
58c4a79e7bd7b8c6578ad08be42c3ce2e9f97129b30a8d1f256b8163e3121205  /workspace/llama.cpp-omni-f6/scripts/run_canonical_kv_ab.py
```

## Results Summary

| Metric | Value |
|--------|-------|
| Valid pairs | 30/30 |
| MISS prefill p50 | 206ms |
| HIT prefill p50 | 85ms |
| Delta p50 | 121ms |
| Stage reduction | 58.7% |
| Speedup | 2.4× |
| n_past | 130 |
| tokens_reused | 130 |
| Distinct cache keys | 5 |
| Collisions | 0 |
| CPU fallback | 0 |
| NOT_REUSABLE | 0 |
| BUSY | 0 |
| Timeout | 0 |
| mutex_wait p50 | 2.0µs |
| handler_hold p50 | 400ms |
| Lifecycle | IDLE→VALIDATING→DECODING→RESPONDING→IDLE |

## Gate Status

| Gate | Status |
|------|--------|
| R13_STATIC_PREFIX_PREFILL_AB | **PASS** |
| R13_END_TO_END_FIRST_AUDIO_AB | **NOT_COLLECTED** |

## npu-smi Output

```
NPU ID  Chip ID  Chip Logic ID  Chip Phy-ID  Chip Name
0      0        0              0            Ascend910
0      1        1              1            Ascend910
0      2        -              -            Mcu
```

## Document Artifacts

| Document | Path |
|----------|------|
| Final Report | `/workspace/llama.cpp-omni-f6/docs/tracking/f6_lifecycle/R13_CANONICAL_STATIC_PREFIX_AB_FINAL.md` |
| Raw Manifest | `/workspace/llama.cpp-omni-f6/docs/tracking/f6_lifecycle/R13_CANONICAL_STATIC_PREFIX_AB_RAW_MANIFEST.md` |
| Evidence Manifest | `/tmp/f6_r13_ab_results/R13_EVIDENCE_MANIFEST.json` |
