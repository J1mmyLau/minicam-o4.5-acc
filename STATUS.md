# F6 Phase 3 — Decode-to-Speak Optimization — 项目状态

## 当前阶段

`Phase 3：R13 Prefill PASS, S13 PROVISIONAL, Phase 2 Bottleneck 分析 COMPLETE` —
静态前缀 Prefill 验证完成，S13 严格基线尚未关闭（详见 [S13 Strict Audit](docs/tracking/f6_lifecycle/S13_STRICT_AUDIT_AND_GATE_CORRECTION.md)）。
**Phase 2（6 步指令）已全部完成**：decode→speak 仅占 W0 的 2.9%（142ms），T2W CPU
inference 占 93%（4490ms）；第一候选实验（CANN T2W/VOC 设备迁移）把 W0 p50 从 4798ms
降至 **894ms（−81.4%）**。见 [Step 6 报告](docs/F6_PHASE2_STEP6_CANN_T2W_AB.md)。

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
| P0 | ~~修复 S13 无限生成问题 (per-request HTTP token cap)~~ | ✅ DONE (e159b3ee) |
| P0 | 补 R13 端到端首音 30 对 A/B (USE_TTS=True) | PENDING |
| P0 | 用原始 Prompt 重新运行 number_mix R23-R30 (targeted regression) | ✅ DONE (7997acf) |
| P0 | Full strict S13 120 re-run with frozen prompts | PENDING |
| P1 | 审计 Git 未跟踪脚本 → 归档或提交 | PENDING |
| P2 | M6 6h mixed-workload soak audit | DEFERRED |
| P3 | Decode-to-Speak bottleneck optimization | ✅ Phase 2 完成 (6 步) — 首音 4.83s→0.89s (CANN T2W 迁移) |

## Step 2-5 代码修改摘要 (2026-08-04)

**Binary**: `e159b3ee418cc8079e9dbb1f219bf98ed7e2eb4eb25a05ad9ccd21a143e188c9`

### 修改的文件

| 文件 | 变更 |
|------|------|
| `tools/omni/omni.h` | +`OmniStopReason` 枚举 (EOS/MAX_TOKENS/WALL_TIMEOUT/CLIENT_DISCONNECT/ERROR), +`omni_stop_reason_name()`, +per-request fields (stop_reason, generated_token_count, request_sliding_window_count, eos_detected, cli_n_predict, request_max_tokens, request_wall_timeout_ms, request_start_wall_ns) |
| `tools/omni/omni.cpp` | stream_decode: entry reset counters, save cli_n_predict, wall-time check before each token generation, eos_detected tracking, stop_reason determination after loop, sliding window delta computation |
| `tools/server/server-omni.cpp` | `/v1/stream/decode`: parse `max_tokens` + `wall_timeout_ms`, set per-request limits on octx, include runtime evidence in non-streaming response |
| `tools/server/ws_handler.cpp` | `create_session_octx`: save/restore `n_predict` around WS default (2048) to prevent cross-contamination of HTTP simplex sessions |

### Token cap semantics (per user spec)
- CLI `-n` = server default (saved as `cli_n_predict` at first decode)
- HTTP `max_tokens` = per-request cap (0 = use n_predict)
- effective = `max_tokens > 0 ? max_tokens : n_predict`
- `create_session_octx` no longer silently overwrites CLI `-n` → 2048 (save/restore pattern) |

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
HEAD:    271265b docs(f6-phase2): Step 6 CANN T2W A/B — W0 4798→894ms (−81.4%)
Branch:  perf/f6-decode-to-speak
Worktree: /workspace/llama.cpp-omni-f6
```

## Phase 2 完成记录 (2026-08-04, 6 步指令)

| 步 | 交付物 | Commit |
|----|--------|--------|
| 1 | Phase 1 冻结（closure + SHA manifest） | 1f08d18（先前） |
| 2 | Latency budget — decode→speak=142ms(2.9%), T2W=93% | f9a6241 |
| 3 | Decode→Speak 内部分解 — 12 类未插桩 → DEFER | 06f261a |
| 4 | MTP audit — MTP_NOT_REACHABLE_WITH_CURRENT_MODEL | 1916743 |
| 5 | Amdahl ranking — T2W CANN move = OPTIMIZE_FIRST | 7c0aa56 |
| 6 | CANN T2W A/B — W0 4798→894ms (−81.4%), 32/32, CI95 [−4220,−3732] | 271265b |

核心结论：首音延迟的瓶颈是 **T2W CPU inference（93%）**，非 LLM Decode→Speak（2.9%）。
CANN 设备迁移（纯环境变量，零代码改动）实现 5.0× request→first-audio。约束全满足
（CHUNK_SIZE=25 / B6b / MTP 均未改动）。
