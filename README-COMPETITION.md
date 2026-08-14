# README-COMPETITION — 赛道一 llama.cpp-omni 参赛提交入口

> **这是比赛的权威入口文档**。上游原始 `README.md` 保持不动（本文件不覆盖它）。
> 比赛最终要求上传哪些文件 / README 名称，**一律以主办方比赛通知为准**；本文件把官方评测规范
> （[`docs/competition-submission/OFFICIAL_EVALUATION_SPEC.md`](docs/competition-submission/OFFICIAL_EVALUATION_SPEC.md)）
> 的 G1→G8 流程与五类提交内容逐条映射到仓库内的交付物。

## 一句话结论

- **最终交付分支**：`competition/final-ascend-track-a`（提交包 commit `16ec3500d`）。
- **真正跑出数据的 runtime**：`fd3dd36`（tag `competition-final-20260814`，冻结，**不再变**）。
- **四项精度准入全部 PASS**（详见下表）。
- **官方 SPEAK→WAV RTF 已可用**：core.rtf_aggregate **1.09–1.17**（官方排名基线 1.087）。
  ⚠️ **诚实口径**：RTF 可用但**没有相对 1.087 的已证实加速**；Config D 的 ~18% wall 改善是本地配对 A/B，**不是** official RTF −18%。

## 比赛评什么（官方评测流程 G1→G8）

| Gate | 内容 | 通过标准 | 本仓库状态 |
|---|---|---|---|
| G1 框架与环境 | llama.cpp-omni · 单卡 910C · CANN 9.1.0-beta1 · F16 · 并发 1 | 环境一致 | ✅ PASS |
| G2–G4 精度准入 | 四项指标（下表） | 全部达标 | ✅ 4/4 PASS |
| G5 Demo 准入 | 接入 MiniCPM-o-Demo | 服务可连、多模态完整、连续稳定 | 🟡 服务侧 PASS / 官方前端 NOT_RUN |
| G6 RTF 排名 | SPEAK→WAV 完整链路 RTF | 越低越好 | ⚖️ 1.09–1.17（parity 1.087，无已证实加速） |
| G7 工程复现 | checkout→构建→启动 | 一键可复现 | ✅ 构建侧 PASS（官方环境 NOT_RUN） |
| G8 提交审查 | 五类提交内容齐全 | 清单全勾 | 🟡 待主办方正式提交 |

### 精度准入阈值（**四项必须全部满足**，官方基线 F16）

| 指标 | 官方基线 | 准入线 | 候选结果 | 判定 |
|---|---|---|---|---|
| VideoMME ↑ | 69.0 | **≥ 67.0** | **69.8%** | ✅ +2.8pp |
| Daily-Omni ↑ | 79.5 | **≥ 77.5** | **79.43%**（950/1196） | ✅ +1.93pp |
| TTS-Seed ASV (SIM) ↑ | 0.709 | **≥ 0.689** | **0.969**（2020/2020） | ✅ |
| TTS-Seed WER ↓ | 1.414 | **≤ 1.56** | **1.422%**（2020/2020） | ✅ |

> ⚠️ TTS-Seed 是**两项**指标（ASV = 绝对下降 ≤0.02；WER = 相对增幅 ≤10%），**不得**用统一 "≤2pp" 描述。

## 提交内容五类 → 仓库交付物（文档 / 代码 / 性能分数）

| 官方要求（最终提交 5 类） | 仓库对应 | 类型 |
|---|---|---|
| ① 完整代码与配置 | `submission/`（源码冻结 `fd3dd36` + `config/server.env`、`benchmark.yaml` + 全部脚本） | **代码** |
| ② Benchmark 评测结果 | [`RESULTS.md`](docs/competition-submission/RESULTS.md) + 三份 comparison.json | **性能分数** |
| ③ 性能测试报告 | [`OPTIMIZATIONS.md`](docs/competition-submission/OPTIMIZATIONS.md) + PERFORMANCE_REPORT | **性能分数** |
| ④ 可运行 Demo | [`DEMO_REPRODUCTION.md`](docs/competition-submission/DEMO_REPRODUCTION.md) + 演示视频 | 文档 |
| ⑤ 优化与复现说明 | [`OPTIMIZATIONS.md`](docs/competition-submission/OPTIMIZATIONS.md) / [`REPRODUCTION.md`](docs/competition-submission/REPRODUCTION.md) / [`KNOWN_LIMITATIONS.md`](docs/competition-submission/KNOWN_LIMITATIONS.md) | **文档** |

## 候选身份（runtime 与 submission 严格区分）

```text
TESTED_RUNTIME_COMMIT    = fd3dd36870f60829e47cafffacc7027cf8eb21d4   (tag competition-final-20260814)
FINAL_SUBMISSION_COMMIT  = 16ec3500d61ab708da60974d9416dc8ffc34ee88  (tag competition-submission-20260814)
FINAL_BRANCH             = competition/final-ascend-track-a
```

> `fd3dd36` 是真正跑出当前数据的 runtime SHA，**固定不变**；`16ec3500d` 只是在它之上追加提交文档，
> 二进制仍对应 `fd3dd36`（构成 = `a77d6a8` + `trackA_fixes.patch` + LISTEN-wedge 生命周期修复 + stage_timing 发射）。

## 代码项目结构（评审速览）

> 根 `README.md` = 组织方 llama.cpp-omni 原始 README，**保持不动**（可 diff 对比）。本分支入口 = 本文件。
> 原始 llama.cpp README 另存于 `README_llama.cpp.md`（只读备份）。

```
llama.cpp-omni-bench-huawei/
├── src/                          # llama.cpp 推理引擎核心（context / graph / kv-cache / arch）
├── tools/omni/                   # ★ Omni 多模态服务与评测
│   ├── omni.cpp / omni.h         #   全双工流式引擎（VPM/APM/LLM/TTS/Token2Wav 接线）
│   ├── omni-cli.cpp              #   CLI 推理入口
│   ├── omni-eval-cli.cpp         #   官方统一评测 CLI（evaluation/ 的入口）
│   ├── omni-eval-daily-cli.cpp   #   Daily-Omni 评测
│   ├── omni-tts-eval.cpp         #   TTS-Seed 评测
│   └── token2wav/                #   Flow Matching vocoder
├── ggml/src/ggml-cann/           # ★ 昇腾 CANN 后端（aclnn_ops.cpp / ggml-cann.cpp）
├── evaluation/                   # 官方评测脚本（run_all.sh + daily-omni/tts_seed/videomme/judge-final）
├── submission/                   # ★ 提交包（config / scripts / docs / benchmark_results / performance / demo）
├── docs/competition-submission/  # ★ 比赛提交文档（权威，见下方导航）
├── docs/F6_*.md                  # 内部证据链（性能/精度/稳定性追踪，非提交物）
├── docs/vllm-migration/          # vLLM-Omni 迁移文档集（子赛道 B 参考）
├── config_d_official.env         # ★ Config D 运行时（6 个环境变量，见 OPTIMIZATIONS.md）
├── examples/ common/ include/ ggml/   # llama.cpp 生态公共代码
└── experiments/ demo_runs/       # 实验/演示产物（transient，不进提交包）
```

**关键改动点（相对组织方 baseline，均在 freeze runtime `fd3dd36` 内）**：
- `tools/omni/omni.cpp` — LISTEN-wedge 生命周期修复 + `stage_timing.jsonl`/SSE `metrics` 发射（RTF 由 BLOCKED→AVAILABLE）
- `ggml/src/ggml-cann/aclnn_ops.cpp` — FA-local Q split + `OMNI_CANN_FA_MAX_UBATCH=16`（FA NaN 修复）
- `tools/omni/token2wav/` — Flow∥Vocoder 并行 pipeline（Config D 的 `OMNI_T2W_PIPELINE_OVERLAP=1`）

## 复现最短路径

```bash
git clone <本仓库> && cd llama.cpp-omni-bench-huawei
git checkout competition/final-ascend-track-a      # 提交包（含全部提交文档）
# 复现评测二进制用冻结 runtime：
git checkout fd3dd36870f60829e47cafffacc7027cf8eb21d4
bash submission/environment/env_check.sh
bash submission/scripts/build.sh                    # 期望 server=4694cb58… libomni=3f3e1e63…
```

## 完整文档导航（从本文件跳转）

> 所有链接相对本文件；`docs/competition-submission/` 简称 **cs**。

### 一、官方规范与身份（先读）
| 文档 | 内容 |
|---|---|
| [`cs/OFFICIAL_EVALUATION_SPEC.md`](docs/competition-submission/OFFICIAL_EVALUATION_SPEC.md) | 官方评测规范 G1→G8（权威，只读） |
| [`cs/COMPETITION_REQUIREMENTS_MATRIX.md`](docs/competition-submission/COMPETITION_REQUIREMENTS_MATRIX.md) | 需求矩阵（官方要求 → 状态 → 产物） |
| [`submission/VERSION_MANIFEST.md`](submission/VERSION_MANIFEST.md) | 版本溯源（commit/SHA 唯一权威） |
| [`cs/BINARY_PROVENANCE.md`](docs/competition-submission/BINARY_PROVENANCE.md) | 二进制 SHA256 溯源表 |

### 二、结果与优化（评审核心）
| 文档 | 内容 |
|---|---|
| [`cs/RESULTS.md`](docs/competition-submission/RESULTS.md) | 四项精度指标 + 官方 RTF |
| [`cs/OPTIMIZATIONS.md`](docs/competition-submission/OPTIMIZATIONS.md) | 优化方法 + 每项 A/B 证据 |
| [`cs/REPRODUCTION.md`](docs/competition-submission/REPRODUCTION.md) | 复现步骤 |
| [`cs/KNOWN_LIMITATIONS.md`](docs/competition-submission/KNOWN_LIMITATIONS.md) | 已知限制（诚实标注） |

### 三、Demo 与提交包
| 文档 | 内容 |
|---|---|
| [`cs/DEMO_REPRODUCTION.md`](docs/competition-submission/DEMO_REPRODUCTION.md) | Demo 复现 |
| [`cs/DEMO_USER_GUIDE.md`](docs/competition-submission/DEMO_USER_GUIDE.md) | Demo 使用说明 |
| [`cs/DEMO_VALIDATION_PLAN.md`](docs/competition-submission/DEMO_VALIDATION_PLAN.md) · [`DEMO_VIDEO_SCRIPT.md`](docs/competition-submission/DEMO_VIDEO_SCRIPT.md) | 验证计划 · 录像脚本 |
| [`cs/FINAL_SUBMISSION_CHECKLIST.md`](docs/competition-submission/FINAL_SUBMISSION_CHECKLIST.md) | 提交检查清单（A–F） |
| [`submission/README.md`](submission/README.md) | 提交包入口 |

### 四、Gate 状态与工具链
| 文档 | 内容 |
|---|---|
| [`cs/OFFICIAL_GATE_STATUS.md`](docs/competition-submission/OFFICIAL_GATE_STATUS.md) | Gate 状态 Dashboard（唯一权威） |
| [`cs/OFFICIAL_GATE_MATRIX.md`](docs/competition-submission/OFFICIAL_GATE_MATRIX.md) · [`OFFICIAL_GATE_READINESS_REPORT.md`](docs/competition-submission/OFFICIAL_GATE_READINESS_REPORT.md) | Gate 矩阵 · 就绪度核查 |
| [`cs/OFFICIAL_GATE_TOOLING_SELFTEST.md`](docs/competition-submission/OFFICIAL_GATE_TOOLING_SELFTEST.md) | 工具链自检 |

### 五、性能测量规范
| 文档 | 内容 |
|---|---|
| [`cs/CHUNK_RTF_MEASUREMENT_SPEC.md`](docs/competition-submission/CHUNK_RTF_MEASUREMENT_SPEC.md) | chunk RTF 测量规范 |
| [`cs/PERFORMANCE_REPORT_TEMPLATE.md`](docs/competition-submission/PERFORMANCE_REPORT_TEMPLATE.md) | 性能报告模板 |
| [`cs/BENCHMARK_EXECUTION_PLAN.md`](docs/competition-submission/BENCHMARK_EXECUTION_PLAN.md) · [`RTF_PARSER_AUDIT.md`](docs/competition-submission/RTF_PARSER_AUDIT.md) | Benchmark 执行计划 · RTF 解析审计 |

### 六、内部证据链（追踪用，非提交物）
| 文档 | 内容 |
|---|---|
| [`docs/F6_OFFICIAL_RTF_RESOLVED.md`](docs/F6_OFFICIAL_RTF_RESOLVED.md) | RTF 阻塞解除根因（LISTEN-wedge） |
| [`docs/F6_FINAL_REPORT.md`](docs/F6_FINAL_REPORT.md) | 最终报告 |
| `docs/F6_*.md`（其余 15+ 份） | 性能/精度/稳定性追踪（Phase A–D / Track A–F / Gate 0–4） |

## 状态速览

| 块 | 状态 |
|---|---|
| 精度准入（4 项） | ✅ 4/4 PASS |
| 官方 RTF | ⚖️ AVAILABLE（1.09–1.17，parity baseline 1.087，无已证实加速） |
| 二进制可复现 | ✅ PASS（重建 SHA 逐字节一致） |
| 稳定性 | ✅ PASS（2× RTS soak 0 崩溃、无线程泄漏） |
| Demo | 🟡 服务侧 PASS / 官方前端 NOT_RUN |
| 提交完成声明 | 🟡 NOT_CLAIMED（以主办方正式提交为准） |
