# CHANGELOG（比赛收口阶段）

## 2026-08-05 — 收口阶段启动
- 新建 `docs/competition-submission/`（需求矩阵/门状态/Benchmark 计划/Demo 计划/chunk RTF 规范/性能报告模板/复现审计/提交清单/Demo 指南/录像脚本）。
- 新建 `submission/` 提交包骨架（脚本全 `set -Eeuo pipefail`，冻结 env 固化，chunk RTF 采集管线可运行）。
- 新建 `docs/vllm-migration/VLLM_COMPETITION_REQUIREMENTS.md`（vLLM 比赛约束附录）。

## 2026-08-04 — 内部候选冻结（前序）
- source `bdd4550`，REPRODUCIBLE_BINARY=PASS，T6 冻结二进制 11/11。
- 详细历史见仓库 git log（f26323f / d5cc978 / adb9bb6 / bd52707 / bdd4550）。
