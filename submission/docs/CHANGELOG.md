# CHANGELOG（比赛收口阶段）

## 2026-08-14 — 最终冻结 fd3dd36（tag competition-final-20260814）
- 候选最终身份定为 `fd3dd36`（branch `fix/cann-fa-nan-ubatch16`），内含 a77d6a8 +
  trackA_fixes.patch + LISTEN-wedge 生命周期修复 + stage_timing 发射。
- 二进制 SHA 权威表落 `VERSION_MANIFEST.md`（server `4694cb58…` / libomni `3f3e1e63…` 等 8 项 + model）。
- OFFICIAL_RTF 从 BLOCKED 改为 AVAILABLE（core.rtf_aggregate 1.09–1.17，parity baseline 1.087）。
- 新增权威提交入口：`README-COMPETITION.md` + `docs/competition-submission/{RESULTS,REPRODUCTION,
  OPTIMIZATIONS,BINARY_PROVENANCE,KNOWN_LIMITATIONS,DEMO_REPRODUCTION}.md`。

## 2026-08-14 — 官方状态校正 + RTF 阻塞重审
- 移除过时 `BLOCKED_BY_OFFICIAL_STARTER_KIT` 口径：统一评测分支 `tc-mb/llama.cpp-omni`（`bench/huawei`）
  已到达并已跑通 official smoke 4/4 + Daily-Omni/Video-MME/Seed-TTS 全量准确率。
- 置 `OFFICIAL_UNIFIED_EVAL_BRANCH=AVAILABLE` / `STARTER_KIT_BLOCKER=REMOVE`。
- RTF=NULL 阻塞重审结论 = **Class A（RUNTIME_EMISSION_MISSING）**：生产 C++（非受保护）不吐
  `stage_timing.jsonl`/SSE `metrics`；官方 judge 完整；旧 `benchmark_client.py` 占位说法作废。
  详见 `docs/F6_RTF_BLOCKER_REAUDIT.md`。

## 2026-08-14 — Track F 最终可复现提交包（证据闭环）
- 候选重新冻结：source `a77d6a8`（`fix/cann-fa-nan-ubatch16`）+ `trackA_fixes.patch`（4 文件）。
- 二进制 SHA256 权威表（libomni `b600ce52…` / server `c330dc5a…` 等 8 项）落 `VERSION_MANIFEST.md`。
- 三条准确率基线 PASS（Daily 79.43% / VideoMME 69.8% / Seed-TTS 1.422%/0.969）。
- 恢复 `docs/competition-submission/`（17 文件）+ `submission/`（40 文件骨架）并回填当前口径。

## 2026-08-13 — Track A/C：Seed-TTS WER=100% 根因 + 全量准确率
- Seed-TTS 三污染源定位修复（gf_enc 双重计算 / FA Q-split 默认 16 / ecee7de memcpy rope）。
- 全量 2020 条 Seed-TTS WER 1.422% / SIM 0.969（pristine 1.5%/0.97），0 NaN/error。
- Config D 统一兼容性 VERIFIED（MAX_UBATCH=16 + Q-split 0 对 Seed-TTS 无副作用）。

## 2026-08-11~12 — FA NaN 根因 + FA-local Q split
- 冻结根因：FA mask regression `b6b6af0`；`aclnnMm` 有限输入→NaN（MAX_UBATCH=16 workaround）。

## 2026-08-05 — 收口阶段启动
- 新建 `docs/competition-submission/`（需求矩阵/门状态/Benchmark 计划/Demo 计划/chunk RTF 规范/性能报告模板/复现审计/提交清单/Demo 指南/录像脚本）。
- 新建 `submission/` 提交包骨架（脚本全 `set -Eeuo pipefail`，冻结 env 固化，chunk RTF 采集管线可运行）。
- 新建 `docs/vllm-migration/`（vLLM 比赛约束附录）。

## 2026-08-04 — 内部候选冻结（前序）
- source `bdd4550`，REPRODUCIBLE_BINARY=PASS，T6 冻结二进制 11/11。
- 详细历史见仓库 git log（f26323f / d5cc978 / adb9bb6 / bd52707 / bdd4550）。
