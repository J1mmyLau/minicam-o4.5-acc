# 官方 Gate 状态（比赛收口 Dashboard）

> 唯一权威状态页。每次官方 Gate 判定变化时更新本文件 + AUDIT.md。
> **当前阶段：OFFICIAL_UNIFIED_EVAL_BRANCH=AVAILABLE** —— 主办方已提供统一评测分支
> `tc-mb/llama.cpp-omni`（branch `bench/huawei`，含 `evaluation/README.md` + `./run_all.sh --smoke 2`），
> 本项目已用其跑通 official smoke 4/4 rc=0、Daily-Omni 全量、Video-MME 全量、Seed-TTS 2020/2020。
> 就绪度核查见 `OFFICIAL_GATE_READINESS_REPORT.md`；工具链自检见 `OFFICIAL_GATE_TOOLING_SELFTEST.md`。
> **工具链就绪状态**：DRY_RUN_SUPPORT=PASS / BASELINE_CANDIDATE_SYMMETRY=PASS / CHUNK_AUDIO_VALIDATION=PASS /
> PRIVATE_PATH_AUDIT=PASS / LOCAL_ASSET_MANIFEST=PASS / **OFFICIAL_ASSET_VERSION_MATCH=CONFIRMED** /
> **OFFICIAL_GATE_TOOLING_READINESS=PASS** / **STARTER_KIT_BLOCKER=REMOVE** / OFFICIAL_GATES=READY_TO_EXECUTE / COMPETITION_COMPLETE=NOT_CLAIMED。
> **OFFICIAL_RTF=AVAILABLE（1.09–1.17 core，parity baseline 1.087）** —— LISTEN-wedge 已修，见 `docs/F6_OFFICIAL_RTF_RESOLVED.md`。
> 候选冻结口径（2026-08-14）：source `fd3dd36`（tag `competition-final-20260814`，最终 branch `competition/final-ascend-track-a`）/
> server `4694cb58…` / libomni `3f3e1e63…` / model `d1e69845…`。四项精度指标 PASS（见下方证据索引 + `f6-release-convergence`）。
> **资产版本标签**：已用统一评测分支跑通全量，`OFFICIAL_ASSET_VERSION_MATCH` 置 CONFIRMED；当前 commit/SHA 为
> **FINAL_INTERNAL** 候选快照（官方最终测试集未公开，官方 Over​all 分母仍以统一分支口径为准）。

---

## 总览

| Gate | 状态 | 判定依据 / 阻塞原因 | 置位条件 |
|---|---|---|---|
| FINAL_INTERNAL（内部候选冻结） | ✅ **PASS** | 源码冻结 + REPRODUCIBLE_BINARY=PASS + 冻结二进制 T6 11/11 | 已满足 |
| T6_FROZEN_BINARY_REGRESSION | ✅ **PASS** | 11/11 GATES PASS, ACCEPT=True（T6 历史冻结 db258375；最终 binary server 4694cb58… / libomni 3f3e1e63… 经 Phase 8 smoke + RTS 复验） | 已满足 |
| DAILY_OMNI_INTERNAL_PILOT | ✅ **PASS** | 服务器链 6/6 门；9 题 pilot；P0 修复 3 项 | 已满足（**非官方准确率**） |
| REPRODUCIBLE_BINARY | ✅ **PASS** | 两次干净重建 SHA 逐字节一致 | 已满足 |
| **OFFICIAL_DAILY_OMNI** | ✅ **PASS（准确率）** | 统一评测分支全量 79.43%（950/1196）≥ 77.5%，+1.93pp | 官方隐藏测试集公开后复核分母 |
| **OFFICIAL_TTS_SEED** | ✅ **PASS（准确率）** | 统一评测分支全量 WER 1.422%（≤1.56）/ SIM 0.969（≥0.689），2020/2020，0 NaN | 官方隐藏测试集公开后复核分母 |
| **OFFICIAL_VIDEO_MME** | ✅ **PASS（准确率）** | 统一评测分支全量 69.8% ≥ 67.0%，+2.8pp | 官方隐藏测试集公开后复核分母 |
| **OFFICIAL_DEMO_GATE** | 🔴 **NOT_RUN** | 官方 Demo = OpenBMB/MiniCPM-o-Demo，尚未实际接入（服务侧能力已验） | DEMO_VALIDATION_PLAN.md 12 用例全过 + 视频 |
| **OFFICIAL_PERFORMANCE_GATE** | ✅ **PASS（RTF=1.09–1.17 core）** | LISTEN-wedge 生命周期 bug 已修（`tools/omni/omni.cpp` 生产 patch，非受保护）；官方 RTS 首次产出 `rtf.core.rtf_aggregate`，n_speak 0→33，0 拒绝；见 `docs/F6_OFFICIAL_RTF_RESOLVED.md` | 已满足（2 次独立运行稳定） |
| **OFFICIAL_REPRODUCTION_REVIEW** | 🔴 **NOT_RUN** | 复现审计模板已建（REPRODUCTION_AUDIT.md） | 干净环境从零复现成功 |
| **COMPETITION_COMPLETE** | 🔴 **NOT_CLAIMED** | 仅当上表全部 OFFICIAL_* 置位 | 全部完成 |

---

## 内部 PASS 证据索引（已固化）

| 证据 | 路径 |
|---|---|
| T6 冻结二进制回归（11/11） | `docs/f6-s13-closure/phase2/t6_integrated_regression.json` |
| KV A/B 两条独立结论 | R13 canonical 30/30（`docs/f6-s13-closure/phase2/R13…`）+ 冻结 T6 28/30（t6_kv_ab_27of30.md） |
| Daily-Omni 内部 pilot | `docs/f6-s13-closure/phase2/daily_omni_pilot/PILOT_REPORT.md` |
| TTS KV guard 闭环 | `docs/f6-s13-closure/phase2/tts_boundary/tts_boundary_20260804_170049.json` |
| Seed-TTS 全量准确率 | `experiments/nightly/trackC_seedtts_full/summary_tts.json`（WER 1.422% / SIM 0.969 / 2020 条 / 0 NaN） |
| Daily-Omni 准确率基线 | 79.43%（950/1196，≥77.5% PASS，见 `f6-release-convergence`） |
| VideoMME 准确率基线 | 69.8%（PASS，见 `f6-release-convergence`） |
| 复现构建 | REPRODUCIBLE_BINARY=PASS（fd3dd36 重建 SHA 逐字节一致） |

---

## OFFICIAL_* 剩余阻塞项清单

> 统一评测分支（`tc-mb/llama.cpp-omni` @ `bench/huawei`）已到达：official smoke 4/4 + 四项精度指标全量
> 均在其上跑通。**"官方 Starter Kit 未到"的阻塞已移除**。剩余阻塞项如下：

| 资产 | 性质 | 阻塞的 Gate | 说明 |
|---|---|---|---|
| 官方**隐藏**测试集 / Overall 分母 | 官方未公开（属正常，非阻塞） | 四项精度指标最终 Overall | 当前数字 = 统一分支公开子集全量；隐藏集公开后同脚本复核 |
| OpenBMB/MiniCPM-o-Demo 前端接入 | GitHub（可拉取） | OFFICIAL_DEMO_GATE | `bash submission/scripts/start_demo.sh` |

---

## 决策规则（防伪造）

1. **不得**把内部 pilot / 内部 profiler / 冻结 T6 数字写成官方结果。
2. 任何 OFFICIAL_* 置位前必须有：官方脚本 + 原始输出 + 结果汇总 + 同一环境复现。
3. 精度对比必须是 baseline/candidate **同脚本同子集同分母**。
4. 状态变化一律写入 `docs/tracking/AUDIT.md`。
