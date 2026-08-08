# fix/tts-thread-lifecycle — WS Session Lifecycle & Thread Fix

> 服务生命周期修复分支。解决了连续请求下的线程泄漏、drain timeout、context 失效
> 和 WebSocket session 状态机问题。P0-C final cleanup 也在此分支完成。

## 分支目的

将一次性运行的服务改造成可持续处理多轮请求的 Persistent Server，
修复所有已知的服务稳定性问题。

## 解决的问题

### 线程泄漏（ROOT CAUSE CONFIRMED）

- **现象**：线程数 monotonic 增长（1598→1917→3524→4480），5-6 session 后 crash
- **根因**：libgomp 为每个 httplib worker 创建 319-thread OpenMP team
  （319 = cpuparams.n_threads-1 = 320-1）
- **修复**：`-t 4` 将 pool 降至 3 线程/session
- **证据**：strace cascade confirmed

### WS Session 生命周期

- **根因**：`CTX_STATE_REUSABLE` 未在 session 结束时正确重置（ws_handler.cpp）
- **修复**：统一 finalizer + abort recovery = session accepted
- **验证**：3 个连续 E2E session 全部通过，turn_based mode 正确

### Drain Timeout

- **现象**：全双工解码不终止，decoder 持续运行数分钟
- **根因**：`stream_decode` with `n_predict=-1` 在最后 chunk 后无限生成
- **修复**：drain CV notify 替代纯 polling；`DRAIN_TIMEOUT` 是线程争用的症状而非数据丢失
- **确认**：所有 `final_dequeued == final_completed`，无数据丢失

### Per-Generation Active

- `active_t2w_generation` 改为 per-generation 粒度
- Drain predicate: `(active_gen==0 || active_gen>N)`
- 3/3 sequential PASS

### Fault Injection

5 种故障注入模式全部恢复：
- 突然断连
- 快速 session 循环
- 无效输入
- 异常消息序列
- 并发 session 冲突

### P0-C Final Cleanup

- 所有 "37 is official" claims 从代码/docstrings/tasks 中移除
- 推送到 private repo（f996239）

## 关键验证

| 测试 | 结果 |
|------|------|
| 10 连续 sessions (turn_based) | 10/10 PASS |
| KV cache cleared between sessions | CONFIRMED |
| n_past reset between sessions | CONFIRMED |
| Fault injection recovery | 5/5 PASS |
| Thread stability (17min single session) | 234 T2W calls, 0 errors |

## 与前后分支的关系

```
eval/official-baseline              ← 基线
ecee7de (CANN RoPE fix)            ← GPU TTS 可用
fix/tts-thread-lifecycle            ← 本分支：稳定性修复    [← YOU ARE HERE]
perf/f6-decode-to-speak            ← 性能优化
release/final-integration          ← 最终集成
```

## 详细推进记录

完整的时间线和每阶段累积进展见 [主分支 README（推进全记录）](../../main/README.md)。

---

> 分支标签：`STABILITY_FIX` | 状态：`MERGED_INTO_LATER`
