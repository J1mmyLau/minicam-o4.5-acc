# Official Gate Matrix — llama.cpp-omni 子赛道

> 依据官方赛事规则建立。通过顺序: Framework → Accuracy → Demo → Performance → Reproduction。
> 精度和 Demo 属于**准入条件**，不通过则不进性能评测。

---

## 测评流程

```
G1 框架与环境检查
        ↓
G2-G4 三项 Benchmark 精度（降幅 ≤ 2pp）
        ↓
G5 官方 Demo 端到端稳定可用
        ↓
G6 每 audio chunk RTF
        ↓
G7 工程复现审查
        ↓
G8 最终提交
```

**仅能运行 Benchmark、但无法正常接入 Demo 的方案，不满足本赛道准入条件。**

---

## 正式 Gate 矩阵

| ID | Gate | 赛事要求 | 所需资产 | 脚本 | 原始输出 | 汇总 | 当前状态 | 阻塞原因 | 通过条件 |
|----|------|---------|---------|------|---------|------|---------|---------|---------|
| **G1** | Framework & Environment | 在官方昇腾环境部署 llama.cpp-omni | 官方硬件/镜像/CANN | `submission/scripts/start_server.sh` | — | — | `INTERNAL_PASS` | — | 官方环境可复现 |
| **G2** | Daily-Omni Accuracy | 精度 vs 官方 baseline，降幅 ≤ 2pp | 官方 Daily-Omni benchmark + 数据 | `submission/scripts/run_daily_omni.sh` | — | — | `NOT_RUN` | BLOCKED_BY_OFFICIAL_STARTER_KIT | 降幅 ≤ 2pp |
| **G3** | TTS-Seed Accuracy | 精度 vs 官方 baseline，降幅 ≤ 2pp | 官方 TTS-Seed benchmark + 数据 | `submission/scripts/run_tts_seed.sh` | — | — | `NOT_RUN` | BLOCKED_BY_OFFICIAL_STARTER_KIT | 降幅 ≤ 2pp |
| **G4** | Video-MME Accuracy | 精度 vs 官方 baseline，降幅 ≤ 2pp | 官方 Video-MME benchmark + 数据 | `submission/scripts/run_video_mme.sh` | — | — | `NOT_RUN` | BLOCKED_BY_OFFICIAL_STARTER_KIT | 降幅 ≤ 2pp |
| **G5** | Official Demo | 接入 MiniCPM-o-Demo，完整端到端稳定交互 | MiniCPM-o-Demo 前端 + 素材 | `submission/scripts/run_demo_gate.sh` | — | — | `NOT_RUN` | 官方 Demo 资产未到位 | D1-D12 全部 PASS |
| **G6** | Per-chunk RTF | 每 audio chunk RTF（统一硬件/环境/模型/数据/脚本） | 官方 benchmark harness | `submission/scripts/run_chunk_rtf_client.py` | — | — | `NOT_RUN` | BLOCKED_BY_OFFICIAL_STARTER_KIT | RTF < 1.0（实时） |
| **G7** | Engineering Reproduction | 官方在官方环境重新部署并复现全部结果 | 完整代码/配置/脚本/文档/视频 | `submission/scripts/` (全部) | — | — | `PARTIAL_READY` | G2-G6 需先通过 | clean-room 复现一致 |
| **G8** | Final Package Review | 按要求提交全部材料 | 完整 submission 包 | — | — | — | `NOT_READY` | G2-G7 需先通过 | 材料完整、格式合规 |

---

## 内部 Gate 矩阵（已完成）

| ID | Gate | 结果 | n | 证据 |
|----|------|------|---|------|
| T6 | 集成回归 | 11/11 PASS | S13 120 + Extended 30 + Voice 5 + Disconnect 5 + KV A/B 28/30 + Smoke 5 | [`T6_INTEGRATED_REGRESSION_REPORT.md`](../f6-s13-closure/phase2/T6_INTEGRATED_REGRESSION_REPORT.md) |
| R13 | Static Prefix KV Cache | 30/30 PASS | 30 strict matched pairs | [`R13_CANONICAL_STATIC_PREFIX_AB_FINAL.md`](../../tracking/f6_lifecycle/R13_CANONICAL_STATIC_PREFIX_AB_FINAL.md) |
| P6 | CANN T2W A/B | 32/32 PASS | 32 strict matched pairs | [`F6_PHASE2_STEP6_CANN_T2W_AB.md`](../F6_PHASE2_STEP6_CANN_T2W_AB.md) |
| C6 | Persistent Lifecycle | PASS | 3 sequential requests | [`F6_C6_PROFILE_LIFECYCLE_STATE_MACHINE.md`](../../tracking/F6_C6_PROFILE_LIFECYCLE_STATE_MACHINE.md) |
| T13 | TTS KV Bounds | PASS | 1 boundary test | F6 T13 tracking |
| T9 | Text + SSE Fixes | PASS | — | F6 T9 tracking |

---

## 状态汇总

```
FINAL_INTERNAL                       = PASS
REPRODUCIBLE_BINARY                   = PASS
INTERNAL_HANDOFF_READY                = YES

OFFICIAL_DAILY_OMNI                  = NOT_RUN
OFFICIAL_TTS_SEED                     = NOT_RUN
OFFICIAL_VIDEO_MME                    = NOT_RUN
OFFICIAL_DEMO_GATE                    = NOT_RUN
OFFICIAL_CHUNK_RTF                    = NOT_RUN

OFFICIAL_GATES                       = BLOCKED_BY_OFFICIAL_STARTER_KIT
OFFICIAL_GATE_TOOLING_READINESS       = PASS
F6_OFFICIAL_SUBMISSION_PACKAGE        = NOT_READY
COMPETITION_COMPLETE                  = NOT_CLAIMED
```

**最终比赛成绩以主办方在官方硬件、镜像、Starter Kit 和测试脚本中重新部署并复现得到的结果为准。**
