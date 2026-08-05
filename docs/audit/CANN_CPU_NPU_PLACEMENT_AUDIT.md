# CANN CPU/NPU 放置与同步审计

> **日期**: 2026-08-05（初版）/ 修订 2026-08-05
> **冻结源码**: `bdd4550`（不得修改）
> **审计对象**: `ggml/src/ggml-cann/ggml-cann.cpp`, `ggml/src/ggml-backend.cpp`, `src/llama-context.cpp`, `src/llama-kv-cache.cpp`, `tools/omni/omni.cpp`, `tools/omni/token2wav/token2wav-impl.cpp`
> **硬件**: Ascend 910C 单卡 dual-die, CANN 9.1.0-beta.1
> **模型**: MiniCPM-o 4.5, `-ngl 999`
> **性质**: 只读审计。不修改源码。不运行 Benchmark。不宣称官方结果。
> **辅助文档**: [supports_op 矩阵](CANN_SUPPORTS_OP_MATRIX.md) · [同步与拷贝模式](CANN_SYNC_COPY_PATTERNS.md) · [KV Cache 放置](CANN_KV_CACHE_PLACEMENT.md) · [Per-Chunk RTF 相关性](CANN_PER_CHUNK_RTF_RELEVANCE.md)

---

## 0. 审计状态（四级拆分）

```
CANN_STATIC_CAPABILITY_AUDIT      = PASS    ← 源码审计已完成
MAIN_LLM_STATIC_PLACEMENT         = PASS    ← -ngl 999 模型 weight tensor 在 CANN；scheduler Pass 1.wgt 可追踪
MAIN_LLM_RUNTIME_PLACEMENT        = PARTIAL ← 无直接 profiler 证据（msprof/CANN timeline/backend 分配日志）证明主 Decode 图实际落在 CANN
MAIN_LLM_CPU_FALLBACK_OBSERVED    = NO      ← 冻结日志未观察到 CPU fallback 报错
GRAPH_SPLIT_RUNTIME_COUNT         = NOT_MEASURED ← 待 GGML_SCHED_DEBUG=1 测量
CPU_PER_CHUNK_CRITICAL_PATH       = TO_MEASURE   ← 需逐 chunk 运行时预算完成 Amdahl 判定
```

| 状态 | 含义 | 证据类型 | 完成度 |
|------|------|---------|--------|
| `CANN_STATIC_CAPABILITY_AUDIT=PASS` | 后端 capability / `supports_op` / offload 规则 / KV buffer / copy/sync 调用点 / Tensor 分配规则已查清 | 静态源码 | ✅ |
| `MAIN_LLM_STATIC_PLACEMENT=PASS` | `-ngl 999` 模型 weight tensor 在 CANN buffer；scheduler Pass 1.wgt 路径可静态追踪 | 静态源码 | ✅ |
| `MAIN_LLM_RUNTIME_PLACEMENT=PARTIAL` | 静态放置 PASS 但缺少直接运行时证据（msprof kernel timeline / CANN backend 分配日志 / GGML_SCHED_DEBUG 输出） | 静态源码 + 冻结日志（仅间接，无 profiler） | ⚠️ |
| `MAIN_LLM_CPU_FALLBACK_OBSERVED=NO` | 冻结日志未发现 CPU fallback 报错（不等于运行时证明无 fallback；fallback 可能静默发生） | 冻结日志（grep） | ⚠️ |
| `GRAPH_SPLIT_RUNTIME_COUNT=NOT_MEASURED` | 冻结候选未运行 `GGML_SCHED_DEBUG=1` 记录 backend 分配明细 | — | ❌ |
| `CPU_PER_CHUNK_CRITICAL_PATH=TO_MEASURE` | CPU（采样/队列/音频打包/D2H/序列化/stream sync）在 chunk RTF 中的占比未独立测量 | 待逐 chunk 时间预算 | ❌ |

**当前可以写的结论**: 静态放置路径已审计（PASS）；"未观察到 CPU fallback" ≠ "已证明运行时无 fallback"；主模型 decode 的 CPU fallback 风险较低但不能宣称运行时验证通过。CPU 是否影响最终 per-chunk RTF，仍需逐 chunk 运行时预算完成最终 Amdahl 判定。

**不可以写的结论**: "主模型运行时放置 PASS" / "CPU 工作不在 per-chunk RTF 关键路径" / "同步等待 p50=0ms" — 前两者缺直接 profiler 证据，后者是 mutex_wait（线程锁等待）与 `aclrtSynchronizeStream`（Host 等 NPU stream）误用。

---

## 1. 已确认的结论（可保留）

以下来自源码静态审计，不依赖运行时测量：

```text
-ngl 999 不等于完全没有 CPU 参与
CANN supports_op 覆盖面较完整（~60 种 op）
decode bs=1 的主要权重算子可落在 CANN（weight 在 CANN → scheduler pass 1.wgt 分配到 CANN）
offload_op 的小 batch 路径有 ne[1] >= 32 条件（对 decode bs=1 始终 false，但不影响已分配的权重）
CANN caps.async = false（无通用异步计算流水能力）
主模型 KV 在 offload_kqv=true 时使用 CANN buffer
D2H logits/hidden 读取存在且有语义必要性（async API）
```

关键源码位：

```cpp
// ggml-cann.cpp:2942 — CANN 不支持 async compute
props->caps = { .async = false, .events = true };

// ggml-cann.cpp:3001-3004 — 小 batch 不自动 offload
return op->ne[1] >= dev_ctx->op_offload_min_batch_size  // 默认 32
    && op->op != GGML_OP_GET_ROWS;

// ggml-backend.cpp:918-922 — 但 scheduler pass 1.off 仅在 weight 在 CPU 时尝试 offload
// 若 weight 已在 CANN（-ngl 999），此路径不触发
if (sched->op_offload && src_backend_id == sched->n_backends - 1
    && ggml_backend_buffer_is_host(src->buffer)) { ... }
```

**这两个发现纠正了 CUDA 文章中"batch<32 就大量算子全部回 CPU"的过度泛化**：CAN 后端有设备权重归属的主要模型算子，仍可能由 scheduler 分到 CANN。

---

## 2. 审计层次（6 层框架）

按方法论 §3 的 6 层框架逐层审计。

**重要**: 以下各层的 `结论` 为静态源码结论（`CANN_STATIC_CAPABILITY_AUDIT=PASS`），运行时结论另标测量状态。

### 2.1 权重放置

**结论**: 由 `-ngl 999` 控制的主模型可卸载 **weight tensor** 均在 CANN NPU。

**需要区分**:

| Tensor 类别 | 位置 | 证据 |
|------------|------|------|
| **模型 weight tensor**（Linear/Embedding/Norm/RoPE 权重） | CANN NPU（`-ngl 999` + `is_host=false`） | 源码 |
| **input token/index/control tensor** | 可能 CPU（`GGML_TENSOR_FLAG_INPUT` → 强制 CPU） | 源码 |
| **KV cache K/V tensor** | CANN NPU（`offload_kqv=true`） | 源码 |
| **KV cache 元数据**（cell 状态/seq 映射） | CPU（`ggml_backend_cpu_buffer_type`） | 源码 |
| **output/logits tensor** | CANN NPU（compute output）→ D2H 读取到 Host | 源码 |
| **scheduler metadata** | CPU | 源码 |

**措辞规范**: 不得写"全部 tensor 都在 CANN"或"全部工作都在 CANN"。必须指明 tensor 类别。

### 2.2 算子放置

**静态能力**（`CANN_STATIC_CAPABILITY_AUDIT`）:
- `ggml_backend_cann_supports_op()` 覆盖 ~60 种 op（详见 [supports_op 矩阵](CANN_SUPPORTS_OP_MATRIX.md)）
- 已知 **不支持的 op 条件**（→ CPU fallback）：

| Op | 不支持条件 | 冻结模型是否命中 |
|----|-----------|-----------------|
| `GGML_OP_ROPE` | `ne[0] > 896` | `NOT_MEASURED`（需查 MiniCPM-o head_dim） |
| `GGML_OP_FLASH_ATTN_EXT` | attention sinks (`src[4] != NULL`) | `NOT_MEASURED` |
| `GGML_OP_FLASH_ATTN_EXT` | `logitSoftcap != 0.0f` | `NOT_MEASURED` |
| `GGML_OP_FLASH_ATTN_EXT` | K/V head sizes mismatch | `NOT_MEASURED` |
| `GGML_OP_FLASH_ATTN_EXT` | non-F16 Q/K/V | `NOT_MEASURED`（源码双重检查，第一个要求 F16） |
| `GGML_OP_SOFT_MAX` | attention sinks | `NOT_MEASURED` |
| `GGML_OP_SCALE` | `bias != 0.0f` | `NOT_MEASURED` |

**运行时可达性**（`RUNTIME_REACHED`）: 所有条件均未对冻结模型实测——`NOT_MEASURED`。

**调度器分配逻辑** (ggml-backend.cpp):
1. Pass 1 (weight): weight 在 CANN → op 在 CANN
2. Pass 1 (offload): weight 在 CPU 且有更高优先级 backend `supports_op && offload_op` → offload
3. Pass 2 (dst): 从 dst/view_src 继承 backend
4. Pass 3 (upgrade): 当前 backend 不支持 → 向上搜索
5. Pass 4 (fallback): 剩余分配
6. Pass 5 (split): 切分 graph

**关键差异**: `supports_op` 回答"op 能否在 CANN 执行"（静态），不等于"该 op 在目标 graph 中实际分配到 CANN"（运行时）。后者还需满足：shape/dtype 满足条件、buffer ownership 满足调度条件、未被 INPUT flag 或前后端关系重新分配。

### 2.3 Tensor 放置

**静态规则** (`ggml_backend_sched_backend_from_buffer`):

| Tensor 类型 | 分配规则 | 典型后端 |
|-------------|---------|---------|
| Model weight tensor | 跟随 weight buffer（CANN） | CANN |
| Activation tensor | 跟随 producer op | CANN（跟随 weight op） |
| `GGML_TENSOR_FLAG_INPUT` | 强制 CPU（`sched->n_backends - 1`） | CPU |
| `view_src` tensor | 跟随源 tensor | 跟随源 |
| KV cache K/V tensor | `offload_kqv` 控制 | CANN |
| KV cache metadata | `ggml_backend_cpu_buffer_type` | CPU |

**关键**: `GGML_TENSOR_FLAG_INPUT` 强制 CPU，但对于 `-ngl 999`，embedding 矩阵在 CANN，`GGML_OP_GET_ROWS` 的 weight（src[0]）在 CANN buffer → Pass 1.wgt 覆盖 INPUT flag → GET_ROWS 最终在 CANN。

### 2.4 KV Cache 放置

详见 [KV Cache 放置](CANN_KV_CACHE_PLACEMENT.md)。

**静态结论**（源码确认）:
- 主 LLM KV cache K/V tensor：通过 `offload_kqv=true` → CANN buffer
- TTS KV cache K/V tensor：独立 `llama_context`，同样 `offload_kqv=true` → CANN buffer
- KV cache 元数据（cell 状态/seq 映射）：`ggml_backend_cpu_buffer_type`
- Vision encoder / Audio encoder / Projector / T2W Flow/Vocoder：无 KV cache

### 2.5 同步点

详见 [同步与拷贝模式](CANN_SYNC_COPY_PATTERNS.md)。

**源码调用点**（`STREAM_SYNC_SOURCE_PATH=CONFIRMED`）:

| 调用点 | 触发条件 | 函数 | 源码位置 |
|--------|----------|------|---------|
| `ggml_backend_cann_synchronize` | 每次 backend sync | `aclrtSynchronizeStream` | ggml-cann.cpp:2313 |
| `ggml_backend_sched_compute_splits` | 每个 split 切换 | `ggml_backend_synchronize` → 上者 | ggml-backend.cpp:1565 |
| `ggml_backend_cann_cpy_tensor_async` | 跨 device D2D | `aclrtSynchronizeStream` | ggml-cann.cpp:2292 |
| CANN graph capture | 图捕获前 | `aclrtSynchronizeStream` | ggml-cann.cpp:2371 |
| `ggml_backend_cann_free` | 后端析构 | `aclrtSynchronizeDevice` | ggml-cann.cpp:2147 |

**关键**: CANN `props.caps.async = false` → `pipeline_parallel = false` → 调度器用 `ggml_backend_synchronize()` 替代 event 机制。每次 split 切换 = 一次 `aclrtSynchronizeStream`。

**运行时开销**（`STREAM_SYNC_RUNTIME_COST=TO_MEASURE` for frozen candidate）:

**以下是历史 msprof 数据（旧 commit 2026-07-28，CANN 9.0 时期，不等同于冻结候选 bdd4550），仅用作存在性参考**:

| 指标 | 历史 msprof 值 | 状态 |
|------|--------------|------|
| `aclrtSynchronizeStream` 调用次数 | 46,914 | `HISTORICAL_REF_ONLY` |
| 单次 durtion p50/p95 | 1.1 μs / 19.2 μs | `HISTORICAL_REF_ONLY` |
| 累计耗时 | 268.7 ms（~227s 会话） | `HISTORICAL_REF_ONLY` |
| `aclrtMemcpy` (sync) 调用次数 | 25,226 | `HISTORICAL_REF_ONLY` |
| `aclrtMemcpy` (sync) p50/p95 | 25.1 μs / 42.5 μs | `HISTORICAL_REF_ONLY` |
| `aclrtMemcpy` (sync) 累计 | 971.4 ms | `HISTORICAL_REF_ONLY` |

**冻结候选 (bdd4550) 的 stream sync 运行时数据**: `STREAM_SYNC_RUNTIME_COST=NOT_MEASURED`

**禁止行为**: 用 `mutex_wait p50=0ms`（线程锁/条件变量等待）代替 `aclrtSynchronizeStream` 耗时（Host 等 NPU stream 完成）。这两个指标测的是不同东西：
- `mutex_wait`: 线程等待锁/条件变量/队列竞争
- `aclrtSynchronizeStream`: Host 等待 CANN Stream 完成所有已提交操作

### 2.6 图分裂

**静态分析**: `-ngl 999` + decode bs=1 下：
- 几乎所有 decode op 在 CANN `supports_op` 中
- 无跨-backend weight（全部在 CANN）
- Split 仅在 `supports_op=false` 的 op 出现或图输入节点产生

**运行时测量**: `GRAPH_SPLIT_RUNTIME_COUNT=NOT_MEASURED`

`GGML_SCHED_DEBUG` 环境变量在冻结 binary 中可用（ggml-backend.cpp:1740，运行时 env 读取，非编译期开关），但模型文件不可用，无法做单请求测量。**待模型就位后补测**：
```bash
GGML_SCHED_DEBUG=1 ./llama-omni-server ... 2>&1 | grep "SPLIT\|backend"
```
预期采集：prefill graph / decode bs=1 graph / TTS chunk graph 的 node count、split count、CPU split count、触发 CPU split 的 op、是否在 chunk 路径。

---

## 3. CPU 工作分类：计算 vs 搬运 vs 同步等待

### 3.1 计算（compute）

| 路径 | 位置 | 量级 | 测量状态 |
|------|------|------|---------|
| LLM Decode 所有 layer forward | CANN NPU | N/A | `PLACEMENT_CONFIRMED`（静态 + 冻结日志无 CPU fallback 报错） |
| T2W/Flow/Vocoder forward | CANN NPU | N/A | `PLACEMENT_CONFIRMED`（F6 Phase 2 修正后） |
| Vision/Audio encode | 部分 CPU（n_threads 编码） | ~数百 ms | `NOT_IN_CHUNK_PATH`（prefill 阶段） |
| Tokenizer/Sampler | CPU | ~μs 级 | `NOT_MEASURED`（不在 CANN stream，可与 decode 重叠） |
| 队列管理 / 序列化 / 请求处理 | CPU | 不定 | `NOT_MEASURED` |
| T2W 控制逻辑 | CPU | 不定 | `NOT_MEASURED` |
| 音频拼接 / 后处理 | CPU | 不定 | `NOT_MEASURED` |

### 3.2 搬运（copy）

| 拷贝 | 方向 | API | 测量状态 |
|------|------|-----|---------|
| Weight 加载 | H2D | sync `aclrtMemcpy` | `NOT_IN_CHUNK_PATH`（初始化） |
| Split 间 tensor copy | H2D/D2H | sync `aclrtMemcpy` | `NOT_MEASURED`（split count 未知） |
| D2H logits 读取 | D2H | async `aclrtMemcpyAsync` → caller sync | `D2H_EXISTS=CONFIRMED` |
| D2H hidden states 读取 | D2H | async `aclrtMemcpyAsync` → caller sync | `D2H_EXISTS=CONFIRMED` |
| Dual-die D2D | D2D | async `aclrtMemcpyAsync` + sync | `NOT_MEASURED` |

### 3.3 同步等待（sync wait）

| 同步 | 操作 | 测量状态 |
|------|------|---------|
| Split 间 synchronize | `aclrtSynchronizeStream` | `STREAM_SYNC_RUNTIME_COST=NOT_MEASURED`（冻结候选） |
| CANN graph capture 前 | `aclrtSynchronizeStream` | 仅首次 |
| 后端析构 | `aclrtSynchronizeDevice` | `NOT_IN_CHUNK_PATH` |

**历史参考（不等同于冻结候选）**: `mutex_wait p50=0ms`（来自 F6 R13 octx_mutex 实测，反映线程锁等待，不反映 stream sync）。历史 msprof: `aclrtSynchronizeStream` p50=1.1μs（旧 commit）。

---

## 4. 逐 Chunk 时间预算

> **以下从 G7 稳定性日志（`profiles/g7_stability_30min/`）解析，不代表冻结候选 bdd4550 的正式性能数据。用作内部分解参考。**

| 阶段 | p50 | p95 | 样本量 | Backend | 占 chunk 耗时比例 | 数据来源 |
|------|-----|-----|--------|---------|------------------|---------|
| T2W inference (Flow+Vocoder) | 227.0 ms | 351.1 ms | 797 | CANN NPU | ~100% of measured inference | G7 日志 `T2W线程: ... inference` |
| T2W queue_wait | 0.0 ms | 0.1 ms | 797 | CPU | ~0% | G7 日志 `queue_wait` |
| Talker token generation | `NOT_MEASURED` | — | — | CANN NPU (主 LLM) | — | 未独立计时 |
| D2H (logits) | `NOT_MEASURED` | — | — | — | — | 未独立埋点 |
| D2H (hidden states → T2W) | `NOT_MEASURED` | — | — | — | — | 未独立埋点 |
| Audio packaging | `NOT_MEASURED` | — | — | CPU | — | 未独立埋点 |
| Stream synchronization | `NOT_MEASURED` | — | — | — | — | 未独立埋点 |
| Sampler / Tokenizer | `NOT_MEASURED` | — | — | CPU | — | 未独立埋点 |

**Amdahl 规则**: 占逐 chunk 耗时 <5% 且不是稳定性/串行阻塞点 → `REJECT_BY_AMDAHL`。当前没有足够分解数据来做此判定。

---

## 5. 历史版本对照

| 维度 | 历史基线 (`3f7a7f0` / CANN 9.0) | 冻结候选 (`bdd4550` / CANN 9.1.0-beta.1) |
|------|----------------------------------|------------------------------------------|
| T2W Flow/Vocoder | **CPU**（`ggml_backend_cpu_buffer_type`） | **CANN NPU**（Phase 2 修正） |
| 主 LLM Decode | CANN NPU | CANN NPU |
| KV Cache | CANN（`offload_kqv=true`） | CANN（`offload_kqv=true`） |
| 首包 W0 p50 | ~4,798 ms | **894 ms**（−81.4%） |
| Per-chunk RTF | N/A（无 chunk RTF 测量） | p50=0.23（G7 日志）/ p50=0.28（S13 120 baseline） |
| Stream sync 机制 | `aclrtSynchronizeStream`（同） | `aclrtSynchronizeStream`（同） |

**历史"CPU T2W 瓶颈"与当前"CPU 非关键路径"不矛盾**：差异来自 T2W 从 CPU 搬到 CANN 的源码/配置/设备放置变化。

---

## 6. 与 CUDA 后端的差异

> **不得将 CUDA 文章结论写成 CANN 事实。** 以下仅为对照参考。

| 维度 | CUDA | CANN (910C) | 影响 |
|------|------|-------------|------|
| `caps.async` | `true` | **`false`** | CANN 不支持 async compute → 无 pipeline parallel |
| Graph mode | CUDA Graph | ACL Graph（仅 decode, node≥100） | 类似机制但 API 不同 |
| `offload_op` | batch-size gate | batch-size gate（默认 32） | 行为一致 |
| `supports_op` | 覆盖更全（FA3 等） | 覆盖 ~60 种，特定限制（ROPE ne[0]≤896 等） | 差异小 |
| 同步机制 | event-based | `aclrtSynchronizeStream`（caps.async=false → sync fallback） | CANN 用 stream sync 替代 event wait |
| 内存类型 | Unified memory 可选 | 无 unified memory | CANN buffer 始终 device-only |

**关键纠正**: CUDA 文章所谓"batch<32 大量算子回 CPU"是 CUDA 后端的特定行为。CANN 的 scheduler 在 weight 已在 CANN 时不依赖 `offload_op`（pass 1.off 仅在 weight 在 CPU 时触发），不可直接照搬。

---

## 7. 环境变量生效确认

| 变量 | 源码位置 | 默认值 | 作用 |
|------|---------|--------|------|
| `GGML_OP_OFFLOAD_MIN_BATCH` | ggml-cann.cpp:3140 | `32` | op offload 的最小 batch size |
| `GGML_CANN_WEIGHT_NZ` | ggml-cann.cpp:1338 | `on` | 权重 NZ 格式转换 |
| `GGML_CANN_OPERATOR_FUSION` | ggml-cann.cpp:2377 | `""` (off) | ADD+RMS_NORM / ADD+NORM 融合 |
| `GGML_CANN_PREFILL_USE_GRAPH` | ggml-cann.cpp:2453 | `""` (off) | prefill 也使用 ACL graph |
| `GGML_CANN_GRAPH_MIN_NODES` | ggml-cann.cpp:2478 | `100` | 使用 ACL graph 的最小节点数 |
| `GGML_SCHED_DEBUG` | ggml-backend.cpp:1740 | `0` | 打印 split/backend 分配（**运行时可用**） |
| `GGML_SCHED_DEBUG_REALLOC` | ggml-backend.cpp:1747 | `0`+默认 1 | 检测不必要的 realloc |
| `TTS_GPU_LAYERS` | omni-cli.cpp:418 | `0` | TTS 独立 GPU layers |
| `LLAMA_ARG_KV_OFFLOAD` | server/README.md:68 | `enabled` | 服务端 KV offload 开关 |

---

## 8. 审计方法

- **静态部分**: 源码阅读 `ggml/src/ggml-cann/ggml-cann.cpp`（完整, ~3200 行）, `ggml/src/ggml-backend.cpp`（scheduler 逻辑）, `src/llama-context.cpp`（后端初始化）, `tools/omni/omni.cpp`（多模型 backend）
- **运行时参考**: G7 稳定性日志 797 chunks 的 `T2W线程` 行（来自旧 session，非冻结候选正式 benchmark）；历史 msprof 数据（旧 commit 2026-07-28，CANN 9.0 时期，仅作存在性参考）
- **交叉验证**: env var 名称在源码中 grep 确认存在；函数签名与调用匹配
- **未运行**: 任何 Benchmark（冻结候选）；`GGML_SCHED_DEBUG` 单请求测量（模型文件不可用）

---

## 9. 未覆盖项（审计边界）

- CANN 算子 kernel 内部实现 — 不在本次审计范围
- 冻结候选 (bdd4550) 的 graph split 数量/backend 分配 — `NOT_MEASURED`（需 `GGML_SCHED_DEBUG=1` + 模型文件）
- 冻结候选 (bdd4550) 的 `aclrtSynchronizeStream` 每 chunk 开销 — `NOT_MEASURED`
- 冻结候选 (bdd4550) 的 D2H logits/hidden 每 chunk 累计耗时 — `NOT_MEASURED`
- Multi-die (910C dual-die) 的 peer access 开销 — `NOT_MEASURED`
- MiniCPM-o 4.5 head_dim 是否 > 896（触发 ROPE CPU fallback）— `NOT_MEASURED`
- 冻结模型是否使用 attention sinks / logit softcap / SCALE bias — `NOT_MEASURED`

---

## 10. 最终推荐状态

```
CANN_STATIC_CAPABILITY_AUDIT    = PASS          ← 源码审计已完成
MAIN_LLM_STATIC_PLACEMENT       = PASS          ← -ngl 999 weight tensor 在 CANN，Pass 1.wgt 可追踪
MAIN_LLM_RUNTIME_PLACEMENT      = PARTIAL       ← 无直接 profiler 证据
MAIN_LLM_CPU_FALLBACK_OBSERVED  = NO            ← 冻结日志未观察到（不等于证明无）
GRAPH_SPLIT_RUNTIME_COUNT       = NOT_MEASURED  ← 待 GGML_SCHED_DEBUG=1 测量
STREAM_SYNC_SOURCE_PATH         = CONFIRMED     ← 源码调用点已确认
STREAM_SYNC_RUNTIME_COST        = NOT_MEASURED  ← 冻结候选未测量
D2H_EXISTS                      = CONFIRMED     ← 源码确认
D2H_COST                        = NOT_MEASURED  ← 每 chunk 累计未测量
CPU_PER_CHUNK_CRITICAL_PATH     = TO_MEASURE    ← 需逐 chunk 预算完成 Amdahl 判定
FROZEN_SOURCE_UNCHANGED         = YES           ← bdd4550 未修改
```

**何时可以将 `CPU_PER_CHUNK_CRITICAL_PATH` 改为 `REJECT_BY_AMDAHL`**:
- 逐 chunk 分解时间表补全，且 CPU 项（采样/队列/D2H/音频打包/sync）合计占比 <5% 且非稳定性阻塞点
- 或通过 msprof 冻结候选 session 证明 CPU 侧耗时在各 chunk 间稳定且 <5%

**何时应改为 `CONFIRMED_BOTTLENECK`**:
- 逐 chunk 分解发现任何 CPU 项占比 ≥5% 或造成串行阻塞
