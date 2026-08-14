# F6 — Phase 7: Flow Optimization — Negative Result (DO NOT SHIP)

Date: 2026-08-13 · Commit: a77d6a8 (clean, experiment reverted)
Directive: 【BYPASS — FINAL OFFICIAL GATE THEN FLOW OPTIMIZATION】 Phase 7

## 结论速览

| Field | Value |
|---|---|
| FLOW_OPT_SELECTED | Flow-scoped ACL graph capture (`GGML_CANN_FLOW_ACL_GRAPH`) |
| FLOW_STAGE_GAIN | **−20.4%** p50（`token2mel` 147.5 → 117.3ms；`t2m.compute` 138.1 → 109.6ms） |
| FLOW_OPT_E2E_GAIN | **NEGATIVE**（+11% mean，14286 → 15863ms） |
| DECISION | **DO NOT SHIP** — 未达「measurable E2E gain」达标线 |
| FINAL_STATE | ggml-cann.cpp 已 revert，二进制与 Gate 2 逐字节一致（SHA256 相同） |

## 实验方法（clean A/B）

- workload：`token2wav-example`，`OMNI_T2W_DEVICE=gpu`（flow=CANN0）、`OMNI_VOC_DEVICE=cpu`
  （vocoder CPU 8 线程，稳定基线）、`OMNI_T2W_REPEAT=8`（30 chunk）、`OMNI_T2W_PROFILE=1`。
- 变量：`GGML_CANN_FLOW_ACL_GRAPH` off（Arm A EAGER）vs on（Arm B capture）。
- 固定：`GGML_CANN_ACL_GRAPH=off`（评价硬约束，全局 EAGER）。
- 每臂 3 次重复，1 次 warmup 丢弃。

## 结果（30 chunk，3 rep）

| metric | Arm A (EAGER) | Arm B (capture) | Δ |
|---|---|---|---|
| `t2m.compute` p50（flow kernel） | 138.1ms | 109.6ms | **−20.7%** |
| `token2mel` p50（flow 总） | 147.5ms | 117.3ms | **−20.4%** |
| `t2m.compute` p95 / p99 | 141.2 / 141.6ms | **362.3 / 460.9ms** | +156% / +226% |
| `vocoder` p50（CPU） | 349.1ms | 389.4ms | +11.5% |
| `total` p50 | 489.5ms | 506.7ms | +3.5% |
| **infer E2E（3 rep mean）** | **14286ms** | **15863ms** | **+11%** |

## 根因分析（为何失败）

1. **p95/p99 尾部爆炸 = 2 次一次性 capture**：非 last 图（11740 节点）+ last 图（11746 节点）
   各 capture 一次（~360–460ms/次），是 EAGER 单 chunk 的 ~3 倍。30 chunk 摊薄后仍有 6.7%
   的 chunk 受影响；真实 SPEAK 轮（35 chunk）摊薄后 ≈ 2/35 = 5.7%。
2. **capture 只消 kernel launch，不消 graph build**：flow 每个 chunk 仍 `ggml_init` →
   `build_forward_chunk_graph` → `gallocr_alloc`（~50–70ms）。ACL graph 只省 188k 次
   kernel launch（实测仅 ~30ms），Phase 5 估计的 104–160ms host 开销中 graph build
   占大头、且未被本轮候选触及。
3. **CPU vocoder 竞争 +11.5%**：`aclmdlRIExecuteAsync` graph 执行改变了 host/device 同步
   时序，挤压了同 chunk 串行的 CPU vocoder（本测试 artifact，Config D 下 vocoder 走 CANN
   不复现，但 Config D 的 overlap 线程模型下风险未知）。

## 决策依据

- 可测增益上限被 graph build 封顶（~30ms/chunk），远小于 Phase 5 的乐观估计。
- E2E 实测为负（+11%），且尾部方差翻倍，会拖累 RTF p95。
- 要拿到更大增益需 Rank 2（持久化 flow 图，消 graph build），但那是 token2wav-impl.cpp
  重构、动态 shape 处理，风险中高，超出「ONE Flow candidate」范围且无低风险回报。

→ **flow ACL graph capture 不达标，revert，Config D 保持 VERIFIED（未优化）。**

## 最终状态

- `ggml/src/ggml-cann/ggml-cann.cpp`：**revert 至 pristine**（`git status` 0 行改动）。
- `USE_ACL_GRAPH`：build cache 恢复 `OFF`。
- 4 目标二进制 SHA256 与 Gate 2 逐字节一致（libomni=1e5b0103… / server=c330dc5a… /
  tts-eval=0208071b… / eval-cli=640aa777… / eval-daily-cli=1b06868c…）。

## NEXT_ACTION

进入 Phase 8：最终官方校验（accuracy + SPEAK→WAV RTF），使用未优化的 VERIFIED Config D。
