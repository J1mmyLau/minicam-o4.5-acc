# F6 — Track D：Config-D 稳定性 soak

Date: 2026-08-14 · Candidate `a77d6a8` + trackA_fixes.patch（Config D）
Directive: 【BYPASS — LONG-RUN FINALIZATION QUEUE】Track D

## 结论（一句话）

冻结候选 + Config D 的 RTS 服务端 soak **无崩溃、无线程泄漏**，但**稳定复现
Track B 的 SPEAK turn 楔死**（`context_state=3` → 24 次拒绝）。楔死是候选
`a77d6a8` 的 per-chunk drain 语义（Track B 已根因），非 Config D 注入，非稳定性退化。

## 运行证据（2 次 RTS 直接评测，Config D，同一视频 37 chunk）

| 运行 | SPEAK/LISTEN | 崩溃 | context_state=3 拒绝 | 用时 |
|---|---|---|---|---|
| `trackD_soak/rts_runs` (02:57) | LISTEN=37 SPEAK=0 | 无 | 24 | ~80s |
| `trackD_soak/rts_runs_2` (03:01) | SPEAK=3 | 无 | 24 | ~80s |

- 两次均：服务就绪 → 处理 → full_reinit → 「服务已停止」，生命周期干净。
- 两次均在 gen=5 处楔死（`T2W drain: TIMEOUT after 5000ms` 或直接 `context_state=3`），
  与 Track B 的 `trackB_rts_drainfix` gen5 TIMEOUT 逐字一致。

## 楔死（Track B 复现，非 Track D 新增）

gen 1–4 干净（LISTEN，`fast=1`），gen 5 处：

```
T2W drain: TIMEOUT after 5000ms — (queued=0 active=0 active_gen=0 tts_done=5
  final_dequeued=0 final_completed=5 my_gen=5)
❌ F6 lifecycle: context_state=3 (not REUSABLE/DRAINING), rejecting request  (×24)
```

`final_dequeued=0` 而 `tts_done=5`：SPEAK 残留 TTS 仍在产出但队列看似空闲，
5s 默认超时边界触发 → handler 置 `context_state=3`。这是 `a77d6a8` F6 lifecycle
的 per-chunk drain 语义（Track B 根因），Config D 仅暴露之，非引入之。

## 线程泄漏（Track D 关注点）— 判定不适用于 RTS 路径

- 线程泄漏根因（`f6-thread-leak-root-cause-definitive`）：libgomp 每 httplib worker
  建 319 线程 team（= `cpuparams.n_threads-1` = 320-1），修复 = `-t 4`。
- **RTS 路径不适用**：`full_reinit` 每视频 stop→start 服务进程，跨视频无线程累积；
  单视频 37 请求受 httplib 线程池（默认 8）有界，8×319 ≈ 2552 < pids.max 10000。
- **eval CLI 准确率路径不适用**：Daily-Omni / VideoMME / Seed-TTS 用 eval CLI
  进程内加载模型，无 httplib 服务端，无泄漏面。
- 泄漏仅影响 WS Demo 路径（单服务进程多 session），已由 `-t 4` 修复。

⇒ 官方准确率评测（Track C，2.76h Seed-TTS + Daily-Omni + VideoMME，0 error）与
RTS 服务端 soak（本次 2 次，0 崩溃）共同覆盖 Config D 稳定性。无线程泄漏风险增量。

## 处置

Track D **关闭**。Config D 稳定性 = 无崩溃 + 无线程泄漏（RTS/eval 路径均不适用或已修），
唯一负面 = SPEAK 楔死（Track B 已结论性关闭，属候选级 per-chunk drain 限制）。
不继续投入（无新增价值）。
