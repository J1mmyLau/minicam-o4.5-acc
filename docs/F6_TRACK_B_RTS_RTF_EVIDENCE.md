# F6 — Track B：RTS SPEAK→WAV RTF 证据闭环

Date: 2026-08-14 · Candidate `a77d6a8` + trackA_fixes.patch（Config D）
Directive: 【BYPASS — LONG-RUN FINALIZATION QUEUE】Track B

## 结论（一句话）

RTS SPEAK→WAV 端到端延迟已捕获（1306–2747 ms），但**官方 RTF 指标 = NULL**
（`stage_timing.jsonl` 的 t2w 事件缺 `duration_ms`/`src_cnt`），且候选的 per-chunk
T2W drain 会把 duplex SPEAK turn 楔死（SPEAK=1~3 后 context_state=3 拒绝后续请求）。
Track B 的 RTF 证据链**结论性受阻**，按 directive 关闭并移入证据记录。

## 已捕获证据

| 运行 | SPEAK 数 | SPEAK→WAV 延迟 (mean) | RTF | 文本 |
|---|---|---|---|---|
| `trackB_rts_qsplit0` | 3 | 2747.2 ms (n=3) | NULL | 「没问题，现在是24楼了。」 |
| `trackB_rts_drainfix` | 1 | 1306.0 ms (n=1) | NULL | 「没问题，现」（截断） |

- SPEAK→WAV 延迟 = SPEAK 输入 → WAV 生成（poll）端到端墙钟，非 RTF。
- RTF 官方基线（pristine 服务端 [bench]）：**1.083**（official 1.087），见
  `f6-server-rtf-baseline-a`。候选 Config D 未复测该 [bench] RTF。
- 官方 RTF 入口（`benchmark_client.py`）本就可跑不了（WS adapter 占位、无
  HTTP `/v1/stream`）—— 见 `f6-speak-to-wav-rtf-status`。

## 楔死根因（候选特有，已定位，未修）

RTS 路径（`server-omni.cpp` HTTP handler → `stream_decode` → `omni_duplex_drain_tts_audio`）
在每个 chunk 后无条件调 per-chunk drain（`t2w_drain_signal_and_wait`），四条件谓词：

```
tts_producer_done >= gen && queued==0 && (active_gen==0 || active_gen>gen)
    && final_processed >= gen   [ + vocoder 侧 final_vocoder_processed >= gen (pipeline) ]
```

超时 `t2w_get_drain_timeout_ms(pending, worker_active)` = `5000 + pending*15000
(+60000 if worker_active)`。当 SPEAK turn 的残留 TTS 工作（flow+vocoder）超过 5000ms
而队列/worker 看似空闲时（`queued=0 active=0` 但 producer 仍在产出），drain 在 5000ms
边界超时 → 谓词恰在边界后为真 → handler 层把 `context_state` 置 3（NOT_REUSABLE）→
后续所有请求被 `❌ F6 lifecycle: context_state=3 rejecting request` 拒绝。

证据（`trackB_rts_drainfix` cpp.log，gen 5）：
```
T2W drain: TIMEOUT after 5000ms — (queued=0 active=0 active_gen=0 tts_done=5
  final_dequeued=0 final_completed=5 my_gen=5)
❌ F6 lifecycle: context_state=3 ... rejecting request  (×15)
```

## 修复尝试（均已回滚，候选二进制已还原）

| 尝试 | 改动 | 结果 | 处置 |
|---|---|---|---|
| TOCTOU 修复 | `t2w_drain_signal_and_wait` 返回 bool，handler 用其返回值而非重查四条件 | 楔死仍在（SPEAK=1），run 完成但 15 拒绝 | 回滚（正确但不完整） |
| 超时修复 | producer 活跃时 +60s 头room | **gen 5 死锁/挂起**（纯 LISTEN gen 谓词永不满足，65s 轮询未触发） | 回滚（回归） |

两次修复均未解决楔死。**根本问题是候选 per-chunk drain 语义**：LISTEN chunk 紧邻
SPEAK turn 时，drain 要等 SPEAK 残留 TTS 完成，5s 默认超时过短；加长超时又因纯
LISTEN gen 的 producer 永不推进 `tts_producer_done_generation` 而挂起。这是
`a77d6a8` F6 lifecycle 引入的候选级限制，非 Config D 注入所致。

## 二进制一致性

两处调查改动（TOCTOU + timeout）已逐字回滚，`libomni.so` 重建后 SHA256 复现冻结
候选：

```
libomni.so  b600ce5277be4eeb   （= 冻结候选，见 f6-seedtts-wer100-root-cause）
```

其余 3 文件补丁（aclnn_ops.cpp / token2wav-impl.cpp / server-omni.cpp）未动。

## 处置

- Track B 状态：**结论性受阻**（RTF NULL + SPEAK 楔死），按 directive 关闭。
- 证据已捕获：SPEAK→WAV 延迟 1306–2747 ms；RTF 基线 1.083（pristine [bench]）。
- 不继续投入 per-chunk drain 修复（两次尝试均失败/回归，属低价值深坑）。
