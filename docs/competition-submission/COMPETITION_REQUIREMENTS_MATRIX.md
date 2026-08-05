# 比赛需求矩阵（赛道一 · llama.cpp-omni 子赛道 A）

> 依据最新官方赛事规则整理。本文是**需求侧全景**：官方要求 → 适用子赛道 → 当前状态 → 已有/缺失证据 → 执行入口 → 通过标准 → 最终产物。
> 状态标签**只允许 5 种**，禁止混用：
> `INTERNAL_PASS` / `OFFICIAL_PENDING` / `BLOCKED_BY_ASSET` / `OFFICIAL_PASS` / `NOT_APPLICABLE`
>
> 候选口径（冻结，2026-08-05）：
> - `CANDIDATE_SOURCE_COMMIT=bdd4550`（比赛候选源码）
> - `EVIDENCE_DOCS_COMMIT=adb9bb6`（+ d5cc978 + f26323f 证据文档提交）
> - server `db258375…` / libomni `c4b16937…` / model `d1e69845…`
> - `POST_T11_FINAL_CANDIDATE=FINAL_INTERNAL`，`COMPETITION_COMPLETE=NOT_CLAIMED`

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
| 固定仓库/分支/commit | A | `INTERNAL_PASS` | source `bdd4550`、branch `perf/f6-decode-to-speak` | 复现审查时 checkout 同一 commit | REPRODUCTION_AUDIT.md | 复现 checkout 成功 | 无 | VERSION_MANIFEST.md |

## 2. 三项 Benchmark 精度准入（第二步，P0）

> 官方要求：优化版相对官方基线降幅 ≤ 2 个百分点（85%→≥83%，70%→≥68%）。同脚本、同子集、同分母对比。
> **现状：三个 Benchmark 官方结果均 NOT_RUN**。数据资产已在 `/workspace/benchmarks/`，但官方 Harness / 计时口径 / 子集定义未定（official-eval competition 45 项 starter kit 核对清单 0/45 已确认，METRIC_CONTRACT 全部"待官方确认"）。

| 官方要求 | 当前状态 | 已有证据 | 缺失证据 | 执行入口 | 通过标准 | 阻塞项 | 最终产物 |
|---|---|---|---|---|---|---|---|
| Daily-Omni 官方精度 | `BLOCKED_BY_ASSET` | 内部 pilot PASS（服务器链 6/6 门；9 题 pilot，whisper 上限 29.5s→"?" 已文档化）——**不是官方准确率** | 官方 Harness + 官方子集 + 计时口径 | run_daily_omni.sh | candidate ≥ baseline − 2pp | 官方 starter kit | daily_omni_comparison.json + DAILY_OMNI_REPORT.md |
| TTS-Seed 官方结果 | `BLOCKED_BY_ASSET` | 数据目录存在；内部 CANN T2W 性能证据 | 官方能力指标（WER/SIM/音频有效性/RTF）+ 官方脚本 | run_tts_seed.sh | 官方口径判定 | 官方 starter kit + 指标定义 | tts_seed_comparison.json + TTS_SEED_REPORT.md |
| Video-MME 官方结果 | `BLOCKED_BY_ASSET` | 数据目录存在；输入侧媒体协议 CONFIRMED（两次 prefill） | 官方子集/解码/抽帧/答案解析 | run_video_mme.sh | 官方口径判定 | 官方 starter kit | video_mme_comparison.json + VIDEO_MME_REPORT.md |
| 精度降幅 ≤ 2pp | `OFFICIAL_PENDING` | — | 三项官方 baseline+candidate 同脚本对比 | 三个 run_*.sh | 全项 ≤ 2pp 且无核心能力异常 | 同上 | 三个 comparison.json |

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
| per-audio-chunk RTF | `INTERNAL_PASS`（测量基础已就绪） | **冻结二进制日志已逐 chunk 打印 RTF**：`T2W线程: wav_1002.wav | 1.00s audio | 232.4ms inference | RTF=0.23 | …` | 官方计时口径确认后按官方定义重测 | run_performance.sh + analyze_chunk_rtf.py | 官方口径通过 | 官方 starter kit 计时定义 | chunk_rtf_raw.csv + chunk_rtf_summary.json |
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

OFFICIAL_DAILY_OMNI               = NOT_RUN  （BLOCKED_BY_OFFICIAL_STARTER_KIT）
OFFICIAL_TTS_SEED                 = NOT_RUN
OFFICIAL_VIDEO_MME                = NOT_RUN
OFFICIAL_DEMO_GATE                = NOT_RUN
OFFICIAL_PERFORMANCE_GATE         = NOT_RUN
OFFICIAL_REPRODUCTION_REVIEW      = NOT_RUN

COMPETITION_COMPLETE              = NOT_CLAIMED
```

> 任何一项 OFFICIAL_* 只有在官方 Harness/Starter Kit 到达并按其口径执行后，才允许置位。
