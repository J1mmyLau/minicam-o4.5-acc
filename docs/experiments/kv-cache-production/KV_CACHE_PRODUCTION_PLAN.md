# KV Cache Production Gates — 生产化验证计划

**Date:** 2026-07-26
**Worktree:** `/workspace/llama.cpp-omni-kvcache-prod`
**Branch:** `perf/kv-cache-production-gates`
**Base HEAD:** `a70c085` (ngl8-e2e-closeout-20260726)

---

## 0. 来源

从 `perf/ngl8-e2e-stage-profiling` (`ngl8-e2e-closeout-20260726`) 分出。
上一个闭环不得修改。

## 1. 目标

将 KV cache 复用从 PASS_FOR_TESTED_STATIC_PREFIX_WORKLOAD 提升至生产可部署：

- **P0:** 阶段初始化和计划制定
- **P1:** 生产级 cache 文件存储语义
- **P2:** 8 项边界条件 Gate matrix
- **P3:** 分级稳定性长测（1h→6h→24h→72h→168h）
- **P4:** DEFAULT_ON / OPT_IN 最终决策
- **P5:** 状态与提交

## 2. 当前已知基线

| 维度 | 判定 | 证据 |
|------|------|------|
| T2W Lifecycle | VALIDATED | 91e5674, P9: 150/150, 0 rc0_without_audio |
| KV Cache Functional | PASS | 62 reused tokens, cache_miss=0 |
| KV Cache Performance | PASS_FOR_TESTED_STATIC_PREFIX_WORKLOAD | 30 pairs, 9642ms p50, CI [8742,11470] |
| Production | OPT_IN_READY / DEFAULT_OFF | 8 boundary conditions NOT_TESTED |
| General Production Readiness | NOT_YET_APPROVED | soak / boundary tests pending |

## 3. 禁止事项

- 不得修改旧 `perf/ngl8-e2e-stage-profiling` 分支
- 不得覆盖已有实验报告
- 不得在完成全部 Gate 前宣称 DEFAULT_ON
- 不得跳过任一 Gate
- 不得仅凭代码审计判定边界测试 PASS

## 4. 提交计划

每个阶段独立提交。每个 Gate 通过后更新 STATUS、HANDOFF、AUDIT、TASKS。

---

**文档版本:** 1.0
**最后更新:** 2026-07-26
