# README-COMPETITION — 赛道一 llama.cpp-omni 参赛提交入口

> **这是比赛的权威入口文档**。上游原始 `README.md` 保持不动（本文件不覆盖它）。
> 比赛最终要求上传哪些文件 / README 名称，**一律以主办方比赛通知为准**，本文件只是仓库内的权威索引。

## 一句话结论

- **最终候选**：commit `fd3dd36870f60829e47cafffacc7027cf8eb21d4`（tag `competition-final-20260814`，branch `fix/cann-fa-nan-ubatch16`）。
- **三条准确率全部 PASS**（Daily-Omni 79.43% / VideoMME 69.8% / Seed-TTS WER 1.422% + SIM 0.969）。
- **官方 SPEAK→WAV RTF 已可用**：core.rtf_aggregate **1.09–1.17**（官方基线 1.087）。
  ⚠️ **诚实口径**：RTF 可用但**没有相对 1.087 的已证实加速**；Config D 的 ~18% wall 改善是本地配对 A/B，**不是** official RTF −18%。

## 权威文档索引（按主办方需求逐条对齐）

| 主题 | 权威文档 |
|---|---|
| 结果（准确率 + RTF） | [`docs/competition-submission/RESULTS.md`](docs/competition-submission/RESULTS.md) |
| 复现（从零构建 + 评测） | [`docs/competition-submission/REPRODUCTION.md`](docs/competition-submission/REPRODUCTION.md) |
| 优化说明 | [`docs/competition-submission/OPTIMIZATIONS.md`](docs/competition-submission/OPTIMIZATIONS.md) |
| 二进制溯源（SHA256） | [`docs/competition-submission/BINARY_PROVENANCE.md`](docs/competition-submission/BINARY_PROVENANCE.md) |
| 已知限制 | [`docs/competition-submission/KNOWN_LIMITATIONS.md`](docs/competition-submission/KNOWN_LIMITATIONS.md) |
| Demo 复现 | [`docs/competition-submission/DEMO_REPRODUCTION.md`](docs/competition-submission/DEMO_REPRODUCTION.md) |
| 版本溯源（唯一权威） | [`submission/VERSION_MANIFEST.md`](submission/VERSION_MANIFEST.md) |
| 提交包入口 | [`submission/README.md`](submission/README.md) |

## 候选身份（一次定死，不复改）

```text
COMPETITION_FINAL_COMMIT = fd3dd36870f60829e47cafffacc7027cf8eb21d4
COMPETITION_FINAL_TAG    = competition-final-20260814
COMPETITION_FINAL_BRANCH = fix/cann-fa-nan-ubatch16
构成 = a77d6a8 + trackA_fixes.patch（4 文件）+ LISTEN-wedge 生命周期修复 + stage_timing 发射
```

## 复现最短路径

```bash
git clone <repo> && cd llama.cpp-omni-bench-huawei
git checkout fd3dd36
bash submission/environment/env_check.sh
bash submission/scripts/build.sh          # 期望 server=4694cb58… libomni=3f3e1e63…
bash submission/scripts/start_server.sh
bash submission/scripts/health_check.sh
```

## 状态速览

| 块 | 状态 |
|---|---|
| 准确率（3 项） | ✅ PASS |
| 官方 RTF | ✅ AVAILABLE（1.09–1.17，parity baseline 1.087） |
| 二进制可复现 | ✅ PASS（重建 SHA 逐字节一致） |
| 稳定性 | ✅ PASS（2× RTS soak 0 崩溃、无线程泄漏） |
| Demo | 🟡 服务侧 PASS / 官方前端 NOT_RUN |
| 提交完成声明 | 🟡 NOT_CLAIMED（以主办方正式提交为准） |
