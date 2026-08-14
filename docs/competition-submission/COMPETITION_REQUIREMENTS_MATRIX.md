# 比赛需求矩阵（赛道一 · llama.cpp-omni 子赛道 A）

> 依据最新官方赛事规则整理。本文是**需求侧全景**：官方要求 → 适用子赛道 → 当前状态 → 已有/缺失证据 → 执行入口 → 通过标准 → 最终产物。
> 状态标签**只允许 5 种**，禁止混用：
> `INTERNAL_PASS` / `OFFICIAL_PENDING` / `BLOCKED_BY_ASSET` / `OFFICIAL_PASS` / `NOT_APPLICABLE`
>
> 候选口径（冻结，2026-08-14）：
> - `TESTED_RUNTIME_COMMIT=fd3dd36`（真正跑出数据的 runtime，tag `competition-final-20260814`）
> - `FINAL_SUBMISSION_COMMIT=16ec3500d`（提交文档包，tag `competition-submission-20260814`，branch `competition/final-ascend-track-a`）
> - server `4694cb58…` / libomni `3f3e1e63…` / model `d1e69845…`
> - `COMPETITION_COMPLETE=NOT_CLAIMED`

---

## 0. 比赛主线（提炼自规则）

```
框架与单卡环境 → 三项 Benchmark 精度准入 → 官方 Demo 可用 → 官方 chunk RTF 性能 → 工程复现审查
```

llama 子赛道**核心排名指标只有一项：per-audio-chunk RTF**。TTFT/TTFP 是体验分析指标，不是 llama 子赛道公开排名指标。
精度准入相对**对应框架官方基线**，不是 llama 与 vLLM 互比。

---

## 1. 框架与环境（第一步）

| 官方要求 | 适用子赛道 | 当前状态 | 已有证据 | 缺失证据 | 执行入口 | 通过标准 | 阻塞项 | 最终产物 |
|---|---|---|---|---|---|---|---|---|
| 指定框架 llama.cpp-omni | A | `INTERNAL_PASS` | 全链路在 llama.cpp-omni 完成 | — | — | 框架正确即满足 | 无 | VERSION_MANIFEST.md |
| 单卡 910C（统一评测硬件） | A+B | `INTERNAL_PASS` | R13_HARDWARE=1×Ascend 910C dual-die（2× Ascend910 芯片，单卡合规） | 提交材料中保存完整 `npu-smi` 输出 | environment/env_check.sh | npu-smi 与声明一致 | 无 | system_info.txt |
| 镜像 CANN 9.1.0-beta.1 | A | `INTERNAL_PASS` | env-cann91.sh + ASCEND_HOME_PATH 验证 | 环境安装/验证脚本进提交包 | environment/env_check.sh | `ASCEND_HOME_PATH` / `ASCEND_OPP_PATH` 正确 | 无 | env_check.sh 输出 |
| 固定仓库/分支/commit | A | `INTERNAL_PASS` | source `fd3dd36`、branch `competition/final-ascend-track-a` | 复现审查时 checkout 同一 commit | REPRODUCTION_AUDIT.md | 复现 checkout 成功 | 无 | VERSION_MANIFEST.md |

## 2. 三项 Benchmark 精度准入（第二步，P0）

> 官方要求：优化版相对官方基线降幅 ≤ 2 个百分点（85%→≥83%，70%→≥68%）。同脚本、同子集、同分母对比。
> **现状：四项精度指标均 PASS（三个 Benchmark，统一评测分支）**。统一评测分支 `tc-mb/llama.cpp-omni`（`bench/huawei`）
> 已到达，官方脚本上跑通全量：Daily-Omni 79.43%（950/1196）≥77.5% +1.93pp · Video-MME 69.8% ≥67.0% +2.8pp ·
> Seed-TTS WER 1.422% ≤1.56% + SIM 0.969 ≥0.689（2020/2020，0 NaN）。隐藏测试集公开后同脚本复核分母。

| 官方要求 | 当前状态 | 已有证据 | 缺失证据 | 执行入口 | 通过标准 | 阻塞项 | 最终产物 |
|---|---|---|---|---|---|---|---|
| Daily-Omni 官方精度 | `PASS（准确率）` | 全量 79.43%（950/1196）≥77.5%，+1.93pp | 官方隐藏测试集（公开后复核分母） | run_daily_omni.sh | candidate ≥ baseline − 2pp | 无（隐藏集属正常） | daily_omni_comparison.json + DAILY_OMNI_REPORT.md |
| TTS-Seed 官方结果 | `PASS（准确率）` | 全量 WER 1.422% ≤1.56% / SIM 0.969 ≥0.689（2020/2020，0 NaN） | 官方隐藏测试集（公开后复核分母） | run_tts_seed.sh | 官方口径判定 | 无（隐藏集属正常） | tts_seed_comparison.json + TTS_SEED_REPORT.md |
| Video-MME 官方结果 | `PASS（准确率）` | 全量 69.8% ≥67.0%，+2.8pp | 官方隐藏测试集（公开后复核分母） | run_video_mme.sh | 官方口径判定 | 无（隐藏集属正常） | video_mme_comparison.json + VIDEO_MME_REPORT.md |
| 精度降幅 ≤ 2pp | `PASS` | 四项均优于官方阈值（见上） | 官方隐藏测试集复核 | 三个 run_*.sh | 全项 ≤ 2pp 且无核心能力异常 | 无 | 三个 comparison.json |

## 3. 官方 Demo 可用（第三步，P0）

> llama 子赛道接入 `OpenBMB/MiniCPM-o-Demo`。主办方检查：服务启动 / Demo 连接 / 文本-音频-视频输入 / 输出完整 / 音频连续 / 卡顿中断崩溃 / 连续交互稳定 / 完整交互流程。

| 官方要求 | 当前状态 | 已有证据 | 缺失证据 | 执行入口 | 通过标准 | 阻塞项 | 最终产物 |
|---|---|---|---|---|---|---|---|
| 服务冷启动 | `INTERNAL_PASS` | T6 Restart 3 会话 + Smoke 5/5 | — | start_server.sh | 启动成功 + health OK | 无 | — |
| Demo 连接与多模态输入 | `INTERNAL_PASS`（服务侧） | T10 pilot：图像+音频+文本输入 CONFIRMED；SSE 文本+[DONE]；常驻上下文第 2 次请求 OK | **官方 Demo 前端实际接入** | start_demo.sh / demo_smoke.sh | 12 用例全过 | 官方 Demo 仓库可拉取 | DEMO_GUIDE.md |
| 流式语音连续性 | `INTERNAL_PASS` | T6 Voice 5/5 + Disconnect 5/5 + followup | Demo 场景长稳录像（10 分钟） | demo_smoke.sh | 无卡顿/中断/崩溃 | 无 | 演示视频 |
| 连续运行稳定 | `INTERNAL_PASS` | T6 11/11 GATES；0 cpu_fallback/0 cann_error | Demo 场景 10min 连续运行录像 | DEMO_VALIDATION_PLAN.md | 录像无异常退出 | 无 | DEMO_VIDEO_SCRIPT.md |

## 4. 核心性能：chunk RTF（第四步，P0）

| 官方要求 | 当前状态 | 已有证据 | 缺失证据 | 执行入口 | 通过标准 | 阻塞项 | 最终产物 |
|---|---|---|---|---|---|---|---|
| per-audio-chunk RTF | `AVAILABLE（1.09–1.17）` | `stage_timing.jsonl` + SSE `metrics` 已发射；2 次独立运行 n_speak 0→33、0 拒绝，`core.rtf_aggregate` 1.09–1.17（parity baseline 1.087） | 无已证实加速（诚实口径，见 `F6_OFFICIAL_RTF_RESOLVED.md`） | run_performance.sh + analyze_chunk_rtf.py | 官方口径通过 | 无 | chunk_rtf_raw.csv + chunk_rtf_summary.json |
| 不得用全请求 RTF / Flow 内部 / Vocoder 内部 RTF 代替 | — | 规范已定（见 CHUNK_RTF_MEASUREMENT_SPEC.md） | 官方口径 | — | 报告按逐 chunk 统计 | 无 | PERFORMANCE_REPORT.md |

## 5. 工程复现审查（第五步）

| 官方要求 | 当前状态 | 已有证据 | 缺失证据 | 执行入口 | 通过标准 | 阻塞项 | 最终产物 |
|---|---|---|---|---|---|---|---|
| 源码 checkout + 构建 + 启动可复现 | `INTERNAL_PASS`（构建侧） | REPRODUCIBLE_BINARY=PASS（两次干净重建 SHA 一致） | 干净环境从零复现时间线 | REPRODUCTION_AUDIT.md | 一条命令从 checkout 到启动成功 | 官方环境与本地一致 | REPRODUCTION_GUIDE.md |
| 提交包完整（代码/配置/脚本/结果/视频/报告） | `OFFICIAL_PENDING` | submission/ 骨架已建 | 官方结果回填 | FINAL_SUBMISSION_CHECKLIST.md | 清单全勾 | 官方 Gate 通过后 | submission/ 完整包 |

## 6. 明确 NOT_APPLICABLE / 边界

| 要求 | 说明 |
|---|---|
| vLLM-Omni 相关（TTFT/TTFP/PR 加分/minicpm-challenge 分支） | `NOT_APPLICABLE`——属子赛道 B，见 `docs/vllm-migration/VLLM_COMPETITION_REQUIREMENTS.md` |
| 双 Demo 兼容 | `NOT_APPLICABLE`——规则明确只需完成所报子赛道对应 Demo |

---

## 7. 当前正式口径（唯一权威）

```
POST_T11_SOURCE_FREEZE            = PASS
POST_T11_FINAL_CANDIDATE          = FINAL_INTERNAL
T6_FROZEN_BINARY_REGRESSION       = PASS（11/11）
DAILY_OMNI_INTERNAL_PILOT         = PASS（服务器链；非官方准确率）
REPRODUCIBLE_BINARY               = PASS

OFFICIAL_DAILY_OMNI               = PASS（准确率 79.43% ≥ 77.5% +1.93pp）
OFFICIAL_TTS_SEED                 = PASS（准确率 WER 1.422% ≤ 1.56% / SIM 0.969 ≥ 0.689）
OFFICIAL_VIDEO_MME                = PASS（准确率 69.8% ≥ 67.0% +2.8pp）
OFFICIAL_DEMO_GATE                = NOT_RUN（官方 Demo 前端未接入）
OFFICIAL_PERFORMANCE_GATE         = AVAILABLE（1.09–1.17，parity baseline 1.087，无已证实加速）
OFFICIAL_REPRODUCTION_REVIEW      = NOT_RUN

COMPETITION_COMPLETE              = NOT_CLAIMED
```

> 统一评测分支 `tc-mb/llama.cpp-omni`（`bench/huawei`）已到达（`OFFICIAL_UNIFIED_EVAL_BRANCH=AVAILABLE`，
> `STARTER_KIT_BLOCKER=REMOVE`）。四项精度指标已在其官方脚本上跑通全量；隐藏测试集公开后同脚本复核分母。
> RTF 已可用（1.09–1.17，parity baseline 1.087，无已证实加速），根因 LISTEN-wedge 生命周期修复见 `docs/F6_OFFICIAL_RTF_RESOLVED.md`。
