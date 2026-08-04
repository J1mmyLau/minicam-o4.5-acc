# F6 Phase 3 — 最终口径（T8）

**日期**: 2026-08-04
**状态**: 内部工作全部完成；外部（官方）结果一律不宣称。
**候选**: 最终集成候选 = **FINAL**（T5 freeze + T6 回归全过）。
**二进制**: `llama-omni-server` `e77b43c3…` + `libomni.so` `f1d2f86d…` @ HEAD `460a1fd`
**硬件**: 1× Ascend 910C (dual-die)，CANN 9.1.0-beta.1，单卡

---

## 1. 一句话结论

F6 阶段三的**内部优化与验证链全部闭环**：瓶颈定位 → 设备放置修正 → 最终集成候选
（KV Cache + HTTP token cap + 生命周期 + CANN Flow/Vocoder）→ 11/11 回归 Gate 全过。
**冻结候选无法通过 HTTP 返回可读文本答案（SSE 崩溃 + 非流式无文本），因此
Daily-Omni 准确率等官方质量 Gate 在本候选上无法评测（BLOCKED_BY_CANDIDATE_LIMITATION）。
任何 OFFICIAL_BENCHMARK_PASS / COMPETITION_COMPLETE 均不宣称。**

---

## 2. 完成内容（T1–T7）

| 任务 | 结果 |
|------|------|
| T1 统一状态文档 | S13_FROZEN_STRICT_BASELINE=PASS_120_OF_120 |
| T2 baseline 设备口径审计 | CPU T2W = 默认回退 + 实测参考 baseline；候选 = DEVICE_PLACEMENT_CORRECTION |
| T3 严格事件关联 | 埋点实现（round_idx/gen/reqidx），全渠道一致 |
| T4 严格复核 | 20 对 / 19 active，T2W-only delta 19/19 全负（p50 −4215.8ms） |
| T5 最终集成候选冻结 | KV + CANN T2W + 生命周期 组合，binary e77b43c3 |
| T6 最终集成回归 | **11/11 Gates PASS, ACCEPT=True** |
| T7 质量/比赛 Gate 评估 | 输入 CONFIRMED（修正协议）；输出 BLOCKED（候选限制） |

---

## 3. 权威 Gate 矩阵（最终）

| Gate | 判定 |
|------|------|
| S13_FROZEN_STRICT_BASELINE | **PASS_120_OF_120**（err=0, runaway=0, prompt_modified=0） |
| R13_STATIC_PREFIX_PREFILL | **PASS**（30/30, prefill 2.4×: 206→85ms p50） |
| R13_STATIC_PREFIX_E2E | **PASS**（30/30, prefill 2.5×） |
| PHASE2_BOTTLENECK_ANALYSIS | **PASS**（decode→speak=2.9%, T2W CPU=93%） |
| CANN_T2W_CANDIDATE | **STRONG_INTERNAL_PASS**（W0 4798→894ms, −81.4%） |
| BASELINE_DEVICE_PLACEMENT_AUDIT | **PASS** |
| T4_STRICT_CANN_T2W_REVERIFY | **PASS**（19/19, T2W-only delta 全负） |
| T6_FINAL_INTEGRATED_REGRESSION | **PASS（11/11）**：S13 120/120、Extended 30/30、Voice 5/5+隔离、Disconnect 5/5+followup、KV A/B 30 对/27 valid（3 对按预声明 A_ERR/B_ERR 排除，机制 30/30，Δ119.7ms, 2.44×）、3 重启、0 CPU fallback、0 CANN error |
| **FINAL_INTEGRATED_CANDIDATE** | **FINAL** |
| OFFICIAL_ACCURACY | **PENDING_REVERIFY_AFTER_T9**（T9 已修复非流式 text 字段 + SSE 崩溃；BLOCKED_BY_CANDIDATE_LIMITATION 已过时 → 待 Daily-Omni pilot 复核） |
| OFFICIAL_BENCHMARK | **PENDING_REVERIFY_AFTER_T9**（T9 修复后待官方 Harness 复核）+ 接口 provisional |
| COMPETITION_COMPLETE | **NOT_CLAIMED** |

---

## 4. 候选真实边界（诚实披露，不伪造）

### 已验证（内部回归范围）
- 单请求 simplex；120 冻结 + 30 扩展 + 5 切音色 + 5 断连 + 3 重启
- KV cache MISS→HIT prefill 2.44×（30 对/27 valid，机制 30/30），无正确性回归
- CANN T2W 设备放置（环境变量切换），0 CPU fallback / 0 CANN error
- 用户图像/音频/文本输入经**修正协议**（两次 prefill）确认可用

### 未验证 / 已确认受限（不伪造）
| 边界 | 性质 |
|------|------|
| Daily-Omni 准确率（需文本答案字母） | **BLOCKED**：非流式 decode 无 text 字段；SSE decode 崩溃（std::bad_alloc, 2/2 可复现） |
| seed-tts-eval | **PENDING_EXTERNAL_ASSETS**：测试集在 Google Drive，不可达 |
| 比赛提交接口 | **PENDING_EXTERNAL_ASSETS**：METRIC_CONTRACT 全项“待官方确认” |
| SSE 流式路径 | **候选缺陷 F7-1**：崩溃服务器（T6 从未测 stream:true） |
| 双工（duplex）模式 / WS | 未验证（benchmark_client WS adapter 为 placeholder） |
| 并发多请求、多卡、其他量化档位 | 未验证 |

---

## 5. 最终口径

1. **FINAL_INTEGRATED_CANDIDATE = FINAL** — 内部优化与回归闭环，可交付内部报告。
2. **OFFICIAL_ACCURACY / OFFICIAL_BENCHMARK / COMPETITION_COMPLETE = 不宣称 PASS**。
   失败/阻塞原因如实记录（候选文本输出限制 + 外部资产缺失），无任何伪造。
3. 修正协议（两次 prefill）与 SSE 崩溃（F7-1）为 T7 实测发现，已完整记录于
   [T7 评估](T7_QUALITY_GATES_ASSESSMENT.md)。
4. 若后续需推进官方 Gate：修复 SSE 文本输出路径（需解冻 → 重建 + 重 SHA + 重跑 T6）
   或采用音频+ASR 变通（whisper，非官方偏差）。

---

## 6. 交付物索引

| 交付物 | 路径 |
|--------|------|
| T5 冻结文档 | `docs/F6_PHASE3_T5_FINAL_INTEGRATED_CANDIDATE.md` |
| T6 回归报告 | `docs/f6-s13-closure/phase2/T6_INTEGRATED_REGRESSION_REPORT.md` |
| T6 证据 JSON | `docs/f6-s13-closure/phase2/t6_integrated_regression.json` |
| T7 质量 Gate 评估 | `docs/f6-s13-closure/phase2/T7_QUALITY_GATES_ASSESSMENT.md` |
| 任务状态 | `docs/tracking/TASKS.md` / `docs/tracking/AUDIT.md` / `STATUS.md` |

---

## 附录 T9 — 接口修复（2026-08-04，用户 P0 指令）

T8 之后按用户 P0 指令解冻 server 修复文本输出接口。**libomni.so 保持冻结 `f1d2f86d`**
（核心 omni 库未动），server 由 `e77b43c3` → `594920b6`（三处修复见
[T7 附录](T7_QUALITY_GATES_ASSESSMENT.md#附录-t9--接口修复2026-08-04用户-p0-指令)）。

**媒体协议实测（PASS）**：frame+audio+question 输入 → 非流式 `text` 字段 748/1088 字符
（两轮常驻复用，未再 reject）；SSE 干净 `[DONE]` 不崩溃不挂起（F7-1 根治）。
**T6 重跑验证中**（frozen discipline）。此修复不改变 T8 的内部优化结论；官方 Gate 判定
仍遵循诚实口径（官方 harness/接口未定前不宣称 OFFICIAL_BENCHMARK_PASS / COMPETITION_COMPLETE）。
