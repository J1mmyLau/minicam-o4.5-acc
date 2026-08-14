# 最终提交包检查清单

> 对照赛事"最终提交内容"逐项勾选。全部完成后才允许 `COMPETITION_COMPLETE=YES`。
> 提交目录：`submission/`（骨架已建，见 REPRODUCTION_AUDIT.md §防复现失败清单）。

---

## A. 完整代码与配置

- [ ] 推理适配与性能优化代码（冻结源码 `bdd4550` 已固化）
- [ ] llama.cpp-omni 相关配置（`submission/config/server.env`、`benchmark.yaml`）
- [ ] 服务启动脚本（`start_server.sh` / `stop_server.sh` / `health_check.sh`）
- [ ] Benchmark 执行脚本（`run_daily_omni.sh` / `run_tts_seed.sh` / `run_video_mme.sh`）
- [ ] Demo 启动脚本（`start_demo.sh` / `run_demo.sh` / `demo_smoke.sh`）
- [ ] 依赖与环境配置（`environment/env_check.sh` / `requirements.txt` / `system_info.txt`）

## B. 三项 Benchmark 评测结果

- [ ] **Daily-Omni**：测试命令 + 参数 + 原始输出 + 结果汇总
- [ ] **TTS-Seed**：同上
- [ ] **Video-MME**：同上
- [ ] baseline 与 candidate 同脚本同子集同分母
- [ ] 精度降幅 ≤ 2pp 逐项判定
- [ ] 失败样本 / 异常说明

## C. 性能测试报告

- [ ] chunk RTF（逐 chunk：count/mean/p50/p90/p95/p99/max/首/中/尾）
- [ ] 测试环境 / 测试数据 / 测试次数 / 统计方式
- [ ] 优化前后对比（baseline vs candidate）
- [ ] 资源使用情况（CPU/NPU HBM/RSS）
- [ ] 异常情况说明
- [ ] TTFT / TTFP：llama 子赛道作为体验分析指标说明（非排名指标）

## D. 可运行 Demo

- [ ] 可运行 Demo（接入 OpenBMB/MiniCPM-o-Demo）
- [ ] Demo 使用说明（`DEMO_USER_GUIDE.md`）
- [ ] 启动与访问方式
- [ ] 核心交互流程
- [ ] 演示视频（`demo/video_manifest.md` + 视频文件）

## E. 优化与复现说明

- [ ] 原始性能瓶颈分析（T2W CPU = 93%）
- [ ] 采用的优化方法（静态前缀 KV / 生命周期 / CANN Flow/Vocoder / TTS KV guard / 接口修复）
- [ ] 各项优化带来的性能变化（每项 baseline/candidate/CI95/决策）
- [ ] 效果保持情况（T6 11/11 + 三项精度）
- [ ] 完整复现步骤（`REPRODUCTION_GUIDE.md`）
- [ ] 关键技术说明

## F. 提交包目录核对

- [ ] `submission/README.md`（入口）
- [ ] `submission/VERSION_MANIFEST.md`（commit/SHA 对应）
- [ ] `submission/environment/`（env_check.sh / requirements.txt / system_info.txt）
- [ ] `submission/config/`（server.env / benchmark.yaml）
- [ ] `submission/scripts/`（全部脚本 set -Eeuo pipefail、可执行、幂等）
- [ ] `submission/benchmark_results/baseline/` + `candidate/`
- [ ] `submission/performance/`（chunk_rtf_raw.csv + chunk_rtf_summary.json + PERFORMANCE_REPORT.md）
- [ ] `submission/demo/`（DEMO_GUIDE.md + video_manifest.md + 视频）
- [ ] `submission/docs/`（OPTIMIZATION_REPORT / REPRODUCTION_GUIDE / KNOWN_LIMITATIONS / CHANGELOG）

## 当前状态

| 块 | 状态 |
|---|---|
| A 代码与配置 | 基本齐备（骨架 + 冻结源码） |
| B 三项 Benchmark | 待官方 Starter Kit（BLOCKED_BY_ASSET） |
| C 性能报告 | 模板就绪，官方口径待定 |
| D Demo | 服务侧 PASS，官方前端接入 NOT_RUN |
| E 复现 | 构建侧 PASS，官方环境 NOT_RUN |
| F 目录 | 骨架已建 |

> `COMPETITION_COMPLETE` 在 A–F 全勾 + 官方 Gate 全过后才置 YES。
