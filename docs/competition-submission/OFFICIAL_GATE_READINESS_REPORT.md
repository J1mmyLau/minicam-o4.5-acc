# OFFICIAL_GATE_READINESS_REPORT（官方 Gate 就绪度核查报告）

> 生成：2026-08-05 · 状态：**OFFICIAL_GATE_TOOLING_READINESS=PASS**（工具链就绪；官方 Gate 仍 BLOCKED_BY_OFFICIAL_STARTER_KIT）
> 就绪度标签：DRY_RUN_SUPPORT=PASS / BASELINE_CANDIDATE_SYMMETRY=PASS / CHUNK_AUDIO_VALIDATION=PASS /
> PRIVATE_PATH_AUDIT=PASS / LOCAL_ASSET_MANIFEST=PASS / OFFICIAL_ASSET_VERSION_MATCH=PENDING_STARTER_KIT / OFFICIAL_GATES=BLOCKED_BY_OFFICIAL_STARTER_KIT
> 本报告是对 `submission/` 提交包在官方资产到达前的就绪度核查，**不产生任何 OFFICIAL 成绩**。
> 与 `OFFICIAL_GATE_STATUS.md` 配套：后者是 Gate 判定状态页，本报告是"资产到达后第一步做什么"的执行准备页。
> 工具链离线自检命令与结果见 `OFFICIAL_GATE_TOOLING_SELFTEST.md`。

---

## 0. 固定版本口径（不得混用）

```text
LLAMA_CANDIDATE_SOURCE_COMMIT = bdd4550     # 真正参加 llama 子赛道的冻结源码
COMPETITION_DOCS_COMMIT       = 7a3f11e     # 比赛收口文档（competition-submission/ + submission/）
VLLM_MIGRATION_DOCS_COMMIT    = 37dc598     # vLLM 迁移文档对齐比赛约束层
FINAL_TRACKING_HEAD           = c328d1b     # 最终跟踪文档 HEAD（不是候选源码版本）

server  SHA256 = db258375c3d2185ca2181da2a5c8f99a95d381413fcb7ab92a771850ba3a4a21
libomni SHA256 = c4b169376bced6bc3107cfda2f77abf35a634c1e146eed313a193e99e3739ea1
model   SHA256 = d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de
```

> **禁令**：`c328d1b`（及任何文档 HEAD）仅作 FINAL_TRACKING_HEAD；任何地方不得把文档 HEAD 写成候选源码版本。
> 参赛冻结源码永远是 `bdd4550`。
> **资产版本标签**：当前 commit/SHA 只叫 **CURRENT_LOCAL_ASSET_SNAPSHOT**；`OFFICIAL_ASSET_VERSION_MATCH=PENDING_STARTER_KIT`（官方 starter kit 到达并核对后方可称 CONFIRMED，本报告不称 CONFIRMED）。

---

## 1. 七项就绪度核查结果

### 1.1 官方 Gate 脚本 dry-run 支持 — ✅ PASS

| Gate 脚本 | 显式 dry-run | 返回码 | 无副作用 |
|---|---|---|---|
| `run_daily_omni.sh` | `--dry-run`/`-n` | 0=就绪 / 2=缺官方资产或 Harness / 3=配置非法 / 4=baseline/candidate 不对称 | 不起服务 / 不占 NPU / 不发请求 / 不落成绩（仅打印 MODE/路径/命令/OUT/缺失资产） |
| `run_tts_seed.sh` | 同上 | 同上 | 同上 |
| `run_video_mme.sh` | 同上 | 同上 | 同上 |
| `run_performance.sh` | `--dry-run`/`-n` | 0=就绪 / 2=缺资产 / 3=配置非法（含 baseline 未给 BASELINE_SERVER_BIN）/ 4=不对称 | 同上 |

**实测**：缺官方 Harness → 全 exit 2（`OFFICIAL_SCRIPT` 未设即失败，绝不伪造）；资产齐全 candidate dry-run → exit 0 并打印完整 server/benchmark/analyze 命令。全部 dry-run 命令与结果记录在 `OFFICIAL_GATE_TOOLING_SELFTEST.md`。

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
| Performance（逐 chunk RTF） | 官方计时口径 | 先 `bash submission/scripts/run_performance.sh --dry-run`（预检 exit 0）→ `MODE=baseline bash submission/scripts/run_performance.sh`（N 调至 ≥30 有效 chunk）→ 同 RUN_ID 跑 `candidate` → `check_baseline_candidate_symmetry.py`（不对称退出非零）→ `chunk_rtf_summary.json` |
| 复现 | 干净环境 | `REPRODUCTION_AUDIT.md` → `build.sh`（期望 SHA 复现 db258375/c4b16937）→ 从零重跑 S13 抽样 + chunk RTF |

### 1.4 baseline 与 candidate 同数据/同参数/同统计 — ✅ PASS（执行 NOT_RUN）

- 三份 Gate 脚本强制 **同一 `OFFICIAL_SCRIPT`** 跑 `baseline` 与 `candidate` 两种 MODE，同一 `DATA`、同一 `OUT` 目录模式 → **同脚本同子集同分母**（脚本内已注明）。
- `benchmark.yaml`：`admission.max_accuracy_drop_pp: 2.0`、`compare_against: official_baseline`、`同脚本同子集同分母`。
- ✅ **RTF 采集入口已补齐**：`run_performance.sh` 支持 `MODE=baseline|candidate`，同一 runner/数据 manifest/请求顺序/seed/warmup/measured count/chunk parser/valid_audio/统计脚本；仅通过 MODE 切换二进制配置（baseline 必须显式 `BASELINE_SERVER_BIN`）。输出隔离到 `${OUTPUT_ROOT}/<run_id>/<mode>/`，每次落 `manifest.json`（resolved config / 完整启动命令 / 完整 benchmark 命令 / source commit / binary SHA / model SHA / data SHA / env）。
- ✅ **对称性检查**：`check_baseline_candidate_symmetry.py <run_dir>` 比对 dataset SHA / case count / request IDs / sampling config(seed/warmup/N/sample_rate) / model / prompt(text_dir+data_sha) / 统计代码 SHA / port，任一不一致退出非零（fixture 实测 matching=0 / mismatched=1 / missing=2）。

### 1.5 逐 chunk RTF 不误用 request/Flow/HTTP 首包 — ✅ PASS（含内部 caveat）

- `analyze_chunk_rtf.py` 只解析 `T2W线程` 逐 chunk 行：`chunk_compute_ms` 取自日志 `inference`，`audio_duration_ms` 取自 `X.XXs audio` → **真·逐 chunk RTF**。
- 明确**不**使用：全请求 RTF / Flow 内部 RTF / Vocoder 内部 RTF / HTTP 首包延迟。
- 内置交叉核对：计算 RTF vs 日志打印 RTF（偏差 >0.02 报警）。
- 首/中/尾分桶（is_first_chunk / is_final_chunk=max idx per (req,gen)）正确。
- ✅ **valid_audio 真实判定已实现**（`analyze_chunk_rtf.py::validate_chunk`）：逐 chunk 校验 payload 非空、sample_count>0、sample_rate>0 且∈{24000}、audio_duration_ms>0、PCM/WAV 可解析（存在时 `wave` 模块跨查）、无 NaN/Inf、request_id 存在、chunk_index 存在、时间戳合法（compute>=0、t/queue_wait 非 NaN/Inf）、(req,gen,chunk_index) 不重复、尾 chunk 未截断。排除原因枚举：`EMPTY_PAYLOAD / ZERO_SAMPLES / INVALID_SAMPLE_RATE / DECODE_FAILURE / NAN_INF / MISSING_REQUEST_ID / MISSING_CHUNK_INDEX / INVALID_TIMESTAMP / DUPLICATE_CHUNK / TRUNCATED_CHUNK`。无效 chunk 记录 `valid_audio=false + exclusion_reason + request_id + chunk_index + raw source line`。
- ✅ **统计**：summary 输出 chunks_total / chunks_valid / chunks_invalid / exclusion_rate / 各排除原因计数。**排除率 ≤5% 与样本下限仍标记 INTERNAL_VALIDATION_POLICY，不是官方要求**。
- ✅ **离线验证**：冻结 T6 日志（db258375）实测 329 chunk 全 valid、exclusion_rate=0.0、p50=0.2784；10 种排除原因 + WAV fixture + `--warmup` CLI 单测 21 例全过（`submission/tests/test_analyze_chunk_rtf.py`）。

### 1.6 submission 无 /tmp / 私有路径 / 未提交文件 — ✅ PASS

- ✅ `/tmp`：无硬依赖。KV cache 默认落 `${OUTPUT_ROOT}/<run_id>/kv_cache`（`OUTPUT_ROOT` 默认 `${REPO_ROOT}/submission_runs`，绝不用 /tmp）。
- ✅ 未提交文件：提交前 `git status` worktree clean，本次只提交脚本/测试/就绪度文档。
- ✅ **私有默认路径已清除**：`server.env` `MODEL_PATH` 改为"默认空 + 必填校验"（start_server.sh / env_check.sh / run_performance.sh 缺失即明确报错退出）；`DEMO_DIR` 默认 `${REPO_ROOT}/third_party/MiniCPM-o-Demo`。统一定义 `REPO_ROOT / MODEL_PATH / DATA_ROOT / DEMO_DIR / OUTPUT_ROOT / OFFICIAL_HARNESS_ROOT`，全部默认从 REPO_ROOT 派生（无 `/workspace`、`/home`、`/tmp` 字面量）。
- ✅ **审计**：`submission/tests/check_no_private_paths.py` 扫描 submission/ 代码行，无 `/workspace/`、`/home/`、`/tmp/` 字面量（PASS）；docs 仅 warn（允许示例路径）。

### 1.7 输出本报告 — ✅ 完成

本报告即第 7 项交付。所有未执行结果保持 `NOT_RUN`；本报告**不含任何模拟结果、占位成绩或推测精度**。

---

## 2. 口径守住清单（持续有效）

1. **`INTERNAL_VALIDATION_POLICY`**：样本下限 ≥30 有效 chunk、排除率 ≤5%、首/中/尾分桶、有效判定 —— 均为**内部统计规范**，非 OFFICIAL_REQUIREMENT。官方样本数/排除规则/聚合/权重以 Starter Kit 为准（`VLLM_METRIC_MEASUREMENT_SPEC.md` §5 已显式标注）。
2. **`LLAMA_CONFIRMED`**：`RTF=0.23` / `decode_to_first_audio=1269ms` / `wav_count=12` 为 llama 冻结日志**内部参考值**，仅用于历史候选说明/埋点示例/vLLM 假设来源；**不得**用作官方 llama 成绩、vLLM baseline 或 vLLM 优化收益。
3. **禁止冒充**：request RTF / Flow RTF / HTTP 首包 ≠ chunk RTF；内部 pilot ≠ 官方 Gate；llama 数字 ≠ vLLM 结果。

---

## 3. PENDING_FIX → RESOLVED（2026-08-05 工具链收口提交）

| # | 项 | 结论 | 落点 |
|---|---|---|---|
| P1 | Gate 脚本显式 dry-run | ✅ **RESOLVED** | 3 份 Gate 脚本 + `run_performance.sh` 均支持 `--dry-run`，返回码 0/2/3/4 |
| P2 | RTF baseline 入口 | ✅ **RESOLVED** | `run_performance.sh MODE=baseline\|candidate` + 输出隔离 + `manifest.json` + `check_baseline_candidate_symmetry.py` |
| P3 | chunk RTF 排除率逻辑 | ✅ **RESOLVED** | `valid_audio` 真实判定（10 排除原因枚举）+ total/valid/invalid/exclusion_rate/reason counts + 单测 21 例 |
| P4 | 私有绝对路径默认值 | ✅ **RESOLVED** | MODEL_PATH 必填无默认；DEMO_DIR/OUTPUT_ROOT/DATA_ROOT/OFFICIAL_HARNESS_ROOT 从 REPO_ROOT 派生 |

> P1–P4 均为**提交包卫生/就绪性**改进，不涉及冻结源码 `bdd4550`，不产生任何优化候选。
> 离线自检全绿：`submission/tests/run_selftest.sh` → **14/14 PASS**（命令与结果见 `OFFICIAL_GATE_TOOLING_SELFTEST.md`）。
> 工具链就绪状态：**OFFICIAL_GATE_TOOLING_READINESS=PASS**；官方 Gate 仍 **BLOCKED_BY_OFFICIAL_STARTER_KIT**，COMPETITION_COMPLETE=NOT_CLAIMED。
