# KV Cache 优化定位：系统/框架/运行时 vs 算子优化

**日期:** 2026-07-27
**用途:** 与队友沟通优化分工时使用

---

## 1. 当前工作属于哪个层面

当前 59% 收益来源：

```
重复静态前缀
→ 不再重复执行完整 Prefill
→ 直接加载并复用已经计算好的 KV 状态
→ request-to-first-audio 降低约 59%
```

属于：

> **推理系统层 + 框架运行时层 + 缓存机制层优化。**

具体修改范围：

- 请求执行流程控制
- Prefill 是否执行（skip via cache load）
- 跨请求 KV 状态保存与复用
- cache key 设计、multi-entry 文件管理、HIT/MISS 判定
- 损坏检测、fallback、重建
- T2W 生命周期管理
- CPU/NPU 模块放置
- 长稳测试与生产开关

**不是在改变 MiniCPM-o 的模型结构，也不是重新训练模型。**

可以说具有一定算法思想：

```
把重复计算 → 改成状态复用
```

但工程分类更准确的是：

```
系统级推理优化
运行时优化
框架执行路径优化
```

---

## 2. 算子优化是什么

### 2.1 系统层 vs 算子层的分工

| 层 | 问题 | 示例 |
|----|------|------|
| 系统层 | 要不要执行？什么时候执行？在哪个设备执行？能不能复用已有结果？ | KV Cache skip prefill, CPU/NPU placement |
| 算子层 | 既然必须执行，如何在目标硬件上最快完成？ | Tiling, fusion, double buffer, pipe parallel |

系统层决定 **"做不做"**，算子层决定 **"怎么做最快"**。

### 2.2 算子优化的定义

> 对外保持相同的数学语义和输入输出契约，内部通过不同的 tiling、数据搬运、并行划分、融合及指令实现，提高目标硬件上的执行效率。

例如 RMSNorm：

```
输入 tensor
→ 求平方和
→ reduction
→ rsqrt
→ scale
→ 输出 tensor
```

可以由 CANN 内置算子、AscendC 自定义 Kernel、TileLang、Triton Ascend 分别实现。数学结果相同，底层搬运/切块/并行策略不同。

### 2.3 算子是否针对硬件

**是**。算子优化具有强硬件感知性。Ascend 910C 上关注：

- AI Core / Vector Core 使用方式
- GM 到片上存储的数据搬运
- tiling 大小
- double buffer
- 内存对齐
- 流水并行
- kernel launch 次数
- 中间 tensor 是否落回显存
- dtype 与指令支持
- CANN runtime 调度和同步

同一算子，CUDA / CANN / Metal 最优实现不同。

算子仍需框架提供：shape、dtype、layout、stream、workspace、生命周期、调用入口。

---

## 3. 算子和框架代码的隔离度

> **相对独立，但不是完全隔离。**

### 情况一：同语义算子替换（高度独立）

```
ggml-cann RMSNorm → 优化后的 AscendC RMSNorm
```

只要输入输出、shape/dtype/layout、stream 语义、数值精度一致，修改可限制在 CANN backend 内。队友可独立开发，后期合并。

### 情况二：新增融合算子（部分涉及框架）

```
原 GGML 图：RMSNorm → residual add → cast
新 GGML 图：CUSTOM_FUSED_NORM（单 kernel）
```

需要同时修改：
- 模型图构建或 GGML 图
- CANN backend 实现
- `supports_op`
- 图调度或 pattern matching
- fallback

### 情况三：修改 layout 或执行顺序（明显涉及框架）

例如要求输入 layout 变更，或缓存中间结果。会波及上下游算子、tensor allocation、backend scheduler、CPU/NPU 数据传输。

---

## 4. llama.cpp 里的调用关系

```
MiniCPM-o / llama.cpp-omni 模型代码
        │
        │ 构建计算图
        ▼
GGML graph
        │
        │ backend 调度
        ▼
ggml-cann
        │
        │ 调用 CANN 算子或自定义 Kernel
        ▼
Ascend 910C
```

### 两种接入路线

**路线 A：只替换 CANN backend 实现**

```
GGML_OP_RMS_NORM
       ↓
ggml-cann dispatch
       ↓
原 CANN 实现 / 新 AscendC 实现
```

上层模型图不改，最适合并行开发与后期合并。

**路线 B：增加新的融合节点**

```
原 GGML 图：RMSNorm → Mul → Add
新 GGML 图：CUSTOM_FUSED_NORM
```

需同时修改模型图/GGML 图 + CANN backend + fallback，耦合更强。

---

## 5. 宏观 vs 微观

| 维度 | 你的工作 | 算子优化 |
|------|---------|---------|
| 层面 | 宏观：系统/框架/运行时 | 微观：算子/硬件 |
| 核心问题 | 这项计算有没有必要做？能不能复用？能不能提前？放在哪执行？ | 既然必须做，如何充分利用 910C 执行？ |
| 目标 | 减少要做的工作（"少算"） | 让剩下的工作执行更快（"算得更快"） |
| 方法 | Cache 复用、placement、生命周期 | Tiling、融合、搬运、并行 |
| 效果 | 直接跳过 Prefill，E2E -59% | 加速仍必须执行的计算 |

二者不是对立关系，而是上下层配合：

```
系统层：减少计算量
算子层：提高单位计算效率
```

---

## 6. 59% 的准确含义

> 在已测试的静态前缀工作负载中，KV Cache 将 `request-to-first-audio` 降低约 59%。

**不能**解释为：
- ❌ 整个模型永远最多只能优化 59%
- ❌ 任意请求都能得到 59%
- ❌ 这是理论上限

这是当前测试范围内的 E2E 收益。继续在 KV Cache 上做边际优化（cache load 更快、序列化格式、内存映射、减少校验和拷贝、更细粒度复用、cache 与模型初始化重叠等）仍有少量空间，但性价比需要 profile 决定。

下一步转向 decode-to-speak 是合理方向。

---

## 7. 给队友的沟通模板

> 我目前做的是系统和框架运行时层面的优化，主要通过静态前缀 KV Cache 消除重复 Prefill，在现有测试 workload 下，request-to-first-audio 降低了约 59%。现在正在跑 24 小时 mixed workload，验证多前缀、HIT/MISS、损坏恢复和资源稳定性，确保这部分收益能够作为生产候选能力使用。
>
> 算子优化属于下一层，主要针对 Ascend 910C 硬件，对仍然必须执行的计算进行 tiling、搬运、融合和并行优化。两条工作线相对独立但不完全隔离：如果只是替换同语义的 CANN backend 算子，可以独立开发、后期合并；如果涉及算子融合、GGML 图结构或 tensor layout，则需要同时修改 llama.cpp/ggml 的图构建和 backend 接入。
>
> 可以理解为宏观和微观两层：我现在是在宏观层面减少不必要的计算，算子优化是在微观层面加速剩余的必要计算。下一步先对 decode-to-speak 路径做 profiling，再根据热点选择 CANN 内置优化、AscendC、TileLang 或 Triton Ascend，而不是提前指定某一种实现。

### 一句话定性

```
你现在做的是"少算"；
算子优化做的是"算得更快"。
```

两条线可由不同队员相对独立推进，最终在同一个 `llama-omni-cli` binary 中做 E2E 合并验证。

---

## 参考文献

- [llama.cpp CANN Backend](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/CANN.md)
- [llama.cpp How to Add a Model](https://github.com/ggml-org/llama.cpp/blob/master/docs/development/HOWTO-add-model.md)

---

**文件路径:** `docs/experiments/kv-cache-production/KV_CACHE_OPTIMIZATION_POSITIONING.md`
