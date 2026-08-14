# RESULTS — 最终结果（准确率 + RTF）

> 候选：`fd3dd36`（tag `competition-final-20260814`）· 环境：1× Ascend 910C（dual-die）+ CANN 9.1.0-beta.1 ·
> 模型：`MiniCPM-o-4_5-F16.gguf` · 运行时：Config D（见 `OPTIMIZATIONS.md`）。
> 所有结果 = 统一评测分支（`tc-mb/llama.cpp-omni` @ `bench/huawei`）上的**全量**公开子集。
> 官方隐藏测试集 / Overall 分母未公开；公开后同脚本复核分母，数值会以主办方口径为准。

## 1. 准确率（四项精度指标，全部 PASS）

| 基准 | 候选结果 | 验收线 | 判定 |
|---|---|---|---|
| Daily-Omni | **79.43%**（950/1196） | ≥ 77.5% | ✅ PASS（+1.93pp） |
| Video-MME | **69.8%** | ≥ 67.0% | ✅ PASS（+2.8pp） |
| Seed-TTS ZH_WER | **1.422%**（2020/2020） | ≤ 1.56% | ✅ PASS（优于 pristine 1.5%） |
| Seed-TTS SIM（ASV） | **0.969**（2020/2020） | ≥ 0.689 | ✅ PASS |

- 原始汇总：`experiments/nightly/trackC_seedtts_full/summary_tts.json`（WER 1.422% / SIM 0.969 / 0 NaN）。
- 四项精度指标（三个 Benchmark）在候选 binary 上验证通过，Config D **零精度副作用**（Seed-TTS simplex 保持 pristine NPU 路径）。

## 2. 官方 SPEAK→WAV RTF

| 口径 | 值 | 说明 |
|---|---|---|
| core.rtf_aggregate | **1.09–1.17** | LISTEN-wedge 修复后 2 次独立运行，n_speak 0→33，0 拒绝 |
| 官方基线 | 1.087 | 主办方公开 baseline |
| 相对基线加速 | **无已证实加速** | RTF 落在基线 parity 区间 |

> **诚实口径（务必引用原文）**：
> - RTF **可用**（不再是 BLOCKED），根因是 LISTEN-wedge 生命周期 bug（空 duplex LISTEN chunk_end 未完成
>   drain 记账 → active_gen 楔死 → NOT_REUSABLE 拒绝）。修复见 `docs/F6_OFFICIAL_RTF_RESOLVED.md`。
> - **不要把 Config D 的 ~18% wall 改善写成 official RTF −18%**。Config D 的 wall 改善是**本地配对 A/B**
>   （`docs/F6_*` 系列证据），不是 official RTF 指标。official RTF 当前 = parity，无加速。
> - 证据：`docs/F6_OFFICIAL_RTF_RESOLVED.md`。

## 3. 稳定性

- 2 次 RTS soak：0 崩溃、0 线程泄漏（Track D，`docs/F6_TRACK_D_*`）。
- 无线程泄漏（不适用 RTS/eval 路径），唯一历史负面 = SPEAK turn 楔死（候选级，非 Config D）。

## 4. 结果口径声明

- 准确率对比是 baseline/candidate **同脚本、同子集、同分母**（统一评测分支）。
- 内部 pilot / 内部 profiler / 冻结 T6 数字**不作为**官方结果。
- 完整 gate 状态见 `docs/competition-submission/OFFICIAL_GATE_STATUS.md`。

## 5. 数据可视化

四项精度 + T2W 优化迭代 + W0 Amdahl 占比 + 官方 RTF parity 四张图，
由 `submission/performance/make_charts.py` 离线生成（`python3 make_charts.py`）到
`submission/performance/charts/`：

- `accuracy.png` — 四项精度指标 vs 验收线（全部 PASS）
- `t2w_iteration.png` — T2W 延迟演进（本地 A/B，非 official RTF）
- `w0_breakdown.png` — W0 时间占比（Amdahl）
- `rtf_parity.png` — 官方 SPEAK→WAV RTF（parity，无已证实加速）
