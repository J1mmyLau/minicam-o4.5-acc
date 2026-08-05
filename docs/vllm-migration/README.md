# vLLM-Omni 迁移文档集（入口）

> **这是谁在看**：接手 MiniCPM-o 4.5 昇腾优化的人（或接手用的 AI）。你不需要先读所有文件，按本 README 的顺序即可。
> **这套文档解决什么问题**：我们在 llama.cpp-omni 上把 MiniCPM-o-4_5 优化到比赛交付，踩了大量跟"模型本身"无关的坑（设备放置、异步生命周期、接口协议、完成语义）。这些经验要迁移到 **vLLM-Omni**（官方 Thinker→Talker→Token2Wav 多 Stage pipeline）上，这就是迁移文档集。
> **最重要的纪律**：llama 侧数字只是参考标尺，**不是 vLLM 结果**；vLLM 未源码核实的一律 `TO_AUDIT`；内部结果 ≠ 官方结果。

---

## 30 秒版（你要做什么）

```text
先测量，后优化；准入先于性能。
第 1 步 = 官方接口冒烟（V1：字段完整，防"假低精度"卡准入）
第 2 步 = 三指标冻结基线（V2：TTFT / TTFP / 逐 chunk RTF，单卡）
第 3 步 = Stage 时间线 + 设备放置（V3+V4：三比赛指标占比 + Flow/Vocoder 真实设备）
```

排名核心（llama 子赛道）= **逐 chunk RTF**；vLLM 子赛道 = TTFT + TTFP + chunk RTF。准入（精度相对官方基线 ≤2pp + Demo 可用）先于性能排名。指标口径见 `VLLM_METRIC_MEASUREMENT_SPEC.md`。

llama 上的实测结论（供参考，勿直接当 vLLM 结果）：decode 只占端到端 ~2.9%，语音合成链（T2W）占 ~93%；设备放置从 CPU 迁到 NPU 使首音 −81.4%；静态前缀复用使 prefill 2.4×。

---

## 10 分钟版（读哪几个文件）

| 顺序 | 文件 | 你得到什么 |
|---|---|---|
| 1 | `LLAMA_TO_VLLM_EXPERIENCE_MIGRATION.md` | 12 条核心经验（每条 10 点）+ 4 条决策树 + **§2.5 赛事优先级映射** + 打点事件表 |
| 2 | `LLAMA_RAW_EVIDENCE_APPENDIX.md` | 所有 llama 数字的精确出处（数值/CI95/样本/来源） |
| 3 | `VLLM_METRIC_MEASUREMENT_SPEC.md` | **TTFT/TTFP/chunk RTF 口径**：定义/起止事件/raw schema/统计/误判清单 |
| 4 | `VLLM_COMPETITION_REQUIREMENTS.md` | 比赛规则约束层：准入（≤2pp + Demo）/ 指标 / 加分 / 交付 |
| 5 | `LLAMA_VLLM_COMPONENT_MAPPING.md` | 13 个组件 × 17 字段（含 4 个比赛字段）+ 6 条 rg 源码导航命令 |
| 6 | `VLLM_OPTIMIZATION_EXECUTION_PLAN.md` | 动手路线 V0–V12（比赛口径版），每阶段 16 字段 |
| 7 | `VLLM_RISK_AND_VALIDATION_MATRIX.md` | 16 条证据 + 40 条风险（R26–R40 比赛风险）+ 候选决策 |
| 8 | `VLLM_TEAM_HANDOFF.md` | 队友第一周计划 + 第一个小时 + **第一周禁止清单** + 最终交付清单 |
| 9 | `EXPERIMENT_TEMPLATES.md` | 4 基础模板 + 5 比赛模板（Metric / Accuracy / Demo / chunk RTF / Gate） |

> 快速路径：**先读 1 的 §0–§5 + §2.5**，测指标前读 3，比赛规则查 4，定位代码查 5，动手按 6，出故障按 7。

---

## 关键约定（所有文件通用）

### 证据状态标签（只能从这 4 个选）

| 标签 | 含义 |
|---|---|
| `CONFIRMED_FROM_DEPLOY_DOC` | 现有 vLLM 部署文档已写明 |
| `TO_AUDIT_IN_SOURCE` | 需在 vLLM 源码核实 |
| `TO_MEASURE_AT_RUNTIME` | 需在 vLLM 运行时测量 |
| `UNPROVEN` | 尚无任何证据 |

### 决策类别（只能从这些选）

```text
VERIFY_FIRST / PROFILE_FIRST / OPTIMIZE / DEFER
REJECT_BY_AMDAHL / NOT_APPLICABLE / QUALITY_RISK
```

### 状态标签（交付口径，禁止混用）

```text
DEPLOYMENT_PASS / INTERNAL_PERFORMANCE_PASS / INTERNAL_QUALITY_PASS
PENDING_EXTERNAL_ASSETS / OFFICIAL_BENCHMARK_PASS
```

> 官方 Gate（OFFICIAL_BENCHMARK_PASS / COMPETITION_COMPLETE）仅在官方 Harness 通过后置位。

---

## 第一周地图（做对 4 件事）

```text
规则+冒烟（V0/V1） → 三指标基线（V2） → 占比+设备（V3/V4） → 前缀 TTFT（V5）
```

本周不写算子、不做优化，只建立四张地图：**规则+接口 / 三指标基线 / 占比 / 设备**。详见 `VLLM_TEAM_HANDOFF.md` §3 + §5.1（第一周禁止清单）。

---

## 四个最常见陷阱（先记住）

1. **别先优化 decode** — llama 上 decode 只占 2.9%；先打点确认瓶颈。
2. **别把 memory-slot 类错误全归主模型 KV** — Talker/Token2Wav 有独立上限（llama 上是 4096）。
3. **别把"命中缓存"当"端到端收益"** — Prefix Cache 可能只覆盖 thinker 文本 KV，必须测端到端 TTFT / audio TTFP。
4. **别把内部结果当官方成绩** — 官方权重/归一化未定一律"待官方确认"；chunk RTF 必须逐 chunk 口径（request RTF / Flow 内部 RTF 都不算）。

---

## 变更记录

- 2026-08-03 — 初版 5 文件（组件映射 / 证据附录 / 执行计划 / 风险矩阵 / 交接包 + 主指南）。
- 2026-08-04 — 扩充为可执行深度：主指南 12 经验 + 4 决策树、执行计划 V0–V12 × 16 字段、风险 16→25、新增 `EXPERIMENT_TEMPLATES.md` 与本 README。
- 2026-08-05 — **同步 llama 侧冻结完成状态**：llama 内部候选已真正冻结（源码 `bdd4550`、二进制 `c4b16937`/`db258375` 固化、T6 冻结二进制 11/11 GATES PASS、REPRODUCIBLE_BINARY=PASS）。附录 §0/E/G、交接包 §8 更新为最终口径；文档索引修正为 8 个文件。**llama 侧不再属于候选研发**，本迁移集面向 vLLM-Omni 的审计与优化继续有效。
- 2026-08-05 — **对齐比赛约束层**：新增 `VLLM_METRIC_MEASUREMENT_SPEC.md`（TTFT/TTFP/chunk RTF 口径）+ `VLLM_COMPETITION_REQUIREMENTS.md`（比赛规则）；主指南加 §2.5 赛事优先级映射表；组件映射 13→17 字段（4 个比赛字段）；执行计划重排为比赛口径 V0–V12（Duplex 移入附加实验/DEFER）；风险矩阵 +R26–R40（比赛风险，5 字段）；交接包改准入优先（精度→Demo→单卡→指标）+ 第一周禁止清单；实验模板 +5 比赛模板。文档索引修正为 10 个文件。
