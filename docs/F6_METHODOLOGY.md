# F6 方法论与工程纪律

> 本文提炼 F6 decode-to-speak 优化项目中使用的方法论、统计纪律和工程原则。
> 不是操作手册（见 [F6_QUICKSTART.md](F6_QUICKSTART.md)），而是"为什么这样做"。

---

## 1. Profiling 驱动的瓶颈定位

**原则**：不猜，逐阶段测量。

```
Phase 2 Step 1-5 的标准流程：
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ Baseline │ →  │ 分解延迟  │ →  │ 瓶颈排序  │ →  │ 候选生成  │ →  │ A/B 验证  │
  │ 测量      │    │ 预算      │    │ (Amdahl)  │    │ 排名      │    │ 严格配对  │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

关键实践：
- **Baseline 先固化**：冻结 workload、输入、配置、采样种子——之后所有比较以此为锚
- **逐阶段分解**：Request→Prefill→Decode→TTS→T2W→首包，每段单独计时
- **Amdahl 排名**：不是"看起来慢就优化"，是按占比×可行加速比排序，只优化 Top-N
- **严格 A/B**：同一 binary 同一次运行？不。必须可复现的独立运行 + 配对比较

详见 `docs/F6_PHASE2_STEP2_LATENCY_BUDGET.md`、`docs/F6_PHASE2_STEP5_AMDAHL_RANKING.md`。

---

## 2. Gate-based 质量门控

**原则**：每个优化必须有配对 A/B + 正确性回归 + 稳定性验证，不能只报 best-case。

```
Gate 层级：
  L1: 单次正确性    → 输出一致？无崩溃？无 CPU fallback？
  L2: 配对性能      → 同一 workload 下 before/after delta 方向与量级
  L3: 统计显著性    → CI95 不含 0？p50/p95 均改善？
  L4: 回归栅栏      → 已有 Gate 全部重跑，不引入退化
  L5: 稳定性        → 无内存泄漏？无 CANN error？无超时？
```

关键纪律：
- **不报单次 best-case**：报 p50/p95/CI95，不是"最快的一次"
- **配对比较不是挑好的比**：所有配对必须预先声明排除规则，不能事后挑数据
- **回归必须全量**：加一个新优化 → 已有全部 Gate 重跑
- **Gate 失败 = 拒绝**：不能"差不多就过了"

详见 `docs/tracking/F6_GATE_STATUS_MATRIX.md`、`docs/f6-s13-closure/phase2/T6_INTEGRATED_REGRESSION_REPORT.md`。

---

## 3. 设备放置分层审计

**原则**：`-ngl 999` ≠ 全部计算在 NPU。

```
审计层次（从粗到细）：
  1. 权重放置      → 模型参数在哪个设备
  2. 算子放置      → 每个 op 在哪个 backend 执行
  3. Tensor 放置   → 中间结果在哪个设备的哪种 buffer
  4. KV Cache 放置 → 主 LLM / Talker / TTS 各自的 KV 在哪
  5. 同步点        → 哪些点强制 Host↔Device 同步
  6. 图分裂        → scheduler 是否产生 CPU↔CANN graph split
```

F6 的最大收益来自这一步——发现 T2W 默认走 CPU（即使主 LLM 在 NPU），修正后首包 −81%。

详见 `docs/F6_PHASE2_BASELINE_DEVICE_AUDIT.md`、`docs/tracking/F6_BASELINE_PROVENANCE.md`。

---

## 4. 统计纪律

**原则**：比赛指标不可伪造。内部参考值与官方结果必须严格区分。

```
统计输出标准：
  - 样本量（n）明确标注
  - p50 / p95 / CI95（不只用 mean）
  - 排除规则预先声明（不能事后挑数据）
  - 排除率明确记录（不悄悄丢弃异常值）
```

**标签纪律**（防冒充）：

| 标签 | 含义 | 能用于 |
|------|------|--------|
| `INTERNAL_VALIDATION_POLICY` | 内部统计规范 | 内部参考 |
| `LLAMA_CONFIRMED` | 冻结日志实测值 | 历史说明/埋点示例 |
| `OFFICIAL_REQUIREMENT` | 官方口径 | 仅官方 Harness 产出 |
| `NOT_CLAIMED` | 明确不宣称 | 全部官方指标 |

详见 `docs/competition-submission/CHUNK_RTF_MEASUREMENT_SPEC.md`。

---

## 5. 冻结-复现闭环

**原则**：任何声称的结果必须可复现。

```
冻结链：
  源码 SHA (bdd4550)
    → 二进制 SHA (db258375...)     ← 两次干净重建一致
      → 模型 SHA (d1e69845...)     ← GGUF 文件不变
        → 数据 SHA                 ← benchmark 输入不变
          → 配置 SHA               ← server.env + 命令行参数
            → 结果                  ← 给定以上全部，任何人可复现
```

关键实践：
- `build-twice-same-dir` 验证二进制可复现
- `manifest.json` 每次运行落盘全部指纹
- `check_baseline_candidate_symmetry.py` 保证 baseline/candidate 同条件

---

## 6. 工程原则

1. **只优化 Amdahl 排名 Top-N** — 占比 <5% 的路径标记 REJECT_BY_AMDAHL
2. **不为了"干净"而丢弃现场** — 失败实验也有价值（记录为什么失败）
3. **文档与代码同步** — STATUS.md/AUDIT.md 在每次事件后立即更新，不滞后
4. **不猜配置** — 所有环境变量、后端参数必须源码确认存在 + 实际读取
5. **不跨后端照搬结论** — CUDA 的发现不能直接写成 CANN 的结论
6. **冻结后不再改** — `bdd4550` 之后的优化走新分支，不影响比赛候选
