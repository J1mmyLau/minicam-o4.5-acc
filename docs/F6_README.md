# F6 Decode-to-Speak 优化项目 — 全貌总览

> **分支**: `perf/f6-decode-to-speak`（HEAD: `80a86ab`）
> **冻结候选源码**: `bdd4550`（不得修改）
> **状态**: `FINAL_INTERNAL=PASS` / `OFFICIAL_GATE_TOOLING_READINESS=PASS` / `OFFICIAL_GATES=BLOCKED_BY_OFFICIAL_STARTER_KIT`

## 一句话

在 llama.cpp-omni（MiniCPM-o 4.5）上，针对 Ascend 910C 单卡 + CANN 9.1.0-beta.1，将**首包语音延迟从 4.8s 降到 0.9s（−81%）**，并冻结为正式比赛候选。

## 做了什么

```
Phase 1: 瓶颈定位        → 发现 T2W CPU 路径占首包延迟 93%
Phase 2: 设备放置修正      → T2W/Flow/Vocoder 从 CPU 搬到 CANN NPU
Phase 3: KV Cache 生产化   → 静态 prefix prefill 复用（2.5× 加速）+ 全生命周期正确性
比赛收口: 提交工具链       → baseline/candidate 对称采集 + Gate 就绪 + 文档
```

核心收益全部来自**把已在 NPU 的主模型之外的计算也搬到 NPU**——不是调参，是修正设备放置。

## 关键数字

| 指标 | Before | After | Delta |
|------|-------:|------:|------:|
| Request→W0 p50 | 4,798ms | 894ms | **−81.4%** |
| Prefill p50（KV HIT） | 210ms | 86ms | **2.5×** |
| Per-chunk RTF p50 | — | 0.28 | 实时比 3.6× |
| T6 回归 Gate | — | **11/11 PASS** | ACCEPT=True |
| 稳定性 | — | 120/120 valid | 0 runaway |

## 怎么做到的（方法论摘要）

1. **Profiling 驱动的瓶颈定位** — 不是猜，是逐阶段测量
2. **Gate-based 质量门控** — 每个优化必须有配对 A/B + 正确性回归
3. **统计纪律** — p50/p95/CI95，不是单次 best-case
4. **设备放置分层审计** — 权重放置 ≠ 算子放置 ≠ Tensor 放置 ≠ KV 放置
5. **冻结-复现闭环** — 源码 SHA / 二进制 SHA / 模型 SHA 全部固化

详见 [`F6_METHODOLOGY.md`](F6_METHODOLOGY.md)。

## 文档导航

```
docs/
├── F6_README.md              ← 你在这里（全貌总览）
├── F6_QUICKSTART.md           ← 5 分钟跑起来
├── F6_METHODOLOGY.md          ← 方法论与工程纪律
│
├── f6-s13-closure/            ← 冻结证据归档（DO NOT MODIFY）
│   ├── README.md              ← S13 closure 总览
│   ├── phase2/
│   │   ├── F6_PHASE3_FINAL_FRAMING.md    ← 最终口径
│   │   ├── F6_FINAL_DELIVERY_REPORT.md   ← 交付报告
│   │   └── T6_INTEGRATED_REGRESSION_REPORT.md ← T6 11/11
│   └── raw-data/              ← 原始日志与 JSON
│
├── competition-submission/    ← 比赛提交文档
│   ├── OFFICIAL_GATE_STATUS.md           ← Gate 仪表盘
│   ├── OFFICIAL_GATE_READINESS_REPORT.md ← 就绪度核查
│   ├── OFFICIAL_GATE_TOOLING_SELFTEST.md ← 工具链自检 14/14
│   ├── CHUNK_RTF_MEASUREMENT_SPEC.md     ← RTF 测量规范
│   └── COMPETITION_REQUIREMENTS_MATRIX.md ← 需求矩阵
│
├── vllm-migration/            ← vLLM 迁移文档（比赛约束层）
│   ├── README.md
│   ├── VLLM_METRIC_MEASUREMENT_SPEC.md   ← TTFT/TTFP/chunk RTF 口径
│   └── VLLM_OPTIMIZATION_EXECUTION_PLAN.md
│
├── tracking/                  ← 170+ 份工程追踪（审计/事件/A/B/报告）
│   └── AUDIT.md               ← 全量审计日志
│
└── experiments/               ← 实验记录
    ├── operator-optimization/  ← 算子优化（CANN Vocoder 等）
    ├── kv-cache-production/    ← KV Cache 生产化长测
    └── e2e-ngl8/              ← 早期 E2E 实验
```

根目录：
- `STATUS.md` — 项目状态流水账（413 行，每次事件后更新）
- `README.md` — llama.cpp-omni 项目通用介绍（非 F6 专属）

## 提交工具链

```bash
# 环境检查
bash submission/environment/env_check.sh

# dry-run 预检（不起服务、不占 NPU）
MODEL_PATH=<model.gguf> bash submission/scripts/run_performance.sh candidate --dry-run

# 完整离线自检
SELFTEST_MODEL_PATH=<model.gguf> bash submission/tests/run_selftest.sh
```

详见 [`F6_QUICKSTART.md`](F6_QUICKSTART.md) 和 `submission/tests/run_selftest.sh`。

## 约束

- 冻结源码 `bdd4550` 不得修改
- 不宣称 OFFICIAL_BENCHMARK_PASS / COMPETITION_COMPLETE
- 官方 Gate 全部 BLOCKED_BY_OFFICIAL_STARTER_KIT
- 只允许修改 benchmark 脚本/Demo 适配/统计脚本/submission/复现文档/官方结果文档
