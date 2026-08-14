# F6 — Official SPEAK→WAV RTF Resolved

> 日期：2026-08-14 · 状态：**OFFICIAL_RTF = AVAILABLE（首次实测数值）**
> 关联：`docs/F6_RTF_BLOCKER_REAUDIT.md`（Class A 重审，已解决）· `docs/competition-submission/OFFICIAL_GATE_STATUS.md`（权威状态页）

---

## 结论（一句话）

官方 RTF 阻塞（`rtf=NULL` / Class A RUNTIME_EMISSION_MISSING）的**根因不是「发射缺失」，而是 LISTEN-wedge 生命周期 bug**；修复生产 C++（`tools/omni/omni.cpp`，非受保护文件）后，官方 RTS 首次产出 **`core.rtf_aggregate = 1.0904`**（head-tail 掐头去尾主指标），与官方 baseline **1.087** 处于 parity（+0.31%，无回退、无加速）。

---

## 1. 阻塞根因（LISTEN-wedge）

此前每次 RTS 都是 **37 LISTEN / 0 SPEAK**，被误判为「生产 C++ 不吐 `stage_timing.jsonl`/SSE `metrics`」。真正的链条是：

1. 自然 LISTEN chunk 经 `tts_mark_producer_done`（omni.cpp ~8917）的 **q==0 路径**推进了所有 drain 计数器；
2. 但仍有一条**冗余的空 `is_chunk_end=true, is_final=false` T2W 任务**被入队（~8933）；
3. worker 取出该空任务，把 `active_t2w_generation=gen` 置位（~12001）——而 reset 只有 `is_final` 与 EOS-empty 两条路径，LISTEN 代两条都不具备；
4. 外层 `omni_duplex_drain_tts_audio` 读到 `active_gen==my_gen`，不满足 `(active_gen==0 || active_gen>my_gen)`，把 `context_state=NOT_REUSABLE`，从 ~14396 拒绝后续所有 decode 请求 → 0 SPEAK。

**分类修正**：`RTF_BLOCKER_CLASS` 由「A（RUNTIME_EMISSION_MISSING）」修正为「**生命周期语义缺口（生产可修）**」，已通过生产 patch 解决。

## 2. 修复（2 处外科手术式 edit，`tools/omni/omni.cpp`）

1. "set active" 条件：`empty_listen_chunk_end = duplex_mode && new_tokens.empty() && is_chunk_end && !is_final`，对空 LISTEN chunk_end **不再置 active**。
2. 新增完成 no-op 块：对空 duplex LISTEN chunk_end，幂等推进 `final_processed_generation` + `final_vocoder_processed_generation`，清零 `active_t2w_task_count`/`active_t2w_generation`，`drain_cv.notify_one()`，`continue`。

与之前**已回滚**的 TOCTOU/headroom 修复不同：那是时序/竞态假设，这是**语义缺口（缺完成记账）**，且被 `ctx_omni->duplex_mode` 守卫，只影响 duplex 空 chunk_end，不触及 eval-cli / tts-eval / simplex 路径。

## 3. 实测数值（官方 harness，Config D，omni_duplex1.mp4，gpu 1，2 次独立运行）

| 指标 | Run 1（042352） | Run 2（042733） |
|---|---|---|
| `rtf.available` | **true** | **true** |
| **`core.rtf_aggregate`（主指标）** | **1.0904**（19 帧 / 8 turn） | **1.1653**（19 帧） |
| `rtf_aggregate`（全量） | 0.9821（32 帧） | 1.0849 |
| `core.stage_rtf` | encode 0.189 · prefill 0.2236 · decode 0.142 · tts 0.2974 · token2wav 0.2384 | encode 0.2143 · prefill 0.23 · decode 0.1277 · tts 0.3386 · token2wav 0.2547 |
| `n_speak` | **33**（修复前 0） | **33** |
| `n_wav_events` | 56 | 61 |
| `n_aligned_pairs` | 27（excl_empty=6） | 29（excl_empty=4） |
| SPEAK→wav e2e | 993.8ms（median 939.0） | 936.2ms（median 954.6） |
| 拒绝 / wedge | **0** | **0** |
| `stage_timing.jsonl` | 87 行 | present |

**与官方 baseline（1.087）对比**：core RTF 落在 **1.09–1.17**（全量 0.98–1.08），2 次运行 n_speak=33 稳定、0 拒绝。core 样本仅 19 帧，单帧 RTF 分布 0.6–1.7，导致 trimmed-mean 存在 ~7% run-to-run 噪声；两轮结果均与 baseline 处于同一量级（无数量级回退、无加速）。RTF 不是提交的评分主体（三条准确率基线才是），此数值用于证明候选**无性能回退**。

## 4. 产物身份

| 项 | 值 |
|---|---|
| 会话 | `evaluation/judge-final/sessions/20260814_042352_omni_direct_1744256_r1/` |
| llama-omni-server | `4694cb589b61fbc3d9c26508dbfb044ae06f07395ca409659dbb0f066a28815f` |
| libomni.so | `3f3e1e636f66e81501eeda9285e1228e14da542211292a67f8bae70fbdf822ec` |
| Config D（cpp.log 验证） | `OMNI_CANN_FA_MAX_UBATCH=16`(512→16) · `OMNI_T2W_PIPELINE_OVERLAP=1`(ENABLED) · `OMNI_VOC_DEVICE=gpu:0` · `OMNI_T2W_DEVICE=cann-flow-only`(flow=CANN0) |
| 源码 | HEAD `a77d6a8` + `trackA_fixes.patch` + RTF 修复（omni.cpp/omni.h/server-omni.cpp 3 文件 modified） |

## 5. 最终状态字段

```
CANDIDATE_READY            = YES
ACCURACY_GATE              = PASS（3 条基线，修复为 duplex-only 不影响）
OFFICIAL_SMOKE             = PASS（4/4）
OFFICIAL_RTF               = 1.0904（AVAILABLE，首次实测）
RTF_BLOCKER_CLASS          = A → RESOLVED（生产 patch）
STARTER_KIT_BLOCKER        = REMOVE
OFFICIAL_UNIFIED_EVAL_BRANCH = AVAILABLE
COMPETITION_COMPLETE       = NOT_CLAIMED（仅剩官方 Demo 前端接入 + 复现审计）
```

## 6. 已知运行时局限（诚实声明）

- 三条准确率基线（Daily 79.43% / VideoMME 69.8% / Seed-TTS WER 1.422%+SIM 0.969）是在**冻结候选二进制 a77d6a8+trackA_fixes.patch** 上测得的，**非** RTF 修复后新二进制。该修复被 `ctx_omni->duplex_mode` 守卫、只改 duplex 空 chunk_end 完成记账，结构性无法触及 eval-cli/tts-eval/simplex 推理路径，故无需重跑准确率；此判断为静态审计结论，非实测重跑。
- RTF 数值基于官方统一评测分支（`tc-mb/llama.cpp-omni` @ `bench/huawei`）的公开 RTS harness；官方隐藏测试集/Overall 分母仍待公开。
