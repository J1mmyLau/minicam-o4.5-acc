# CANN 同步与拷贝模式审计

> **源码**: `ggml/src/ggml-cann/ggml-cann.cpp`（CANN 后端）, `ggml/src/ggml-backend.cpp`（调度器 split 计算）
> **冻结 commit**: `bdd4550`

---

## 状态

```
STREAM_SYNC_SOURCE_PATH   = CONFIRMED     ← 源码调用点已全部确认
STREAM_SYNC_RUNTIME_COST  = NOT_MEASURED  ← 冻结候选未测量
MUTEX_WAIT_P50            = 0 ms          ← F6 R13 octx_mutex 实测（线程锁等待，不等同于 stream sync）
COPY_SOURCE_PATH          = CONFIRMED     ← 源码调用点已全部确认
COPY_RUNTIME_COST         = NOT_MEASURED  ← 冻结候选每 chunk 累计未测量
```

**关键纠正**（2026-08-05 修订）:
- `mutex_wait p50=0ms` 测的是**线程等待锁/条件变量/队列竞争**，不能用作 `aclrtSynchronizeStream` 耗时证据
- `aclrtSynchronizeStream` 测的是 **Host 等待 CANN Stream 完成所有已提交操作**
- 这两个指标测的是完全不同的东西

---

## 1. 关键前提: `props.caps.async = false`

```cpp
// ggml-cann.cpp:2941-2945
props->caps = {
    /* .async  = */ false,   // CANN 不支持通用异步计算流水
    /* .events = */ true,    // 支持 event record/wait/synchronize
};
```

**后果链**:
```
caps.async = false
  → pipeline_parallel = false (src/llama-context.cpp:355)
    → 调度器用 ggml_backend_synchronize() 替代 event-based sync
      → 每次 split 切换 = 一次完整的 aclrtSynchronizeStream
```

---

## 2. Memory Copy 分类

### 2.1 初始化路径（不在 per-chunk RTF 内）

| 函数 | 操作 | API | 数据量 |
|------|------|-----|--------|
| `ggml_backend_cann_buffer_set_tensor` | 权重加载 H2D | sync `aclrtMemcpy` | ~16 GB（全模型） |
| `ggml_backend_cann_buffer_set_tensor` (quantized) | 量化权重 transform + H2D | sync `aclrtMemcpy` | 同 |
| `ggml_backend_cann_buffer_set_tensor` (chunked) | NZ 权重分块 H2D | sync `aclrtMemcpy` per chunk | 同 |
| `ggml_backend_cann_buffer_get_tensor` | 权重读取 D2H | sync `aclrtMemcpy` | 极少（debug 路径） |

全部使用 **同步** API。在初始化阶段合理——权重加载是串行操作。

### 2.2 运行时路径（可能在 per-chunk RTF 内）

| 函数 | 操作 | API | 测量状态 |
|------|------|-----|---------|
| `ggml_backend_cann_set_tensor_async` | H2D | async `aclrtMemcpyAsync` | `NOT_MEASURED` |
| `ggml_backend_cann_get_tensor_async` | D2H (logits/hidden) | async `aclrtMemcpyAsync` | `D2H_EXISTS=CONFIRMED` `D2H_COST=NOT_MEASURED` |
| `ggml_backend_cann_cpy_tensor_async` (同 device) | D2D | async `aclrtMemcpyAsync` | `NOT_MEASURED` |
| `ggml_backend_cann_cpy_tensor_async` (跨 device) | D2D + sync | async `aclrtMemcpyAsync` + `aclrtSynchronizeStream` | `NOT_MEASURED` |
| `ggml_backend_cann_buffer_cpy_tensor` (同 device) | D2D | sync `aclrtMemcpy` | `NOT_MEASURED` |

**D2H 语义必要性**:
- `get_tensor_async`: Logits 读取（每个 decode token 1 次）和 hidden states 读取（每个 TTS chunk N 次）
- 使用 async API → 不阻塞 CANN stream
- 但 caller 必须在消费数据前同步 → 隐式同步点
- 单次大小: logits ~512KB (128K vocab × 4B), hidden states ~16KB (4096 dim × 4B)
- 单次开销: `NOT_MEASURED`（历史 msprof 参考: `aclrtMemcpyAsync` p50=6.4μs，71 次总共 0.7ms，旧 commit 不可套用）

---

## 3. 同步点全景

### 3.1 Stream Synchronize

| 调用点 | 源码位置 | 触发条件 | 频率 |
|--------|---------|----------|------|
| `ggml_backend_cann_synchronize` | ggml-cann.cpp:2313 | Scheduler 请求 sync（每次 split 切换） | 取决于 split 数量 |
| `ggml_backend_cann_cpy_tensor_async` | ggml-cann.cpp:2292 | 跨 device D2D 拷贝后 | 仅 dual-die |
| CANN graph capture begin | ggml-cann.cpp:2371 | 图捕获前 | 仅首次每种 shape |

**Scheduler 驱动的 sync 路径** (`ggml_backend_sched_compute_splits`, ggml-backend.cpp:1541-1720):

```
for each split:
  for each input to copy:
    if caps.async == false:  // CANN
      ggml_backend_synchronize(dst)  → aclrtSynchronizeStream
      // 或
      ggml_backend_synchronize(src) → aclrtSynchronizeStream
      ggml_backend_tensor_copy(input, input_cpy)  // sync memcpy
    
  ggml_backend_graph_compute_async(split_backend, &split->graph)
```

### 3.2 Device Synchronize

| 调用点 | 源码位置 | 触发条件 | 是否在 RTF 路径 |
|--------|---------|----------|----------------|
| `ggml_backend_cann_free` | ggml-cann.cpp:2147 | 后端析构 | ❌（server 退出/sleeping） |

### 3.3 Event Synchronize

```cpp
// ggml-cann.cpp:3054
ACL_CHECK(aclrtSynchronizeEvent((aclrtEvent) event->context));
```

CANN 支持 event（`caps.events=true`），但 `caps.async=false` 意味着 scheduler 层面不使用 pipeline_parallel 的 event 机制。

---

## 4. 历史 msprof 数据（仅作存在性参考）

> **来源**: `profiles/decode-speak/PROF_000001_20260728064555800_02891647BFGBMJEL/mindstudio_profiler_output/msprof_20260728064956.json`
> **日期**: 2026-07-28
> **Session 时长**: ~227s
> **状态**: `HISTORICAL_REF_ONLY` — 旧 commit（CANN 9.0 时期），不等同于冻结候选 `bdd4550`（CANN 9.1.0-beta.1, 2026-08-04）

| 事件 | 次数 | p50 | p95 | 累计 |
|------|------|-----|-----|------|
| `aclrtSynchronizeStream` | 46,914 | 1.1 μs | 19.2 μs | 268.7 ms |
| `aclrtSynchronizeDevice` | 7 | 13.6 μs | 67.3 μs | 0.2 ms |
| `aclrtMemcpyAsync` | 71 | 6.4 μs | 24.6 μs | 0.7 ms |
| `aclrtMemcpy` (sync) | 25,226 | 25.1 μs | 42.5 μs | 971.4 ms |

**TID 分布**:
- `aclrtSynchronizeStream`: TID 2891647 (43,840 calls) + TID 2891918 (3,074 calls) — 两个线程
- 主线程 43,840 次 → 平均 ~193 calls/s → 可能包含 prefill 阶段的大量 sync

**注意**:
- 这是旧 CANN 版本、旧设备布局的数据。用户报告过旧 commit 有 `aclrtSynchronizeStream 4535 次 累计 173ms + sync memcpy 2325ms`——与此 session 数字不同，说明不同 workload/配置差异极大。
- 冻结候选 (bdd4550) 的 stream sync 和 memcpy 数据可能显著不同（T2W 从 CPU 搬到 CANN 后 sync memcpy 大幅减少）。
- **不可将此表数字直接套到冻结候选**。

---

## 5. `mutex_wait` vs `aclrtSynchronizeStream` 区分

| 指标 | 测量对象 | 来源 | 实测值 |
|------|---------|------|--------|
| `mutex_wait` | 线程等待锁/条件变量/队列竞争 | F6 R13 octx_mutex（F6 memory） | **p50=0ms** |
| `aclrtSynchronizeStream` duration | Host 等待 CANN Stream 完成已提交操作 | msprof（历史，不等同于冻结候选） | **p50=1.1μs** |

**禁止用 `mutex_wait` 代替 `aclrtSynchronizeStream` 耗时**。这两个指标反映不同层面的等待。

---

## 6. 同步开销与 Chunk RTF 关系

**当前可说的**:
- 同步调用点已从源码全部确认（`STREAM_SYNC_SOURCE_PATH=CONFIRMED`）
- 同步次数取决于 graph split 数量，split 数量取决于运行时 op 分配
- 如果 split=0（纯 CANN graph），decode chunk 内部无 `aclrtSynchronizeStream`
- 如果 split>0（存在 CPU fallback op），每个 split 边界触发一次 sync

**当前不可说的**:
- 冻结候选的每 chunk 同步次数 — `NOT_MEASURED`
- 冻结候选的每 chunk 同步耗时 — `NOT_MEASURED`
- "同步等待 p50=0ms" — 来源于 mutex_wait，非 stream sync

---

## 7. 与 F6 已知数据的吻合度

- **F6 Phase 2 T2W 修正**: T2W 之前走 CPU sync 路径（`ggml_backend_cpu_buffer_type` → sync memcpy H2D/D2H 大量调用），修正后搬至 CANN → 首包 −81%。这证明 CPU sync 路径是真实瓶颈，且已被修正。
- **G7 稳定性日志**: 797 chunks, inference p50=227ms, RTF p50=0.23, queue_wait p50=0ms。inference 时间包含 CANN compute + 隐式 D2H（hidden states 读取）。queue_wait 0ms 说明 T2W 线程几乎不等待 Talker token 到达——流水线效率高。
- **S13 baseline**: 120/120 valid, RTF p50=0.28。详见 `F6 S13 120 Baseline` memory。
