# README — Official RTF Attribution Experiment

> **BASE** = `fd3dd36` (= tag `competition-final-20260814`, = `fd3dd36870f60829e47cafffacc7027cf8eb21d4`)
> **BRANCH** = `perf/official-rtf-attribution`
> **WORKTREE** = `/workspace/llama.cpp-omni-official-rtf`
> **GOAL** = explain local Config-D wall gain (−81% T2W / −18% wall) vs official RTF parity (1.09–1.17 vs baseline 1.087)
> **OWNER** = gfh
> **STATUS** = EXPERIMENTAL
> **CURRENT_HYPOTHESIS** = Config-D 的局部收益被 `queue/drain` 或 Flow↔Vocoder contention 吃掉，导致官方 numerator 不降、RTF 持平

> ⛔ **DO_NOT_MERGE_TO_COMPETITION_FINAL** — 本分支是隔离实验，只做 attribution，不污染 `competition/final-ascend-track-a` 的 frozen `fd3dd36`。promotion 到 final 需单独决策。

---

## 0. 已纠正的旧结论（STALE → CORRECTED）

不要沿用以下过期结论，否则会按错误认知继续干：

| 旧结论（作废） | 现状（事实） |
|---|---|
| official eval `BLOCKED_BY_STARTER_KIT` | 已删此 blocker，official RTF 可测 |
| CANN vocoder = zero output 未解决 | Config D 已验证 **Flow CANN + Vocoder CANN + overlap** 正常出 WAV |
| 官方 harness 固定 gpu，`cann-flow-only` 映射不到 official | Config D 可通过外部 env 合法注入 official harness |
| LLM decode 13% + T2W 93%（当加法 wall 占比用） | 两者相加 >100%，混了不同计时边界 —— **先做 attribution reconciliation，不得直接拿来算 Amdahl** |

---

## 1. 实验配置（A vs D，其余参数完全一致）

| | 拓扑 |
|---|---|
| **A**（保守/reference） | 默认 runtime topology |
| **D**（Config D） | `OMNI_T2W_DEVICE=cann-flow-only` + `OMNI_VOC_DEVICE=gpu:0` + `OMNI_T2W_PIPELINE_OVERLAP=1` |

阶段一 **不改任何性能代码**，只在官方 RTS 路径上复现 A 与 D。

## 2. 严格 paired A/B（交替序，≥6 对，最好 8–10 对）

```
A1 → D1 → D2 → A2 → A3 → D3 → D4 → A4 ...
```

> 不并发跑 NPU benchmark。只跑 A 一遍 / D 一遍会淹没 ~5% 的优化（两次 official core RTF 自身可差 ~7%：1.0904 vs 1.1653）。

每轮记录：

```
core.rtf_aggregate          full rtf_aggregate          n_speak
official numerator          official denominator / audio duration
main_decode_ms              talker_decode_ms             t2w_encoder_ms
flow_ms                     vocoder_ms
queue_wait_ms               drain_ms
speak_to_first_wav_ms       speak_to_final_wav_ms
NaN / Inf / errors
```

## 3. 逐段 wall 对齐（产出最值钱的一张表）

```
stage           A_median   D_median   Δ    included_in_official_RTF?
Main LLM        ...        ...        ...   ?
SPEAK decision  ...        ...        ...   ?
Talker          ...        ...        ...   ?
T2W encoder     ...        ...        ...   ?
Flow            ...        ...        ...   ?
Vocoder         ...        ...        ...   ?
queue/drain     ...        ...        ...   ?
audio output    ...        ...        ...   ?
```

→ 明确回答：本地 T2W 改善、Config-D ~−18% wall，**为什么没有出现在 official RTF**。无实测 timestamp 不得臆测。

## 4. 四种可能（按证据落点决定下一刀）

1. **D 在 official numerator 上其实也快，但 denominator 变了** → 查 generated audio duration / `src_cnt` / SPEAK selection / 不同 run 的 turn composition（**指标统计/样本组成问题**，不是优化没生效）。
2. **Flow/Vocoder 自己快，但 Talker 或 queue/drain 变慢** → `Flow −60 / Vocoder −80 / queue+drain +120 / Talker +30` → E2E +10。下一刀切 queue/overlap/contention，不切 kernel。
3. **Flow 因与 Vocoder 同卡竞争膨胀**（已知先例：Flow serial ≈145ms vs Config D ≈202ms）→ 重测 `Flow alone / Vocoder alone / serial / overlap`，画真实 timeline，算 `OVERLAP_SAVED / CONTENTION_COST / NET_GAIN`。
4. **官方主指标样本太少，优化被噪声淹没** → local paired wall 稳定 −15%，official core RTF median 仅 −2%、CI 跨 0 → 结论：优化真实但官方主指标样本/计时边界无法稳定兑现。

## 5. 优先级（根因明确后）

```
1. official attribution / timing reconciliation
2. Flow↔Vocoder contention
3. queue / drain / overlap scheduling
4. Flow host/build overhead
5. 才考虑新 kernel/graph
```

## 6. 明确不做

- ❌ 不重试 **Flow ACL-graph** 旧方案（已证 negative：Flow p50 −20.4% 但 E2E +11%）。
- ❌ 本分支不做 **DSpark**（另一分支，且 main decode 不是 official RTF 的主战场）。
- ❌ 不动 **quantization**，除非新 profile 抬升它。

## 7. Promotion rule（新 runtime patch 是否保留）

保留条件（全部满足）：
- valid text + valid WAV + 0 NaN/Inf + 无 lifecycle 回归
- **paired official RTF 一致改善**（median + 多数/全部有效对同向）
- 局部 stage 加速**单独不算数**；official gain <3% 且落在 run-to-run 噪声内 → **DO NOT SHIP**

## 8. 最终报告

写 `docs/perf/OFFICIAL_RTF_ATTRIBUTION.md`，字段：

```
BASE_SHA / BRANCH
A_PAIRS / D_PAIRS
A_CORE_RTF_MEDIAN / D_CORE_RTF_MEDIAN / OFFICIAL_RTF_DELTA
LOCAL_T2W_DELTA / OFFICIAL_NUMERATOR_DELTA / DENOMINATOR_DELTA
MAIN_DECODE_DELTA / TALKER_DELTA / FLOW_DELTA / VOCODER_DELTA / QUEUE_DRAIN_DELTA
FLOW_VOC_CONTENTION
LOCAL_OFFICIAL_GAP_ROOT_CAUSE
NEXT_OPT_TARGET
PATCH_SHIPPABLE = YES / NO
```
