# MiniCPM-o 4.5 × Ascend 910C 优化全过程

> 从 Profiling 到实验归档，三个阶段、八次认知修正。

---

## 背景

- **仓库**: llama.cpp-omni, feat/ascend-cann 分支
- **基线**: commit 3f7a7f0
- **硬件**: 2× Ascend 910C (64 GB HBM), Kunpeng 920 (640 核)
- **CANN**: 9.0.0, Driver 25.5.1
- **模型**: MiniCPM-o 4.5 F16 GGUF
- **测试**: Full Omni (Vision + Audio + LLM + TTS + Token2Wav), 2 轮对话

---

## 阶段一：Profiling → 候选排序 (TASK-006, TASK-007)

### 拿到了什么

msprof CLI 对 Full Omni 做了一次完整采集。CANN-level 分析产出:

| 指标 | 值 |
|------|-----|
| MatMulV2 NPU 占比 | 68% (dev0) / 75% (dev1) |
| Cast 占比 | ~7% |
| aclrtMemcpy (sync) | 2325 ms / 2479 次 |
| aclrtMalloc/Free | 1170 ms |
| aclrtSynchronizeStream | 173 ms / 4535 次 |

### 初判

MatMulV2 占 NPU 时间 ~70%，直觉上是最大热点。应该先优化 MatMul。

### 修正

做候选排序时，把 E2E 拆开看:

```
Full Omni E2E ~130s
  CPU TTS + Token2Wav  ~110s (85%)
  Host API overhead     ~10s ( 8%)
  NPU device compute     ~2.6s ( 2%)
```

**NPU 设备时间只占总 E2E 的 2%。**

即使 MatMul 优化 50%，对 E2E 的影响也只有 ~1%（~1.3s）。而 CPU TTS 占 85%，这里省 10% 就是 11s。

### 决策 (D-001~D-004, TASK-007)

- MatMul、AscendC 排到 P4/P5
- 优先做低风险系统开销: sync memcpy, buffer pool, Cast
- 建立 5 层分层模型 (L1 零代码 → L5 算子级)
- 8 个候选按公式评分: `Gain × Confidence × Reproducibility ÷ (Risk × Cost)`

| # | 候选 | 得分 | 层 |
|---|------|------|-----|
| 1 | CAND-002 Sync memcpy → Async | 8.89 | L2 |
| 2 | CAND-003 Memory allocation pooling | 6.67 | L2 |
| 3 | CAND-004 Cast/Transpose/Contiguous | 2.25 | L2 |
| 8 | CAND-008 MatMul shape/layout | 0.27 | L5 |

---

## 阶段二：低风险优化 → "正确但不可测" (EXP-001, EXP-002)

### EXP-001-V1: D2D async stream

**改了**: ggml-cann.cpp 的 `ggml_backend_cann_buffer_cpy_tensor`，sync `aclrtMemcpy` D2D → async `aclrtMemcpyAsync` + 专用 D2D stream。

**结果**:
- Build: PASS
- Smoke: PASS (exit 0, 无 crash)
- A/B: **无法测量** — Full Omni E2E 在 36-136s 间波动

### EXP-002-V1: Buffer free-list cache

**改了**: ggml-cann.cpp 的 buffer allocator，增加 per-device free-list。`aclrtFree` 时不真释放，放入 size-indexed 缓存池（上限 256 MiB），下次 `aclrtMalloc` 优先命中缓存。

**结果**:
- Build: PASS
- Smoke: PASS (exit 0)
- A/B: **无法测量** — 同上，E2E 波动淹没信号

### 认知突破

**Full Omni E2E 的波动来自 TTS 输出长度不确定。** 同一个测试用例，LLM 每次生成的文本长度不同 → TTS 生成的音频 token 数不同 → T2W 处理的 window 数不同。差异可达 3-4 倍（36s vs 136s）。

在这个量级的方差下，设备侧节省的毫秒级收益完全不可见。

### 决策

- EXP-001、EXP-002 标记 ARCHIVED: correctness PASS, performance UNMEASURABLE
- **不标记为 FAILED** — 它们在各自的微 benchmark 上是正确的
- 暂停所有 NPU 设备侧微优化
- **主线切换到 CPU TTS/Token2Wav pipeline**

---

## 阶段三：CPU TTS Token2Wav Pipeline (EXP-005)

### EXP-005A: 定位

**发现 1**: Encoder+flow 的 GGML compute graph **已被上游缓存**。
`sess_->gf_nonlast` / `sess_->gf_last` 在 `setup_cache` 时预构建，`inference_chunk` 只 upload 输入 + compute + download 输出。EXP-005-V1 (graph cache) 是 REDUNDANT。

**发现 2**: Vocoder 的 graph 每窗口重建。
`voc_hg2_runner_eval_stream` 每次创建新 `ggml_context` + 新 `ggml_cgraph`。但 mel 维度 `T_mel` 随窗口累积增长（前窗口 mel + 当前 mel），形状不固定，无法简单缓存。

**发现 3**: Per-window 耗时结构:
```
Token2Mel (encoder + flow matching, 5 timesteps)  ~3.5s
HiFiGAN vocoder                                     ~0.5s
WAV write                                           <0.01s
Total per window                                     ~4.0s
RTF ~3.95 (处理 1s 音频需要 ~4s)
```

### EXP-005-V3: Async vocoder pipeline

**思路**: Encoder+flow (~3.5s) 和 vocoder (~0.5s) 使用不同的 ggml backend → 可以并行。Window N 的 vocoder 在后台线程运行，同时主线程处理 window N+1 的 encoder+flow。

**实现**: `std::async` + `std::future<void>` + 成员变量顺序修正（析构顺序 Bug）。

**结果**: **REJECTED_CORRECTNESS_AND_PERFORMANCE**

| 指标 | Sync | Async | 差异 |
|------|------|-------|------|
| 音频样本数 | 451,200 | 427,200 | **-5.3%** |
| 归一化延迟 (ms/s audio) | 255.7 | 259.3 | **+1.4%** |

**根因**:
1. async_wave_out_ 取回偏移导致音频丢失
2. 线程创建开销 ~200ms / 19 windows
3. **根本限制**: encoder+flow 和 vocoder 在同一设备上无法真正并行

### D-006: Backend 确认 — ALL CPU

查源码 `omni.cpp:4396-4419`:
```cpp
#ifdef GGML_USE_CANN
    device_token2mel = "cpu";  // CANN 下硬编码 CPU
    device_vocoder   = "cpu";
#endif
```

**Encoder、Flow、Vocoder 全部在 CPU 上运行。** 之前的 "同一 NPU device 串行" 假设本身就不成立——它们根本不在 NPU 上。Pipeline overlap 方向从根本上缺乏硬件基础。

### EXP-005-V3-B: Persistent worker

**思路**: 用持久线程替代 `std::async`，消除每次创建线程的开销。即使不能并行计算，至少避免线程创建/销毁的固定成本。

**结果**: **ARCHIVED — 性能中性 (+0.3%)**

- Correctness PASS
- Sync 基线 vocoder 本身是 inline 模式，没有线程创建开销需要消除
- Mutex + condition_variable 同步开销 ~17-35ms/window，抵消了潜在收益

### EXP-005-V5: CPU threads sweep

**思路**: 640 核 Kunpeng 920，T2W 默认 8 线程远未充分利用。扫描 1/2/4/8/16/32 线程。

**结果**: **ACCEPTED — 16 threads 最优**

| 线程 | Token2Wav total | vs 8 threads |
|------|----------------|-------------|
| 8 (default) | 16744.5 ms | baseline |
| 16 | 16542.6 ms | **-1.2%** |
| 32 | 16618.3 ms | -0.8% (收益递减) |

- 所有线程数输出相同音频（correctness confirmed）
- D-008: 默认改为 16，`OMNI_T2W_N_THREADS` env var 可覆盖

---

## 当前状态总览

### 实验归档

| ID | 描述 | 结果 |
|----|------|------|
| EXP-001 | D2D async stream | CORRECTNESS PASS, E2E 不可测 |
| EXP-002 | Buffer free-list cache | CORRECTNESS PASS, E2E 不可测 |
| EXP-005-V1 | Graph cache | REDUNDANT (已缓存) |
| EXP-005-V3 | Async vocoder pipeline | **REJECTED** (音频 Bug + 负性能) |
| EXP-005-V3-B | Persistent worker | ARCHIVED (性能中性) |
| EXP-005-V5 | CPU threads 8→16 | **ACCEPTED** (+1.2%) |

### 方向判断

| 方向 | 结论 |
|------|------|
| NPU 微优化 (D2D, buffer, MatMul) | 暂停 — E2E 被 TTS 波动淹没 |
| Pipeline overlap (V3, V3-B) | 归档 — CPU 串行, 无设备可并行 |
| Async WAV I/O (V4) | 不实施 — 占比 <0.03% |
| CPU threads | **唯一有效方向** — +1.2% |
| AscendC | NOT SATISFIED — 5 条件均未满足 |

### AscendC Gate

| 条件 | 状态 |
|------|------|
| 1. 精确算子实例或 shape 明确 | ❌ |
| 2. 单独占目标 Stage ≥10% 或 E2E ≥5% | ❌ |
| 3. layout/Cast/同步/allocation/Graph 已排除 | ❌ |
| 4. ACLNN 路径确认低效 | ❌ |
| 5. 输入输出契约可冻结 | ❌ |
| 6. 可写 CPU reference | ❌ |

---

## 核心教训

1. **"占比高" ≠ "可优化出收益"。** MatMul 占 NPU 70%，但 NPU 只占 E2E 2%。瓶颈域判断比热点排序更重要。

2. **E2E 波动会淹没毫秒级优化。** 在 Full Omni 的 36-136s 方差下，<1s 的收益无法可靠测量。必须先建立专项 benchmark 排除噪声源。

3. **假设驱动，但要验证假设。** "encoder+flow 和 vocoder 在不同设备上可以并行" 这个假设被 D-006 一次源码阅读就证伪了。早查源码能节省 EXP-005-V3 和 V3-B 两个实验。

4. **流水线重叠需要硬件基础。** 当两个 stage 在同一设备上串行执行时，多线程只是增加同步开销，不会带来计算并行性。

5. **CPU 线程是当前唯一有效的优化方向。** 640 核 Kunpeng 920 + CPU-only T2W → 线程数 tuning 是唯一有正收益的改动。

---

## 证据索引

```
harness/profiling/20260716-131033-full-omni-msprof/    CANN profiling 原始数据 + 分析
harness/experiments/OPTIMIZATION_PRIORITY.md            候选排序
harness/experiments/TASK-007_CONCLUSION.md              排序结论
harness/experiments/EXP-005-token2wav-pipeline/         T2W pipeline 全部实验
harness/experiments/EXP-005-token2wav-pipeline/benchmarks/  V3 专项 benchmark
harness/autonomous/20260716-134420-autonomous-optimization/ 第一阶段 session
harness/autonomous/20260717-032106-cc-autopilot/            ITER-001 (V3 benchmark)
harness/autonomous/20260717-041023-cc-autopilot/            当前无限续跑 session
DECISIONS.md                                            全部技术决策 (D-001 ~ D-008)
FAILURES.md                                             失败记录
```
