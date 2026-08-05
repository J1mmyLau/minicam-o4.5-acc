# Benchmark 执行计划（三项官方 Benchmark）

> 目标：Daily-Omni / TTS-Seed / Video-MME 三项，每项产出 **baseline vs candidate** 同脚本同子集对比。
> 当前全部 `BLOCKED_BY_OFFICIAL_STARTER_KIT`（官方 Harness 与计时口径未定），本文给出**数据现状、内部 pilot 保留、官方执行入口**。
> 数据资产：`/workspace/benchmarks/Daily-Omni/`（qa.json 1197 项）、`/workspace/benchmarks/seed-tts-eval/`、`/workspace/benchmarks/Video-MME/`、`/workspace/llama.cpp-omni-official-eval/competition/`（provisional infra）。

---

## 通用准入判定（三个 Benchmark 共用）

```
candidate_accuracy >= baseline_accuracy - 2 percentage points
```

同时检查（任一触发即视为不合格，需说明）：
- 核心能力明显下降 / 输出异常 / 空输出 / 不可解析输出
- Benchmark 无法完成（HTTP 失败、服务崩溃、超时）
- 模型行为被修改导致结果失去可比性

分母口径：官方脚本定义；未定义前**不得**自行假设。

---

## 1. Daily-Omni

### 数据与资产现状
| 项 | 状态 |
|---|---|
| 数据 | `/workspace/benchmarks/Daily-Omni/`：qa.json（1197 项）、example_videos、example_metadata.csv、assets、baseline/ |
| 官方评测脚本 | ❌ 未定（provisional infra 在 official-eval/competition/，45 项 starter kit 清单 0/45 确认） |
| 官方 prompt / 答案提取 / A-D 解析 | ❌ 未定（内部 pilot 用 extract_choice_letter，非官方） |

### 内部 pilot（保留为证据，**不是官方准确率**）
- 证据：`docs/f6-s13-closure/phase2/daily_omni_pilot/PILOT_REPORT.md`
- 9 项 QA（3 视频 × 3 例，4 case 类型），官方单消息协议（frame+audio+question），media_type=2 / use_tts=False，两次 prefill 媒体协议。
- 服务器链 6/6 门 PASS；P0 修复 3 项已纳入候选源码。
- 模型能力边界：whisper 编码上限 ~24-26s，29.5s 官方音频 → `?`×256（**属模型限制，非服务器 bug**，需在报告中说明）。

### 官方执行入口（starter kit 到达后）
1. 确认：官方数据版本 / 官方子集 / image-audio-video packing / 两次 prefill 协议 / 官方 prompt / 答案提取 / A-D 解析 / HTTP 失败分母 / 媒体 token 信息 / whisper 输入上限 / 视频长度分桶。
2. 命令：`bash submission/scripts/run_daily_omni.sh <baseline|candidate> <subset>`。
3. 输出：`daily_omni_baseline_raw.json` / `daily_omni_candidate_raw.json` / `daily_omni_comparison.json` / `DAILY_OMNI_REPORT.md`。

### 报告必含
baseline accuracy · candidate accuracy · 绝对降幅（percentage points）· HTTP 失败数 · 解析失败数 · 排除项 · 分类别 accuracy · 长度分桶 · 已知限制（whisper 上限）。

---

## 2. TTS-Seed

### 数据与资产现状
| 项 | 状态 |
|---|---|
| 数据 | `/workspace/benchmarks/seed-tts-eval/`（存在） |
| 官方能力指标 | ❌ 未定。不得根据内部文档猜测最终官方指标；可能含 WER / SIM / 音频有效性 / RTF，以官方为准 |

### 官方执行入口（starter kit 到达后）
1. 确认：reference audio 校验 / 输入文本校验 / 输出 WAV 校验（采样率、声道、时长）/ 空音频检测 / NaN/Inf 检测 / WER-SIM 依赖 / 失败样本保存。
2. 命令：`bash submission/scripts/run_tts_seed.sh <baseline|candidate>`。
3. 输出：baseline vs candidate 完整对比 + **逐 chunk RTF raw 数据**（供性能报告）。

---

## 3. Video-MME

### 数据与资产现状
| 项 | 状态 |
|---|---|
| 数据 | `/workspace/benchmarks/Video-MME/`（存在） |
| 官方抽帧/解码/答案解析 | ❌ 未定 |

### 官方执行入口（starter kit 到达后）
1. 确认：官方数据子集 / 视频解码方式 / 抽帧策略 / 音频是否参与 / prompt 模板 / 最大帧数 / 最大音频长度 / 答案解析 / 分母口径。
2. 优先验证分桶：短视频 / 长视频 / 有音频 / 无音频 / 多轮 / 输入上限。
3. 命令：`bash submission/scripts/run_video_mme.sh <baseline|candidate>`。
4. 输出：`video_mme_baseline_raw.json` / `video_mme_candidate_raw.json` / `video_mme_comparison.json` / `VIDEO_MME_REPORT.md`。

---

## 执行顺序与纪律

1. **先 baseline 后 candidate**（同一服务器配置、同一数据、同一脚本、同一环境变量）。
2. 每次 run 记录 run_id + 完整命令 + 环境（VERSION_MANIFEST.md）。
3. 原始输出落 `submission/benchmark_results/{baseline,candidate}/`，禁止只存汇总。
4. 官方 Gate 未到前，三项均保持 `BLOCKED_BY_OFFICIAL_STARTER_KIT`；内部数据只作 pipeline 验证。
5. 失败请求处理规则按官方脚本；官方未定义时标记 `EXCLUDED_UNCONFIRMED`，绝不静默丢弃。
