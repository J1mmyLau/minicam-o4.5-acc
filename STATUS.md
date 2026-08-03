# F6 Phase 3 — Decode-to-Speak Optimization — 项目状态

## 当前阶段

`Phase 3：R13 COMPLETE` — 全部 R13 Gate 通过，准备进入 S13/S14 或 Decode-to-Speak 优化。

## R13 Gate 总结 (2026-08-03)

| Gate | 状态 | 关键数据 |
|------|------|----------|
| **R13_PER_GEN_ACTIVE** | ✅ PASS | 3/3 sequential; per-generation active eliminates cross-gen blocking |
| **R13_OCTX_MUTEX** | ✅ PASS | correctness PASS; mutex_wait p50=0ms sequential; handler_hold p50=71s |
| **R13_HARDWARE** | ✅ CONFIRMED | 1× Ascend 910C (dual-die), 2× Ascend910 chips, single-card compliant |
| **R13_CANONICAL_KV_CACHE** | ✅ PASS | 30/30 pairs; prefill 2.4× speedup (206→85ms p50); n_past=130 tokens |

## R13 Canonical KV Cache A/B 详细

```
Server:   PID 18026, port 18093
Model:    MiniCPM-o-4_5-F16.gguf, -ngl 999, CANN0
Binary:   a47eabf48fb2a6ff3b87de215e814e400db40d51b6fc7569e8e38711059ea034 @ ec6dbc7
Method:   5 cases × 6 pairs = 30 strict matched pairs (A=MISS, B=HIT)
Cache:    /tmp/f6_r13_kv_cache, OMNI_KV_CACHE_REUSE=1

Results (30/30 valid):
  MISS prefill: p50=206ms, p95=216ms
  HIT prefill:  p50=85ms,  p95=91ms
  Delta:        p50=121ms, p95=128ms
  Speedup:      p50=2.4×,  p95=2.5×
  tokens_reused: 130 (consistent across all pairs)
  5 distinct cache keys, 0 collisions

Integrity:
  CPU fallback:   0
  NOT_REUSABLE:   0
  BUSY:           0
  timeout:        0
  mutex_wait:     p50=2.0µs
  handler_hold:   p50=400ms
  lifecycle:      100% IDLE→VALIDATING→DECODING→RESPONDING→IDLE

Data:   /tmp/f6_r13_ab_results/canonical_kv_ab.csv + report.json
Script: /workspace/llama.cpp-omni-f6/scripts/run_canonical_kv_ab.py
```

## 当前待办

| 优先级 | 任务 | 状态 |
|--------|------|------|
| P0 | S13 120/120 baseline | PENDING — next after canonical KV cache |
| P1 | Decode-to-Speak bottleneck optimization | ON HOLD per user instruction |
| P2 | T2W WAV production fix (current config: no WAV output) | DEFERRED |
| P3 | M6 6h mixed-workload soak audit (kvcache-prod worktree) | DEFERRED |

## 约束

- B6b: OFF (frozen)
- CHUNK_SIZE: 25 (frozen)
- 模式: simplex
- FA/speculation/operator fusion: OFF
- NPU: Ascend910C, CANN 9.1.0-beta.1
- Model: MiniCPM-o-4_5
- `-ngl 100/999 --device CANN0`

## Git

```
HEAD:    ec6dbc7 fix(f6-phase3): R13 per-generation active accounting
Branch:  perf/f6-decode-to-speak
Worktree: /workspace/llama.cpp-omni-f6
```
