# 官方 Gate 状态（比赛收口 Dashboard）

> 唯一权威状态页。每次官方 Gate 判定变化时更新本文件 + AUDIT.md。
> **当前阶段：OFFICIAL_GATE_WAITING（工具链已就绪）** —— 文档/提交包/就绪度已收口，等官方 Starter Kit/Harness 到达后直接执行。
> 就绪度核查见 `OFFICIAL_GATE_READINESS_REPORT.md`（7 项核查 + 资产 manifest + 每条首命令）；工具链自检见 `OFFICIAL_GATE_TOOLING_SELFTEST.md`。
> **工具链就绪状态**：DRY_RUN_SUPPORT=PASS / BASELINE_CANDIDATE_SYMMETRY=PASS / CHUNK_AUDIO_VALIDATION=PASS /
> PRIVATE_PATH_AUDIT=PASS / LOCAL_ASSET_MANIFEST=PASS / **OFFICIAL_ASSET_VERSION_MATCH=PENDING_STARTER_KIT** /
> **OFFICIAL_GATE_TOOLING_READINESS=PASS** / OFFICIAL_GATES=BLOCKED_BY_OFFICIAL_STARTER_KIT / COMPETITION_COMPLETE=NOT_CLAIMED。
> 候选冻结口径（2026-08-05）：source `bdd4550` / docs `adb9bb6`+`d5cc978`+`f26323f`（基线）+ `7a3f11e`+`37dc598`+`379e2e6`+`b527dce`+`c328d1b`（收口）/
> server `db258375…` / libomni `c4b16937…` / model `d1e69845…`。
> **资产版本标签**：当前 commit/SHA 仅作 **CURRENT_LOCAL_ASSET_SNAPSHOT**；`OFFICIAL_ASSET_VERSION_MATCH` 在官方 starter kit 核对前一律 PENDING_STARTER_KIT，不得写成 CONFIRMED。

---

## 总览

| Gate | 状态 | 判定依据 / 阻塞原因 | 置位条件 |
|---|---|---|---|
| FINAL_INTERNAL（内部候选冻结） | ✅ **PASS** | 源码冻结 + REPRODUCIBLE_BINARY=PASS + 冻结二进制 T6 11/11 | 已满足 |
| T6_FROZEN_BINARY_REGRESSION | ✅ **PASS** | 11/11 GATES PASS, ACCEPT=True（meta.binary_sha=db258375） | 已满足 |
| DAILY_OMNI_INTERNAL_PILOT | ✅ **PASS** | 服务器链 6/6 门；9 题 pilot；P0 修复 3 项 | 已满足（**非官方准确率**） |
| REPRODUCIBLE_BINARY | ✅ **PASS** | 两次干净重建 SHA 逐字节一致 | 已满足 |
| **OFFICIAL_DAILY_OMNI** | 🔴 **NOT_RUN** | 数据在 `/workspace/benchmarks/Daily-Omni/`，但官方 Harness/子集/计时口径未定（starter kit 45 项 0/45 确认） | 官方 starter kit → run_daily_omni.sh 通过 |
| **OFFICIAL_TTS_SEED** | 🔴 **NOT_RUN** | 数据在 `/workspace/benchmarks/seed-tts-eval/`；官方能力指标（WER/SIM/RTF）未定 | 官方脚本 → run_tts_seed.sh 通过 |
| **OFFICIAL_VIDEO_MME** | 🔴 **NOT_RUN** | 数据在 `/workspace/benchmarks/Video-MME/`；官方子集/答案解析未定 | 官方脚本 → run_video_mme.sh 通过 |
| **OFFICIAL_DEMO_GATE** | 🔴 **NOT_RUN** | 官方 Demo = OpenBMB/MiniCPM-o-Demo，尚未实际接入（服务侧能力已验） | DEMO_VALIDATION_PLAN.md 12 用例全过 + 视频 |
| **OFFICIAL_PERFORMANCE_GATE** | 🔴 **NOT_RUN** | 逐 chunk RTF 采集管线已就绪（日志格式已含 RTF），待官方计时口径 | 官方口径下 chunk_rtf_summary.json 产出 |
| **OFFICIAL_REPRODUCTION_REVIEW** | 🔴 **NOT_RUN** | 复现审计模板已建（REPRODUCTION_AUDIT.md） | 干净环境从零复现成功 |
| **COMPETITION_COMPLETE** | 🔴 **NOT_CLAIMED** | 仅当上表全部 OFFICIAL_* 置位 | 全部完成 |

---

## 内部 PASS 证据索引（已固化）

| 证据 | 路径 |
|---|---|
| T6 冻结二进制回归（11/11） | `docs/f6-s13-closure/phase2/t6_integrated_regression.json`（binary_sha=db258375） |
| KV A/B 两条独立结论 | R13 canonical 30/30（`docs/f6-s13-closure/phase2/R13…`）+ 冻结 T6 28/30（t6_kv_ab_27of30.md） |
| Daily-Omni 内部 pilot | `docs/f6-s13-closure/phase2/daily_omni_pilot/PILOT_REPORT.md` |
| TTS KV guard 闭环 | `docs/f6-s13-closure/phase2/tts_boundary/tts_boundary_20260804_170049.json` |
| 复现构建 | REPRODUCIBLE_BINARY=PASS（bdd4550 两次重建 SHA 一致） |

---

## OFFICIAL_* 阻塞项清单（资产缺失）

| 资产 | 预期来源 | 阻塞的 Gate | 已准备的执行入口 | 资产到达后的第一条命令 |
|---|---|---|---|---|
| 官方 Starter Kit（接口/计时/子集/分母定义） | 赛事官方后续发布 | OFFICIAL_DAILY_OMNI / TTS_SEED / VIDEO_MME / PERFORMANCE | `submission/scripts/run_*.sh`（骨架已建） | `bash submission/scripts/run_daily_omni.sh` |
| Daily-Omni 官方评测脚本（当前 qa.json 为数据非官方评测链） | 官方 | OFFICIAL_DAILY_OMNI | run_daily_omni.sh | — |
| TTS-Seed 官方能力指标定义 | 官方 | OFFICIAL_TTS_SEED | run_tts_seed.sh | — |
| Video-MME 官方抽帧/答案解析 | 官方 | OFFICIAL_VIDEO_MME | run_video_mme.sh | — |
| OpenBMB/MiniCPM-o-Demo 前端接入 | GitHub（可拉取） | OFFICIAL_DEMO_GATE | start_demo.sh / demo_smoke.sh / DEMO_VIDEO_SCRIPT.md | `bash submission/scripts/start_demo.sh` |

---

## 决策规则（防伪造）

1. **不得**把内部 pilot / 内部 profiler / 冻结 T6 数字写成官方结果。
2. 任何 OFFICIAL_* 置位前必须有：官方脚本 + 原始输出 + 结果汇总 + 同一环境复现。
3. 精度对比必须是 baseline/candidate **同脚本同子集同分母**。
4. 状态变化一律写入 `docs/tracking/AUDIT.md`。
