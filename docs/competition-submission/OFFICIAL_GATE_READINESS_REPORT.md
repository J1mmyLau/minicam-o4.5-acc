# OFFICIAL_GATE_READINESS_REPORT（官方 Gate 就绪度核查报告）

> 生成：2026-08-05 · 状态：**OFFICIAL_GATE_WAITING**
> 本报告是对 `submission/` 提交包在官方资产到达前的就绪度核查，**不产生任何 OFFICIAL 成绩**。
> 与 `OFFICIAL_GATE_STATUS.md` 配套：后者是 Gate 判定状态页，本报告是"资产到达后第一步做什么"的执行准备页。

---

## 0. 固定版本口径（不得混用）

```text
LLAMA_CANDIDATE_SOURCE_COMMIT = bdd4550     # 真正参加 llama 子赛道的冻结源码
COMPETITION_DOCS_COMMIT       = 7a3f11e     # 比赛收口文档（competition-submission/ + submission/）
VLLM_MIGRATION_DOCS_COMMIT    = 37dc598     # vLLM 迁移文档对齐比赛约束层
FINAL_TRACKING_HEAD           = 379e2e6     # 最终跟踪文档 HEAD（不是候选源码版本）

server  SHA256 = db258375c3d2185ca2181da2a5c8f99a95d381413fcb7ab92a771850ba3a4a21
libomni SHA256 = c4b169376bced6bc3107cfda2f77abf35a634c1e146eed313a193e99e3739ea1
model   SHA256 = d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de
```

> **禁令**：`379e2e6` 仅作 FINAL_TRACKING_HEAD；任何地方不得把 `379e2e6` 写成候选源码版本。
> 参赛冻结源码永远是 `bdd4550`。

---

## 1. 七项就绪度核查结果

### 1.1 官方 Gate 脚本 dry-run 支持 — ⚠️ 部分就绪

| Gate 脚本 | 显式 dry-run | 当前安全行为 | 处置 |
|---|---|---|---|
| `run_daily_omni.sh` | 无 `--dry-run` | 无副作用 fail-fast：`OFFICIAL_SCRIPT` 未设 → exit 2 + BLOCKED 说明（**实测 exit=2，不起服务**） | 已核 |
| `run_tts_seed.sh` | 同上 | 同上（exit 2） | 已核 |
| `run_video_mme.sh` | 同上 | 同上（exit 2） | 已核 |
| `run_performance.sh` | 无 `DRY_RUN` | 会真实起服务跑 N 请求 | 待官方口径到达后加 `DRY_RUN=1` 预检模式 |

**结论**：当前阶段三份官方 Gate 脚本天然安全（官方脚本缺失即失败退出，绝不伪造/不空跑）。
显式 `--dry-run` 未实现 → **PENDING_FIX**：官方脚本接入时给每份脚本加 `--dry-run`（校验资产清单 + 打印将执行命令 + exit 0），避免官方机器上误触发。

### 1.2 资产 manifest（三 Benchmark + Demo + 模型 + 官方 Harness）

#### 数据资产（全部存在，指纹已固化）

| Benchmark | 路径 | git rev | 关键资产 | 指纹 |
|---|---|---|---|---|
| Daily-Omni | `/workspace/benchmarks/Daily-Omni/` | `ec5b57d` | `qa.json`（**1197 项**）、`qa_example.json`、`baseline/`（6 脚本）、`example_videos/`、`captioning.py`/`config.py` | qa.json SHA `306ade96…f9d4a`；qa_example SHA `c89de597…93d10` |
| TTS-Seed | `/workspace/benchmarks/seed-tts-eval/` | `752f429` | `run_wer.py`/`average_wer.py`/`cal_wer.sh`/`cal_sim.sh`/`get_wav_res_ref_text.py`/`prepare_ckpt.py`/`thirdparty/UniSpeech` | 数据子集/参考音频版本**待官方** |
| Video-MME | `/workspace/benchmarks/Video-MME/` | `06c2315` | `asset/`（图片）、`evaluation/output_test_template.json` | 视频子集/解码/抽帧策略**待官方** |

#### 运行资产

| 资产 | 状态 | 指纹 |
|---|---|---|
| 模型 `MiniCPM-o-4_5-F16.gguf` | ✅ 存在 | SHA `d1e69845…`（= 冻结模型，16.38 GB） |
| 冻结 server | ✅ 存在 | SHA `db258375…` |
| 冻结 libomni | ✅ 存在 | SHA `c4b16937…` |
| 官方 Demo `OpenBMB/MiniCPM-o-Demo` | ❌ **MISSING**（`/workspace/MiniCPM-o-Demo` 不存在） | 需 `git clone https://github.com/OpenBMB/MiniCPM-o-Demo` |
| 官方 Harness / Starter Kit | ❌ **BLOCKED** | `/workspace/llama.cpp-omni-official-eval/competition/`：METRIC_CONTRACT 全"待官方确认"，STARTER_KIT_CHECKLIST **0/45 确认** |

#### 官方口径待定项（METRIC_CONTRACT provisional）

TTFT 起点/终点、TTFP 判定（首完整 WAV vs 首帧）、chunk 语义（服务端帧/固定间隔/语义段）、预处理是否计入、样本数、排除规则、聚合方式、评分权重 —— **全部以 Starter Kit 为准**，到达前一律不填。

### 1.3 每个 Gate 资产到达后的第一条执行命令

> 原则：**先 baseline，后 candidate**；同脚本同子集同分母同统计。

| Gate | 触发资产 | 第一条命令（顺序执行） |
|---|---|---|
| Daily-Omni | 官方 Harness + 子集 + 口径确认 | `bash submission/environment/env_check.sh` → 核对 qa.json SHA `306ade96…` → `OFFICIAL_SCRIPT=<official.py> bash submission/scripts/run_daily_omni.sh baseline` → 复核输出 `daily_omni_baseline_raw.json` → 再跑 `candidate` → `daily_omni_comparison.json` |
| TTS-Seed | 官方能力指标（WER/SIM/音频有效性/RTF）+ 脚本 | 同上模式：`run_tts_seed.sh baseline` → `candidate` → 完整对比 |
| Video-MME | 官方子集/解码/抽帧/解析 + 脚本 | 同上模式：`run_video_mme.sh baseline` → `candidate` → `video_mme_comparison.json` |
| Demo | `MiniCPM-o-Demo` clone | `git clone https://github.com/OpenBMB/MiniCPM-o-Demo` → `DEMO_DIR=<clone> bash submission/scripts/start_demo.sh` → `demo_smoke.sh`（D1/D3/D10/D12 自动化段）→ D1–D12 全量（DEMO_VALIDATION_PLAN.md）→ 录像（DEMO_VIDEO_SCRIPT.md） |
| Performance（逐 chunk RTF） | 官方计时口径 | `bash submission/scripts/run_performance.sh`（N 调至 ≥30 有效 chunk）→ `chunk_rtf_summary.json`；官方口径到达后 `--dry-run` 预检 → 正式跑 |
| 复现 | 干净环境 | `REPRODUCTION_AUDIT.md` → `build.sh`（期望 SHA 复现 db258375/c4b16937）→ 从零重跑 S13 抽样 + chunk RTF |

### 1.4 baseline 与 candidate 同数据/同参数/同统计 — ✅ 设计就绪（执行 NOT_RUN）

- 三份 Gate 脚本强制 **同一 `OFFICIAL_SCRIPT`** 跑 `baseline` 与 `candidate` 两种 MODE，同一 `DATA`、同一 `OUT` 目录模式 → **同脚本同子集同分母**（脚本内已注明）。
- `benchmark.yaml`：`admission.max_accuracy_drop_pp: 2.0`、`compare_against: official_baseline`、`同脚本同子集同分母`。
- ⚠️ **缺口**：`run_performance.sh`（RTF 采集）当前只有 candidate 单模式，**无 baseline 二进制/配置入口**。官方 baseline 定义到达后需补 `MODE=baseline`（同一脚本对官方基线配置同跑）。→ **PENDING_FIX**。

### 1.5 逐 chunk RTF 不误用 request/Flow/HTTP 首包 — ✅ PASS（含内部 caveat）

- `analyze_chunk_rtf.py` 只解析 `T2W线程` 逐 chunk 行：`chunk_compute_ms` 取自日志 `inference`，`audio_duration_ms` 取自 `X.XXs audio` → **真·逐 chunk RTF**。
- 明确**不**使用：全请求 RTF / Flow 内部 RTF / Vocoder 内部 RTF / HTTP 首包延迟。
- 内置交叉核对：计算 RTF vs 日志打印 RTF（偏差 >0.02 报警）。
- 首/中/尾分桶（is_first_chunk / is_final_chunk=max idx per req）正确。
- ⚠️ **内部 caveat（记录，不影响正确性）**：`SAMPLE_RATE=24000` 硬编码（注释要求"以 wav 头核对"但未实现）；`valid_audio` 恒为 True → **排除率逻辑当前是桩**，`invalid_excluded_count` 恒为 0。即"排除率 ≤5%"规则目前不会被触发；真实无效音频检测（静音/解码失败）需在官方口径下实现。→ **PENDING_FIX**。

### 1.6 submission 无 /tmp / 私有路径 / 未提交文件 — ⚠️ 基本干净，2 处 WARN

- ✅ `/tmp`：无硬依赖。KV cache 默认落 `results/<run_id>/kv_cache`（server.env + start_server.sh 均注明"避免 /tmp 依赖"）。
- ✅ 未提交文件：`git status` worktree clean，`submission/` 全部已提交（7a3f11e）。
- ⚠️ **WARN-1**：`MODEL_PATH` 默认 `/workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf`（server.env:6 / env_check.sh:32）——机器私有绝对路径作默认值，可被 env 覆盖且有 env_check 守护，但官方机器上默认值不适用。
- ⚠️ **WARN-2**：`DEMO_DIR` 默认 `/workspace/MiniCPM-o-Demo`（start_demo.sh:7）——同上。
- **处置**：官方资产到达时，路径改为"默认空 + 必填校验"或经 `env_check.sh` 显式要求，避免私有绝对路径进入提交默认值。→ **PENDING_FIX**。

### 1.7 输出本报告 — ✅ 完成

本报告即第 7 项交付。所有未执行结果保持 `NOT_RUN`；本报告**不含任何模拟结果、占位成绩或推测精度**。

---

## 2. 口径守住清单（持续有效）

1. **`INTERNAL_VALIDATION_POLICY`**：样本下限 ≥30 有效 chunk、排除率 ≤5%、首/中/尾分桶、有效判定 —— 均为**内部统计规范**，非 OFFICIAL_REQUIREMENT。官方样本数/排除规则/聚合/权重以 Starter Kit 为准（`VLLM_METRIC_MEASUREMENT_SPEC.md` §5 已显式标注）。
2. **`LLAMA_CONFIRMED`**：`RTF=0.23` / `decode_to_first_audio=1269ms` / `wav_count=12` 为 llama 冻结日志**内部参考值**，仅用于历史候选说明/埋点示例/vLLM 假设来源；**不得**用作官方 llama 成绩、vLLM baseline 或 vLLM 优化收益。
3. **禁止冒充**：request RTF / Flow RTF / HTTP 首包 ≠ chunk RTF；内部 pilot ≠ 官方 Gate；llama 数字 ≠ vLLM 结果。

---

## 3. PENDING_FIX 汇总（官方资产到达后、正式执行前处理）

| # | 项 | 现况 | 修复 |
|---|---|---|---|
| P1 | Gate 脚本显式 dry-run | 三份 Gate 脚本天然 fail-fast，但无 `--dry-run` | 接入官方脚本时加 `--dry-run`（校验资产+打印命令+exit 0） |
| P2 | RTF baseline 入口 | `run_performance.sh` 只有 candidate | 加 `MODE=baseline`，同一脚本对官方基线配置同跑 |
| P3 | chunk RTF 排除率逻辑 | `valid_audio` 恒 True，排除率规则未被触发 | 官方口径下实现真实无效检测（静音/解码失败/空包） |
| P4 | 私有绝对路径默认值 | MODEL_PATH / DEMO_DIR 默认 `/workspace/...` | 默认空 + 必填校验，或经 env_check 显式要求 |

> P1–P4 均为**提交包卫生/就绪性**改进，不涉及冻结源码 `bdd4550`，不产生任何优化候选。
