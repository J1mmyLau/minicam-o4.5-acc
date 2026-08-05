# F6 证据索引

> 每个结论必须可追溯到 raw 数据、commit、配置和源码位置。
> 状态标签: `LLAMA_CONFIRMED` (冻结日志实测) / `INTERNAL` (内部验证) / `NOT_MEASURED` / `NOT_RUN`
> 证据类型: `RAW_PERSISTED` (原始数据文件存在) / `REPORT_ONLY` (仅有报告文档) / `SOURCE_ONLY` (仅源码证据) / `OFFICIAL_PENDING` (待官方)

---

## 证据清单

| ID | 结论 | 状态 | 证据类型 | 源码 commit | Binary SHA | 配置 | 样本 | 报告 | Raw 数据 | 源码位置 | 可用于官方? |
|----|------|------|---------|------------|------------|------|------|------|---------|---------|-----------|
| **E01** | 环境就绪 (910C + CANN 9.1.0-beta.1) | `LLAMA_CONFIRMED` | `SOURCE_ONLY` | bdd4550 | db258375 | env_check.sh | — | `submission/environment/env_check.sh` | env_check 输出 | — | ❌ (工具链，非结果) |
| **E02** | Static Prefix KV Cache — R13 Canonical 30/30 | `INTERNAL` | `REPORT_ONLY` | bdd4550 | db258375 | OMNI_KV_CACHE_REUSE=1 | 30 pairs | `docs/tracking/f6_lifecycle/R13_CANONICAL_STATIC_PREFIX_AB_FINAL.md` | server log (embedded in report) | `src/llama-kv-cache.cpp` | ❌ (内部) |
| **E03** | Persistent 生命周期 — 3 seq requests | `INTERNAL` | `REPORT_ONLY` | bdd4550 | db258375 | — | 3 | `docs/tracking/F6_C6_PROFILE_LIFECYCLE_STATE_MACHINE.md` | lifecycle test logs (embedded) | `tools/server/server-context.cpp` | ❌ (内部) |
| **E04** | CANN T2W 设备放置 — 32/32 pairs | `INTERNAL` | `RAW_PERSISTED` | e159b3ee (early) | e159b3ee | OMNI_T2W_DEVICE=cann-flow-only OMNI_VOC_DEVICE=gpu | 32 pairs | `docs/F6_PHASE2_STEP6_CANN_T2W_AB.md` | `docs/f6-s13-closure/phase2/step6_cann_t2w_ab.json` | `tools/omni/token2wav/token2wav-impl.cpp` | ❌ (内部) |
| **E05** | B6b 负实验 — REJECT | `INTERNAL` | `REPORT_ONLY` | pre-bdd4550 | — | CHUNK_SIZE=25, speak_threshold 10→5 | ~60 | `docs/tracking/F6_B6B_REJECTED_CANDIDATE.md` | B6b A/B logs (embedded) | `tools/omni/omni.cpp` | ❌ (内部) |
| **E06** | TTS KV bounds — T13 test PASS | `INTERNAL` | `REPORT_ONLY` | bdd4550 | db258375 | — | 1 boundary | `docs/tracking/` F6 T13 memory | T13 boundary log (embedded) | `tools/omni/omni.cpp` | ❌ (内部) |
| **E07** | Text non-streaming — fixed | `INTERNAL` | `SOURCE_ONLY` | bdd4550 | db258375 | — | — | T9 fix log | — | `tools/server/server.cpp` | ❌ (内部) |
| **E08** | SSE bad_alloc crash — fixed | `INTERNAL` | `SOURCE_ONLY` | bdd4550 | db258375 | — | — | T9 fix log | — | `tools/server/server.cpp` | ❌ (内部) |
| **E09** | S13 120/120 Baseline stability | `LLAMA_CONFIRMED` | `REPORT_ONLY` | bdd4550 | db258375 | Standard server config | 120 | `docs/f6-s13-closure/phase2/T6_INTEGRATED_REGRESSION_REPORT.md` | S13 server logs (embedded) | — | ❌ (内部) |
| **E10** | T6 KV A/B 28/30 valid | `LLAMA_CONFIRMED` | `REPORT_ONLY` | bdd4550 | db258375 | OMNI_KV_CACHE_REUSE=1 | 30 pairs (28 valid, 2 A_ERR) | `docs/f6-s13-closure/phase2/t6_kv_ab_27of30.md` | T6 regression server log (embedded) | `src/llama-kv-cache.cpp` | ❌ (内部) |
| **E11** | Daily-Omni internal pilot — 6/6 gates | `INTERNAL` | `RAW_PERSISTED` | bdd4550 | db258375 | Standard omni config | 6 gates | `docs/f6-s13-closure/phase2/daily_omni_pilot/pilot_run.log` | pilot_run.log | `tools/omni/omni.cpp` | ❌ (内部) |
| **E12** | CANN CPU/NPU 放置审计 | `INTERNAL` | `SOURCE_ONLY` | bdd4550 (read-only) | — | -ngl 999 | — | `docs/audit/CANN_CPU_NPU_PLACEMENT_AUDIT.md` | — | `ggml/src/ggml-cann/ggml-cann.cpp` | ❌ (审计) |
| **E13** | 二进制可复现构建 | `LLAMA_CONFIRMED` | `REPORT_ONLY` | bdd4550 | db258375 (server) / c4b16937 (libomni) | build-twice-same-dir | 2 builds | `docs/tracking/` F6 source freeze | build SHA logs (embedded) | — | ❌ (工具链) |
| **E14** | 提交工具链 selftest | `LLAMA_CONFIRMED` | `REPORT_ONLY` | 80a86ab (docs) | — | selftest 14 steps | 14 | `docs/competition-submission/OFFICIAL_GATE_TOOLING_SELFTEST.md` | selftest output (embedded) | `submission/` | ❌ (工具链) |
| **E15** | G7 稳定性 30min | `INTERNAL` | `REPORT_ONLY` | pre-bdd4550 | — | Standard server config | 797 chunks | `profiles/g7_stability_30min/` | G7 server logs | — | ❌ (内部旧版) |
| **E16** | msprof 历史数据 | `HISTORICAL_REF_ONLY` | `SOURCE_ONLY` | pre-bdd4550 (2026-07-28) | — | CANN 9.0 era | 835K events | `profiles/decode-speak/PROF_*/` | msprof_20260728064956.json | — | ❌ (历史旧版) |

---

## 证据类型定义

| 类型 | 含义 | 可用于 |
|------|------|--------|
| `RAW_PERSISTED` | 原始实验数据文件存在于磁盘，可被第三方独立解析 | A/B 验证、统计再分析 |
| `REPORT_ONLY` | Markdown 报告存在但原始数据嵌入报告或仅存在于 /tmp | 内部参考、历史记录 |
| `SOURCE_ONLY` | 结论仅从源码静态分析得出，无运行时实验数据 | 代码审计、静态分析 |
| `OFFICIAL_PENDING` | 依赖官方 Harness，当前不可用 | 待官方 Starter Kit 到达 |

**当前分布**: RAW_PERSISTED=2 (E04, E11) / REPORT_ONLY=10 / SOURCE_ONLY=4 (E01, E07, E08, E12, E16) / OFFICIAL_PENDING=0

---

## 证据层级定义

| Level | 含义 | 可用于 |
|-------|------|--------|
| L0 | 假设 | 内部讨论 |
| L1 | 源码静态证据 | 代码审计 |
| L2 | 运行时日志 | 内部追踪 |
| L3 | 单因素 A/B | 内部优化报告 |
| L4 | 长稳回归 | 内部冻结判定 |
| L5 | 官方 Harness | **仅 L5 可写 OFFICIAL_PASS** |

当前 F6 最高证据等级: **L4** (T6 integrated regression, 11/11 PASS)。无 L5 证据。

---

## 路径校验

| 路径 | 存在? | 类型 |
|------|-------|------|
| `docs/f6-s13-closure/phase2/T6_INTEGRATED_REGRESSION_REPORT.md` | ✅ | REPORT_ONLY |
| `docs/F6_PHASE2_STEP6_CANN_T2W_AB.md` | ✅ | REPORT_ONLY |
| `docs/f6-s13-closure/phase2/step6_cann_t2w_ab.json` | ✅ | **RAW_PERSISTED** |
| `docs/tracking/f6_lifecycle/R13_CANONICAL_STATIC_PREFIX_AB_FINAL.md` | ✅ | REPORT_ONLY |
| `docs/audit/CANN_CPU_NPU_PLACEMENT_AUDIT.md` | ✅ | SOURCE_ONLY |
| `docs/competition-submission/OFFICIAL_GATE_TOOLING_SELFTEST.md` | ✅ | REPORT_ONLY |
| `docs/competition-submission/OFFICIAL_GATE_STATUS.md` | ✅ | REPORT_ONLY |
| `profiles/g7_stability_30min/` | ✅ | REPORT_ONLY |
| `profiles/decode-speak/PROF_*/` (msprof) | ✅ | SOURCE_ONLY (historical) |
| `docs/f6-s13-closure/phase2/daily_omni_pilot/pilot_run.log` | ✅ | **RAW_PERSISTED** |

---

## 未归档数据

以下数据仅存在于 `/tmp` 或未持久化路径，标记为 `MISSING_PERSISTED_RAW`：

| 数据 | 状态 |
|------|------|
| (待填充——如发现仅 /tmp 的 raw，在此记录) | — |

---

## 快速查找

```bash
# 按结论 ID 查找
grep -r "E04" docs/F6_EVIDENCE_INDEX.md

# 按证据类型查找
grep "RAW_PERSISTED" docs/F6_EVIDENCE_INDEX.md

# 按 commit 查找
git log --oneline bdd4550

# 按 binary SHA 查找
sha256sum build/bin/llama-omni-server

# 按 raw 路径查找
ls docs/f6-s13-closure/phase2/
```
