# F6 方法论与工程纪律

> 本文提炼 F6 decode-to-speak 优化项目中使用的方法论、统计纪律和工程原则。
> 不是操作手册（见 [F6_QUICKSTART.md](F6_QUICKSTART.md)），而是"为什么这样做"。
> **候选源码**: `bdd4550` | **状态**: `FINAL_INTERNAL`

---

## 目录

1. [Profiling 驱动的瓶颈定位](#1-profiling-驱动的瓶颈定位)
2. [Amdahl 排序与优化取舍](#2-amdahl-排序与优化取舍)
3. [单因素 A/B 实验设计](#3-单因素-ab-实验设计)
4. [统计纪律: p50/p95/CI95](#4-统计纪律-p50p95ci95)
5. [严格配对比较](#5-严格配对比较)
6. [负实验价值与记录](#6-负实验价值与记录)
7. [Gate-based 质量门控](#7-gate-based-质量门控)
8. [设备放置分层审计](#8-设备放置分层审计)
9. [生命周期与故障注入](#9-生命周期与故障注入)
10. [证据层级体系 (L0-L5)](#10-证据层级体系-l0-l5)
11. [冻结-复现闭环](#11-冻结-复现闭环)
12. [内部 vs 官方标签纪律](#12-内部-vs-官方标签纪律)
13. [工程原则](#13-工程原则)
14. [文档纪律](#14-文档纪律)
15. [案例: F6 T2W A/B 实战](#15-案例-f6-t2w-ab-实战)

---

## 1. Profiling 驱动的瓶颈定位

**原则**: 不猜，逐阶段测量。

```
Phase 2 Step 1-5 的标准流程:
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ Baseline │ →  │ 分解延迟  │ →  │ 瓶颈排序  │ →  │ 候选生成  │ →  │ A/B 验证  │
  │ 测量      │    │ 预算      │    │ (Amdahl)  │    │ 排名      │    │ 严格配对  │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

**F6 实战**:

| Step | 动作 | 发现 |
|------|------|------|
| 1. Baseline | 测量 Request→W0 总延迟 | p50=4798ms |
| 2. 分解 | 逐阶段计时: Prefill/Decode/Talker/T2W | T2W=93% of W0 |
| 3. Amdahl | 按占比×加速比排序 | T2W 是 #1 且唯一值得优化的 |
| 4. 候选 | 找最小改动把 T2W 搬到 CANN | env-only 开关 (零代码修改) |
| 5. A/B | 严格配对测量 | W0 −81.4%, CI 不含 0 |

**关键教训**:
- 如果跳过 Step 2 (分解)，可能去优化 Decode (2.9%) 而错失 T2W (93%)
- Baseline 先固化（commit/配置/输入/采样种子），之后所有比较以此为锚

详见: `docs/F6_PHASE2_STEP2_LATENCY_BUDGET.md`

---

## 2. Amdahl 排序与优化取舍

**Amdahl 定律**: 优化收益上限 = 占比 × 该阶段的加速比。

```
F6 原始 Basline Amdahl 排名:
  #1: T2W Flow+Vocoder (93%)     → 值得优化 (唯一高占比路径)
  #2: Talker token gen (2.9%)    → REJECT (即使 10× 加速, 总收益 <3%)
  #3: Prefill (不定)              → REJECT (除非 KV HIT 可消除)
  #4: 其他 (<1%)                  → REJECT_BY_AMDAHL
```

**Amdahl 决策流程**:

```
占比 > 10% ?
  ├── YES → 评估可行加速比
  │         ├── > 2× ? → ACCEPT (进入 A/B)
  │         └── < 2× ? → REJECT (收益不显著)
  └── NO  → REJECT_BY_AMDAHL (占比不足)
```

**F6 中的 Amdahl REJECT**:
- B6b (chunk size): 占比太小，CI 跨 0 → REJECT
- MTP: 模型不支持 → NOT_REACHABLE
- O1 参数调优: 不改变瓶颈 → REJECT

**关键教训**: 不是"看起来慢就优化"，是按占比×可行加速比排序。大部分"优化"在 Amdahl 过滤层被毙掉——这是正确的。

详见: `docs/F6_PHASE2_STEP5_AMDAHL_RANKING.md`

---

## 3. 单因素 A/B 实验设计

**原则**: 一次只改一个变量。

```
A/B 实验必须控制的变量:
  ✅ 同一 binary (同一 commit，同一构建)
  ✅ 同一硬件 (同一 910C 卡)
  ✅ 同一模型 (同一 GGUF 文件，SHA 一致)
  ✅ 同一输入 (同 prompt、同 reference audio)
  ✅ 同一协议 (同 HTTP endpoint、同计时边界)
  ✅ 仅差异: 实验变量 (env var / 代码行 / 配置参数)
```

**F6 T2W A/B 的控制变量清单**:

| 变量 | Baseline | Candidate | 控制? |
|------|---------|-----------|-------|
| 源码 commit | e159b3ee | e159b3ee | ✅ 同 |
| Binary | e159b3ee build | e159b3ee build | ✅ 同 |
| 硬件 | 910C dual-die | 910C dual-die | ✅ 同 |
| 模型 | MiniCPM-o-4_5-F16.gguf | 同一文件 | ✅ 同 |
| Prompt | 32 组固定文本 | 同 32 组 | ✅ 同 |
| HTTP 协议 | 同一 client | 同一 client | ✅ 同 |
| 计时边界 | HTTP→WAV mtime | 同一代码路径 | ✅ 同 |
| **仅差异** | OMNI_T2W_DEVICE=default (CPU) | OMNI_T2W_DEVICE=cann-flow-only | ✅ 单因素 |

**为什么不用同一 binary 同一次运行?**
单次运行内 before/after 切换会受 warmup/资源残留影响。独立运行 + 配对比较更可靠。

---

## 4. 统计纪律: p50/p95/CI95

**原则**: 比赛指标不可伪造。内部参考值与官方结果必须严格区分。

### 为什么不用 mean?

```
示例: [100, 102, 98, 105, 5000, 101]
  mean = 917.7   ← 被单个 outlier 拉偏
  p50  = 101.5   ← 稳定
  p95  = 5000    ← 暴露长尾
```

**F6 统计输出标准**:
- 样本量 (n) 明确标注
- p50 / p95 / CI95（不只用 mean）
- CI95 用 bootstrap (10,000 resamples)，非正态假设
- 排除规则预先声明（不能事后挑数据）
- 排除率明确记录（不悄悄丢弃异常值）

### Bootstrap CI95 计算

```
给定 n 个配对差值 d[0..n-1]:
  for i in 1..10000:
    resample n 个值 (有放回) → 取 mean
  排序 → [2.5%, 97.5%] = CI95

判定: CI95 不含 0 → 统计显著
```

**F6 实例**:
- T2W A/B: n=32 pairs, p50 Δ=−3904ms, CI95=[−4220,−3732] → 不含 0 → PASS
- B6b: CI95 跨 0 → REJECT

### 排除规则

**必须预先声明**。例: S13 120/120 baseline 中的排除规则:
- warmup (前 N 个请求)
- 非正常退出 (rc != 0)
- 协议错误 (HTTP 5xx)

排除率必须在报告中明确记录。120/120 valid 意味着排除率=0%。

---

## 5. 严格配对比较

**原则**: 配对比较不是"挑好的比"。所有配对预先声明，不能事后挑数据。

### 配对设计

```
工作流:
  1. 固定 N 组输入 (prompt list)
  2. Baseline: 全部 N 组 → 记录 N 个测量值
  3. Candidate: 同 N 组 (同顺序) → 记录 N 个测量值
  4. 配对差值: d[i] = candidate[i] - baseline[i]
  5. 统计: p50/p95/CI95 of d
```

### 不允许的操作

- ❌ "baseline 跑 50 次取最好的，candidate 跑 50 次取最好的"
- ❌ "排除掉那几次特别慢的"
- ❌ "只比较有明显的改善的 case"
- ❌ "baseline 和 candidate 用了不同 prompt"
- ❌ "baseline 在 warm，candidate 在 cold"

### F6 T6 KV A/B 中的配对排除

28/30 valid, 2 A_ERR pairs documented:
- 不是 "挑 28 个最好的"——是全部 30 pairs 运行后，2 对因 A_ERR (非性能故障) 排除
- 排除规则预先声明；A_ERR 原因记录在报告中
- 不会因为排除而改变统计结论

---

## 6. 负实验价值与记录

**原则**: 失败实验也有价值——记录为什么失败、学到了什么、如何避免重复。

### F6 负实验: B6b

| 项目 | 内容 |
|------|------|
| 假设 | 降低 speak_threshold 10→5 能更早触发 TTS |
| 方法 | Single-factor A/B, n≈60 |
| 结果 | CI95 跨 0，收益不显著 |
| 决策 | REJECT_BY_AMDAHL |
| 教训 | TTS chunk 调度阈值不是瓶颈；chunk 生成速率由 LLM decode 驱动 |

### 负实验记录模板

```
## 负实验: [标题]
- 假设: ...
- 方法: ...
- 样本: n=..., 配置: ...
- 结果: p50 Δ=..., CI95=[..., ...], 跨0: YES/NO
- 决策: REJECT
- 教训: ...
- 证据路径: docs/tracking/...
```

详见: `docs/tracking/F6_B6B_REJECTED_CANDIDATE.md`, `docs/tracking/F6_B6B_ENGINEERING_THRESHOLD_ANALYSIS.md`

---

## 7. Gate-based 质量门控

**原则**: 每个优化必须有配对 A/B + 正确性回归 + 稳定性验证，不能只报 best-case。

### Gate 层级

```
Gate 层级:
  L1: 单次正确性    → 输出一致？无崩溃？无 CPU fallback？
  L2: 配对性能      → 同一 workload 下 before/after delta 方向与量级
  L3: 统计显著性    → CI95 不含 0？p50/p95 均改善？
  L4: 回归栅栏      → 已有 Gate 全部重跑，不引入退化
  L5: 稳定性        → 无内存泄漏？无 CANN error？无超时？
```

### Gate 判定规则

| Gate | 条件 | 动作 |
|------|------|------|
| 正确性 | 所有 comparison pairs 输出语义等价 | 继续 |
| 正确性 | 任何 hard crash / CANN error | **REJECT immediately** |
| 性能 | CI95 不含 0 | PASS |
| 性能 | CI95 跨 0 | REJECT |
| 正确性 | CPU fallback > 0 | 调查 → 修复 → 重跑 |
| 稳定性 | CANN error / timeout / OOM | 调查 → 修复 → 重跑 |
| 回归 | 任何已有 Gate 退化 | **REJECT immediately** (no regressions allowed) |

### T6 集成回归的 11 个 Gate

| Gate | 结果 |
|------|------|
| S13 120/120 稳定性 | PASS |
| Extended 30/30 | PASS |
| Voice 5/5 + isolation | PASS |
| Disconnect 5/5 + follow-up | PASS |
| KV A/B (28/30 valid) | PASS |
| Smoke 5/5 | PASS |
| cpu_fallback=0 | PASS |
| cann_error=0 | PASS |
| **ACCEPT** | **11/11** |

---

## 8. 设备放置分层审计

**原则**: `-ngl 999` ≠ 全部计算在 NPU。

### 审计层次（从粗到细）

```
1. 权重放置      → 模型参数在哪个设备          → ggml_backend_buffer_type 检查
2. 算子放置      → 每个 op 在哪个 backend      → supports_op + scheduler 追踪
3. Tensor 放置   → 中间结果在哪种 buffer       → GGML_TENSOR_FLAG_INPUT 审计
4. KV Cache 放置 → LLM/TTS KV 各自在哪         → offload_kqv + ctx_map 验证
5. 同步点        → Host↔Device sync call sites → synchronize() / memcpy 类型
6. 图分裂        → CPU↔CANN graph split 触发点  → scheduler Pass 5 审计
```

**F6 最大收益来源**: 第 2 层审计发现 T2W 默认走 CPU（即使主 LLM 在 NPU）→ env-only 修正 → W0 −81.4%。

详见: `docs/audit/CANN_CPU_NPU_PLACEMENT_AUDIT.md` 及 4 个辅助文档

---

## 9. 生命周期与故障注入

### 生命周期测试

```
Persistent Server 生命周期:
  Start → Idle (等待)
    → omni_init (模型加载)
    → Prefill (KV 写入)
    → Decode #1 → complete
    → Decode #2 → complete (ctx still valid?)
    → Decode #N → complete
    → Reset → Prefill → Decode
  → Stop

测试矩阵:
  - Sequential N requests (ctx reuse)
  - Interleaved prefill + decode
  - Break mid-generation + continue
  - Reset + new prefill + decode
```

### 故障注入

| 注入 | 预期行为 | F6 状态 |
|------|---------|---------|
| Request during active generation | 排队或拒绝 | handled |
| Disconnect mid-generation | Clean shutdown, no leak | 5/5 PASS |
| Invalid session_id | Error response, no crash | handled |
| Missing prefill before decode | Error response | handled |
| Concurrent requests | 单会话：排队 | 设计限制 |
| SIGTERM during generation | Graceful shutdown | handled |

### F6 边界测试 (T13)

| 边界 | 测试 | 结果 |
|------|------|------|
| n_past → 4096 (n_ctx limit) | 单请求内多次 speak → TTS KV overflow? | T13 guard=39, cap=256 → PASS |
| Prefill size > n_ctx | 超长 system prompt | 错误处理正确 |
| 0 length user_text | 空输入 | 正常处理 |

---

## 10. 证据层级体系 (L0-L5)

**原则**: 不同结论需要不同等级的证据支撑。不可越级宣称。

| Level | 含义 | 方法论 | 可用于 |
|-------|------|--------|--------|
| L0 | 假设 | 推理/经验 | 内部讨论 |
| L1 | 源码静态证据 | 代码审计、路径追踪 | 代码分析报告 |
| L2 | 运行时日志 | 日志解析、单次观测 | 内部追踪 |
| L3 | 单因素 A/B | 严格配对实验 | 内部优化报告 |
| L4 | 长稳回归 | 多 Gate + 稳定性回归 | 内部冻结判定 |
| L5 | 官方 Harness | 官方脚本 + 对称性校验 | **仅 L5 可写 OFFICIAL_PASS** |

**当前 F6 最高证据等级: L4** (T6 integrated regression, 11/11 PASS)。无 L5 证据。

### 证据升级规则

```
L0 → L1: 源码验证假设 (读代码确认)
L1 → L2: 单次运行确认 (日志确认)
L2 → L3: A/B 严格配对 (样本足够 + CI 判定)
L3 → L4: 全 Gate 重跑 (无退化)
L4 → L5: 官方 Harness 产出的结果

不可跳级。不可从 L2 直接宣称 L5。
```

### F6 证据层级分布

| Level | 数量 | 示例 |
|-------|------|------|
| L0 | — | (所有假设已升级) |
| L1 | 1 | CANN CPU/NPU 放置审计 (E12) |
| L2 | 2 | Persistent lifecycle (E03), Daily-Omni pilot (E11) |
| L3 | 4 | T2W A/B (E04), Static Prefix KV (E02), B6b (E05), T9 fixes (E07/E08) |
| L4 | 1 | T6 集成回归 (E09+E10) |
| L5 | 0 | (全部 NOT_RUN) |

---

## 11. 冻结-复现闭环

**原则**: 任何声称的结果必须可复现。

```
冻结链:
  源码 SHA (bdd4550)
    → 二进制 SHA (db258375...)     ← 两次干净重建一致
      → 模型 SHA (d1e69845...)     ← GGUF 文件不变
        → 数据 SHA                 ← benchmark 输入不变
          → 配置 SHA               ← server.env + 命令行参数
            → 结果                  ← 给定以上全部，任何人可复现
```

**关键实践**:
- `build-twice-same-dir`: 验证二进制可复现
- `manifest.json`: 每次运行落盘全部指纹 (binary SHA/model SHA/commit/env/命令)
- `check_baseline_candidate_symmetry.py`: 保证 baseline/candidate 同条件

### Manifest 包含的指纹

```json
{
  "binary_sha256": "db258375...",
  "model_sha256": "d1e69845...",
  "source_commit": "bdd4550",
  "env": {
    "OMNI_T2W_DEVICE": "cann-flow-only",
    "OMNI_VOC_DEVICE": "gpu",
    "OMNI_KV_CACHE_REUSE": "1"
  },
  "cmdline": ["-ngl", "999", "-fa", "off", "-c", "4096", ...],
  "timestamp": "2026-08-05T12:00:00Z",
  "hostname": "...",
  "cann_version": "9.1.0.beta1"
}
```

---

## 12. 内部 vs 官方标签纪律

**原则**: 比赛指标不可冒充。内部参考值与官方结果必须严格区分。

### 标签体系

| 标签 | 含义 | 能用于 | 示例 |
|------|------|--------|------|
| `INTERNAL_PASS` | 内部验证通过 | 内部追踪、文档 | T2W A/B 32/32 |
| `LLAMA_CONFIRMED` | 冻结日志实测值 | 内部指标引用 | S13 p50=17.0s |
| `NOT_RUN` | 未运行 | 官方 Gate 待执行 | Daily-Omni 官方 |
| `NOT_MEASURED` | 特定指标未采集 | 限制声明 | STREAM_SYNC_RUNTIME_COST |
| `TO_MEASURE` | 计划测量 | 路线图 | CPU_PER_CHUNK_CRITICAL_PATH |
| `BLOCKED_BY_OFFICIAL_STARTER_KIT` | 被外部阻塞 | 状态说明 | 全部官方 Gate |
| `NOT_CLAIMED` | 明确不宣称 | 官方指标 | COMPETITION_COMPLETE |
| `FINAL_INTERNAL` | 内部冻结候选 | 项目状态 | 当前整体状态 |

### 禁止使用的标签

- `OFFICIAL_PASS` — 无 L5 证据不得使用
- `COMPETITION_COMPLETE` — 官方 Gate 未完成
- `正式比赛完成` — 同上
- `正式比赛候选` — 改为 `内部冻结候选 FINAL_INTERNAL`

### 跨文档一致性检查

```
所有顶层文档 (.md in docs/) 必须:
  - 使用相同的状态标签 (不混用)
  - 官方 Gate 状态统一为 NOT_RUN
  - 不出现 "正式比赛" (除说明 NOT_CLAIMED 时)
  - 不出现未经证据支撑的性能数字
```

---

## 13. 工程原则

1. **只优化 Amdahl 排名 Top-N** — 占比 <5% 的路径标记 REJECT_BY_AMDAHL
2. **不为了"干净"而丢弃现场** — 失败实验也有价值（记录为什么失败）
3. **文档与代码同步** — STATUS.md/AUDIT.md 在每次事件后立即更新，不滞后
4. **不猜配置** — 所有环境变量、后端参数必须源码确认存在 + 实际读取
5. **不跨后端照搬结论** — CUDA 的发现不能直接写成 CANN 的结论
6. **冻结后不再改** — `bdd4550` 之后的优化走新分支，不影响比赛候选
7. **不报 best-case** — 报 p50/p95/CI95，不是"最快的一次"
8. **CI95 不含 0 才宣称改善** — 否则就是"不确定"
9. **排除规则预先声明** — 不能事后挑数据，不能悄悄丢异常值
10. **同口径比较** — 性能数字必须附 binary SHA / 硬件 / 模型 / 配置 / 计时边界

---

## 14. 文档纪律

### 文档写入原则

- 每个结论必须有对应的证据路径 (E01-E16)
- 每个性能数字附 commit / binary SHA / 配置 / raw 路径 / 状态标签
- 不确定的数据标注 `NOT_MEASURED`，不填占位符
- "首次"、"最佳"、"全部" 等绝对化词语必须有证据支撑

### 文档交叉引用格式

```markdown
详见 `docs/audit/CANN_CPU_NPU_PLACEMENT_AUDIT.md` (不是 `docs/audit/...`)
详见 `docs/F6_PHASE2_STEP6_CANN_T2W_AB.md` (相对路径)
```

### 版本溯源

内部文档不追求"最新"——追求"可溯源到具体 commit"。
每份重要报告标注 `Generated from commit: bdd4550` 或 `Frozen at: bdd4550`。

---

## 15. 案例: F6 T2W A/B 实战

### 背景

Phase 2 Step 2 延迟预算分析发现 T2W 占 W0 的 93%。

### 假设

`OMNI_T2W_DEVICE=cann-flow-only` + `OMNI_VOC_DEVICE=gpu` 将 Flow + Vocoder 从 CPU 搬到 CANN 后，W0 显著下降。

### 实验设计

- **变量**: 仅 env var（零代码修改）
- **控制**: 同 binary (e159b3ee)、同 910C、同 GGUF、同 32 prompt、同 HTTP 协议
- **样本**: n=32 strict matched pairs
- **计时边界**: HTTP request arrival → 首个 WAV 文件 mtime
- **排除规则**: 预先声明无排除（全部纳入统计）
- **统计**: bootstrap CI95 with 10,000 resamples

### 结果

| 指标 | Baseline | Candidate | Δ | CI95 |
|------|---------:|----------:|----:|------|
| W0 p50 | 4798 ms | 894 ms | −3904 ms (−81.4%) | [−4220, −3732] |
| n | 32 | 32 | 32 pairs | 不含 0 |

### 验证

- CPU fallback count: 0
- WAV validity: 32/32 16-bit PCM @24kHz
- Consistency across 4 case types: all −79% to −83%

### 决策

**ACCEPT** ✅ — 统计显著、效果大、零代码修改、正确性无损。

### 证据链

```
E04: CANN T2W 设备放置
  ├── 报告: docs/F6_PHASE2_STEP6_CANN_T2W_AB.md
  ├── Raw:   docs/f6-s13-closure/phase2/step6_cann_t2w_ab.json
  ├── 源码:  tools/omni/omni.cpp:5589 (OMNI_T2W_DEVICE read)
  │          tools/omni/token2wav/token2wav-impl.cpp:7465 (init_backend)
  │          tools/omni/token2wav/token2wav-impl.cpp:6880 (vocoder dispatch)
  └── 记忆:  /root/.claude/projects/-workspace/memory/f6-phase2-step6-cann-t2w-ab.md
```

### 教训

1. **瓶颈定位优先**: 如果先优化 decode (2.9%) 而忽略 T2W (93%)，最大收益无从发现
2. **最小改动原则**: env-only 开关 vs 代码修改——前者风险最低、可逆性最好
3. **设备放置不等于算子覆盖**: 算子支持 CANN ≠ 运行时实际在 CANN。必须审计 scheduler 实际分配
