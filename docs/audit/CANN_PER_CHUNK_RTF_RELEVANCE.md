# CANN CPU 工作与 Per-Chunk RTF 相关性判定

> **核心问题**: CPU 上的工作是否在官方 per-chunk RTF 关键路径？是计算、搬运还是同步等待？
> **当前状态**: `CPU_PER_CHUNK_CRITICAL_PATH=TO_MEASURE`
> **判定标准**: 如果 CPU 工作导致 chunk 延迟增加（阻塞 decode/TTS pipeline），则"在关键路径"。

---

## 1. Per-Chunk RTF 定义回顾

```
chunk_rtf = chunk_compute_ms / audio_duration_ms
```

- `chunk_compute_ms`: 从上一个 chunk 结束到当前 chunk 完成的墙上时钟间隔（Talker token generation + T2W queue + Flow + Vocoder + D2H + audio packaging）
- `audio_duration_ms`: 当前 chunk 的语音时长

关键路径 = 任何阻塞 `chunk_compute_ms` 的操作。

---

## 2. 现有运行时数据

### 2.1 G7 稳定性日志（`profiles/g7_stability_30min/`）

> **状态**: `HISTORICAL_REF_ONLY` — 旧 session，不等同于冻结候选 bdd4550 正式 benchmark。用作内部参考。

| 指标 | 值 | 样本量 | 来源字段 |
|------|-----|--------|---------|
| T2W inference (Flow+Vocoder) p50 | 227.0 ms | 797 | `T2W线程: ... inference` |
| T2W inference p95 | 351.1 ms | 797 | 同上 |
| RTF p50 | 0.23 | 797 | `T2W线程: ... RTF=` |
| RTF p95 | 0.42 | 797 | 同上 |
| Queue wait p50 | 0.0 ms | 797 | `T2W线程: ... queue_wait=` |
| Queue wait p95 | 0.1 ms | 797 | 同上 |
| Queue wait max | 201.9 ms | 797 | 同上 |
| Audio duration p50 | 1.00 s | 797 | `T2W线程: ... audio` |

### 2.2 S13 TTS 120 Baseline（冻结候选 bdd4550）

> **状态**: `LLAMA_CONFIRMED` — 冻结日志实测，可引用。

| 指标 | 值 | 样本量 | 来源 |
|------|-----|--------|------|
| Chunk RTF p50 | 0.28 | 120 | `F6 S13 120 Baseline` memory |

### 2.3 F6 Phase 2 T2W A/B（冻结候选 bdd4550）

> **状态**: `LLAMA_CONFIRMED`

| 指标 | Before (CPU T2W) | After (CANN T2W) | Delta |
|------|-----------------:|-----------------:|------:|
| W0 p50 | 4,798 ms | 894 ms | −81.4% |

---

## 3. 逐 Chunk 时间预算（当前状态）

| 阶段 | p50 | p95 | 样本量 | Backend | 占 chunk 耗时 | 测量状态 |
|------|-----|-----|--------|---------|-------------|---------|
| Talker token generation | — | — | — | CANN (主 LLM) | — | `NOT_MEASURED` |
| T2W queue wait | 0.0 ms | 0.1 ms | 797 | CPU | ~0% | `MEASURED`（G7 log，非冻结候选） |
| Flow forward | — | — | — | CANN NPU | — | `NOT_MEASURED`（与 Vocoder 合并为 inference） |
| Vocoder forward | — | — | — | CANN NPU | — | `NOT_MEASURED`（与 Flow 合并为 inference） |
| Flow+Vocoder 合计 | 227.0 ms | 351.1 ms | 797 | CANN NPU | ~100% of measured inference | `MEASURED`（G7 log，非冻结候选） |
| D2H (logits → sampler) | — | — | — | CANN→Host async | — | `NOT_MEASURED` |
| D2H (hidden states → T2W) | — | — | — | CANN→Host async | — | `NOT_MEASURED` |
| Sampler | — | — | — | CPU | — | `NOT_MEASURED` |
| Tokenizer | — | — | — | CPU | — | `NOT_MEASURED` |
| Audio packaging (WAV write) | — | — | — | CPU | — | `NOT_MEASURED` |
| Stream synchronization | — | — | — | CANN stream sync | — | `NOT_MEASURED` |

**Amdahl 规则**: 占逐 chunk 耗时 <5% 且非稳定性/串行阻塞点 → `REJECT_BY_AMDAHL`。**当前没有足够分解数据来做此判定。**

---

## 4. CPU 工作分类与判定

### 4.1 图输入处理（INPUT tensors）

**静态**: `GGML_TENSOR_FLAG_INPUT` → 强制 CPU。但 `-ngl 999` 下 weight 规则（pass 1.wgt）通常覆盖此分配。

**运行时**: `NOT_MEASURED`（需 `GGML_SCHED_DEBUG=1` 确认实际分配）。

### 4.2 调度器 Split 间同步

**静态**: `caps.async=false` → 每次 split 切换 = `aclrtSynchronizeStream`。

**运行时**: 
- Split 数量: `NOT_MEASURED`（需 `GGML_SCHED_DEBUG=1`）
- 每 chunk 同步开销: `NOT_MEASURED`
- `mutex_wait p50=0ms` ≠ stream sync 耗时（详见主报告 §2.5）

### 4.3 Split 间 Tensor Copy

**静态**: CPU↔CANN split → sync `aclrtMemcpy`。

**运行时**: 取决于 split 数量和拷贝大小。`NOT_MEASURED` for frozen candidate。

### 4.4 D2H 读取（Logits / Hidden States）

**静态**（`D2H_EXISTS=CONFIRMED`）:
- `ggml_backend_cann_get_tensor_async` → async `aclrtMemcpyAsync` D2H
- Logits: ~512KB per decode token (128K vocab × 4B fp32)
- Hidden states: ~16KB per hidden layer output (4096 dim × 4B)
- TTS: 额外的 hidden states D2H（给 T2W 输入）

**运行时**（`D2H_COST=NOT_MEASURED`）:
- 单次 p50/p95: `NOT_MEASURED`
- 每 chunk 调用次数: `NOT_MEASURED`（取决于 chunk 内 token 数量）
- 每 chunk 累计耗时: `NOT_MEASURED`
- 占 chunk 耗时比例: `NOT_MEASURED`

**历史 msprof 参考（不等同于冻结候选）**: `aclrtMemcpyAsync` 仅 71 次（全 session），p50=6.4μs，说明 async D2H 在旧 session 中极少使用。冻结候选可能有不同模式（TTS hidden states 读取频率更高）。

### 4.5 Sampler / Tokenizer

在 CPU 执行，不占用 CANN stream。理论上可与下一个 chunk 的 decode 重叠。但实际重叠程度取决于流水线实现 — `NOT_MEASURED`。

### 4.6 队列管理 / 请求处理 / 音频打包

在 CPU 执行。G7 日志显示 queue_wait p50=0ms，说明 T2W 线程几乎不等待 Talker token——流水线调度良好。音频打包在 inference 完成后执行，不在 CANN stream 内。

### 4.7 Vision/Audio 编码

在 prefill 阶段，不在 decode chunk 内。`NOT_IN_CHUNK_PATH`。

---

## 5. 判定矩阵

| CPU 工作 | 在关键路径? | 类型 | 测量状态 | Amdahl 判定 |
|----------|-----------|------|---------|-----------|
| 图输入 (如有) | `NOT_MEASURED` | 同步+拷贝 | 需 `GGML_SCHED_DEBUG=1` | — |
| Split 间同步 | `NOT_MEASURED` | 同步等待 | `STREAM_SYNC_RUNTIME_COST=NOT_MEASURED` | — |
| Split 间拷贝 | `NOT_MEASURED` | 搬运 | 需 split 测量 + msprof | — |
| D2H logits | 是（语义必须） | 搬运 | `D2H_COST=NOT_MEASURED` | — |
| D2H hidden states | 是（语义必须） | 搬运 | `D2H_COST=NOT_MEASURED` | — |
| Sampler/Tokenizer | 否（与 CANN 并行） | 计算 | `NOT_MEASURED` | — |
| 队列/请求/Audio 打包 | 否（非 chunk 内） | 计算 | `NOT_MEASURED` | — |
| Vision/Audio 编码 | ❌ 否（prefill 阶段） | 计算 | `NOT_IN_CHUNK_PATH` | — |

---

## 6. F6 已知数据与当前结论的一致性

### 6.1 RTF 值本身不证明"CPU 不在关键路径"

- S13 RTF p50=0.28: chunk 计算时间 = 音频时长的 28%。70%+ 是空闲（等下一个音频 chunk 开始）。
- 但 RTF 是 **整体指标**，不分解为 CPU/NPU 分量。
- RTF=0.28 说明 NPU compute 足够快，但**不能排除 CPU 工作占用了其中一部分**（例如 D2H 占总 inference 的 5% 还是 30%？）。

### 6.2 W0 数据说明 T2W 修正有效

- Before (CPU T2W): W0 p50=4,798ms → CPU T2W 曾经是瓶颈
- After (CANN T2W): W0 p50=894ms → 修正有效
- 但 W0 是首包延迟，不是逐 chunk RTF。不能从 W0 推断 chunk 内 CPU 占比。

### 6.3 queue_wait=0ms 说明流水线尚可

- G7 日志 797 chunks queue_wait p50=0ms → T2W 线程不等待 Talker token
- 如果 CPU 工作阻塞了 Talker token 产出，queue_wait 会 >0
- 但这不排除 D2H 本身在 inference 内部占用了时间

---

## 7. 如何补全 `CPU_PER_CHUNK_CRITICAL_PATH` 判定

需要采集以下数据（全部标记为待补）：

1. **Graph split 确认**: `GGML_SCHED_DEBUG=1` 跑一个短请求 → 确认 decode graph 是否有 CPU split
2. **逐 chunk 时间分解**: 在冻结 binary 中加临时埋点或从 msprof 冻结候选 session 提取：
   - Talker token generation (per token)
   - D2H hidden states (per chunk)
   - Flow forward
   - Vocoder forward
   - Sampler/Tokenizer
   - Audio packaging
3. **Stream sync 开销**: msprof 冻结候选 session → 提取 `aclrtSynchronizeStream` 的 per-chunk 累计
4. **Amdahl 判定**: 若所有 CPU 项合计 <5% 且非串行阻塞 → `REJECT_BY_AMDAHL`；否则 → `CONFIRMED_BOTTLENECK`

**当前阻塞**: 模型文件不可用，无法启动冻结 binary。

---

## 8. 结论

```
CPU_PER_CHUNK_CRITICAL_PATH = TO_MEASURE
```

**可以说的**:
- 主模型 decode 图中没有已知会导致 CPU fallback 的 op（基于静态 `supports_op` 审计）
- G7 日志中 queue_wait p50=0ms 说明 T2W 流水线调度良好
- F6 Phase 2 已将 Flow/Vocoder 从 CPU 搬到 CANN，消除了最大的已知 CPU 瓶颈
- RTF=0.23-0.28 说明 NPU 推理足够快（留有余量）

**不可以说的**:
- "CPU 工作不在 per-chunk RTF 关键路径" — 缺少逐 chunk 分解数据
- "D2H 约 100μs，可以忽略" — 单次开销或许小，但每 chunk 累计未知
- "同步等待 p50=0ms" — mutex_wait 不等于 stream sync

**下一步**: 待模型文件就位后，执行 §7 中的最小测量（`GGML_SCHED_DEBUG=1` 单请求 + msprof 冻结候选 session），完成 Amdahl 判定。
