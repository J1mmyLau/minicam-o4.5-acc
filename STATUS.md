# F6 Phase 3 — Decode-to-Speak Optimization — 项目状态

## 当前阶段

`Phase 3：R13 Prefill PASS, S13 PROVISIONAL` — 静态前缀 Prefill 验证完成，S13 严格基线尚未关闭。详见 [S13 Strict Audit](docs/tracking/f6_lifecycle/S13_STRICT_AUDIT_AND_GATE_CORRECTION.md)。

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

## S13 120/120 严格审计 (2026-08-04)

**之前声明已撤回**：`S13 120/120 PASS`, `ALL GATES CLOSED`。

### 修正状态

| 指标 | 值 | 状态 |
|------|-----|------|
| S13_REQUEST_COMPLETION | 120 个最终成功 HTTP 响应 | ✅ |
| S13_STRICT_FIRST_ATTEMPT | 112/120 (93.3%) | ❌ |
| S13_STRICT_LIFECYCLE_CLEAN | 93.8% (客户端观测)，服务端证据丢失 | ❌ |
| S13_FROZEN_PROMPT_INTEGRITY | 8/30 混合 case Prompt 被简化 | ❌ |
| S13_RUNAWAY_GENERATION | 3 次超时 + ~11 次疑似失控长请求 | ❌ 未解决 |
| OMNI_SERVER_GENERATION_BOUND | HTTP /v1/stream/decode 无 per-request token cap | ❌ 不完整 |
| S13_STRICT_BASELINE_GATE | | **PROVISIONAL** |

### 关键发现

1. **n_predict 被覆盖**：`create_session_octx` 把 CLI `-n 32` 覆盖为 2048，导致单次 decode 可生成至 2048 token
2. **KV sliding window + EOS 抑制**：滑动窗口截断上下文 → 模型丢失框架 → 停止输出 `<|tts_eos|>` → 生成到 max_tgt_len
3. **无 HTTP per-request token cap**：`/v1/stream/decode` 不接受 `max_tokens` 字段
4. **8 个 Prompt 被简化**：原混合 case 中 26.7% 的 Prompt 被替换为简单算术/计数题，改变了 case 分布
5. **服务端生命周期证据丢失**：服务器重启时日志被覆盖，所有 120 请求的 F6_REQSTATE 不可恢复

## 当前待办 (优先级排序)

| 优先级 | 任务 | 状态 |
|--------|------|------|
| P0 | 补 R13 端到端首音 30 对 A/B (USE_TTS=True) | PENDING |
| P0 | 修复 S13 无限生成问题 (per-request HTTP token cap) | PENDING |
| P0 | 用原始 Prompt 重新运行 number_mix R23-R30 | PENDING |
| P1 | 审计 Git 未跟踪脚本 → 归档或提交 | PENDING |
| P2 | M6 6h mixed-workload soak audit | DEFERRED |
| P3 | Decode-to-Speak bottleneck optimization | HOLD |

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
