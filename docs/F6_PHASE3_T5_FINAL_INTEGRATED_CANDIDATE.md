# F6 Phase 3 — T5: FINAL_INTEGRATED_CANDIDATE 冻结

> Status: **INTERNAL_PASS** — freeze 已建立；`FINAL_INTEGRATED_CANDIDATE = INTERNAL_PASS`
> 待 T6（最终集成回归）全绿后冻结为 FINAL。
>
> ⚠️ 诚实口径：此文档只声称**内部集成候选**冻结与各组件已通过的门禁。
> 不写 `OFFICIAL_ACCURACY_PASS` / `OFFICIAL_BENCHMARK_PASS` / `COMPETITION_COMPLETE`
> —— 这些仍 PENDING，需官方 Harness + 质量门禁（T7/T8）。

## 1. 候选定义（FINAL_INTEGRATED_CANDIDATE）

组合：「KV Cache 静态前缀复用 + HTTP token cap + 持久上下文生命周期 + CANN Flow/Vocoder 设备放置」
+ T3/T4 严格事件关联埋点。

### 1.1 二进制（Freeze 时点）

| 对象 | SHA256 | 来源 |
|------|--------|------|
| `build/bin/llama-omni-server` | `e77b43c31d3c575da63a519e956810081f2a5c76bbf9157e01a196f0faab0dd8` | HEAD `b043257`（b043257 = T4 commit） |
| `build/bin/libomni.so` | `f1d2f86dafcf2edaff4ab65cba503e5c58fca42ffd397cabe379f9efb3cf252f` | 同上 |

> 冻结后二进制必须逐字节一致；任何重建都需更新本表并重跑 T6。

### 1.2 模型与启动

```bash
build/bin/llama-omni-server -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf \
  -ngl 999 --device CANN0 -c 4096 -b 512 -ub 512 --split-mode layer --port 18094
```

### 1.3 环境变量（候选语义 = 全 ON）

| 变量 | 值 | 组件 | 语义 |
|------|----|------|------|
| `OMNI_KV_CACHE_REUSE` | `1` | KV Cache | 静态前缀 prefill 命中复用（R13 canonical，omni.cpp:196） |
| `OMNI_T2W_DEVICE` | `cann-flow-only` | CANN T2W | Flow Matching 走 CANN（worker 线程内后端，omni.cpp:5577） |
| `OMNI_VOC_DEVICE` | `gpu` | CANN T2W | Vocoder 走 CANN GPU（omni.cpp:5611/5630） |
| `ASCEND_RT_VISIBLE_DEVICES` | `0` | 硬件 | 单卡 Ascend910C（dual-die） |
| `OMNI_E2E_PROFILE` | `1` | 埋点 | e2e 分阶段 JSON（T3） |
| `OMNI_PIPELINE_TRACE` | `1` | 埋点 | pipeline_trace CSV（T3） |

### 1.4 请求协议（持久上下文）

1. **`/v1/stream/omni_init` 恰好一次**（`msg_type=1, media_type=1, use_tts=true`）。
   注意：`omni_init` 每次调用会 free+recreate context（server-omni.cpp:313-319），
   重复调用会重置 e2e_stage → 破坏关联。候选协议=**一次 init，后续复用**。
2. 每请求：`/v1/stream/prefill`（audio_path_prefix + text）+ `/v1/stream/decode`。
3. decode 必须带 per-request cap：`max_tokens=256, wall_timeout_ms=300000`
   （HTTP token cap，防 runaway）。
4. simplex、`USE_TTS=true`、流式 off（`stream:false`，响应携带 runtime evidence）。

### 1.5 冻结约束（不得改动）

- `CHUNK_SIZE = 25`（冻结）
- `B6b = OFF`（冻结）
- MTP = OFF（模型不可达）
- 模式：simplex（duplex 不在验证范围内）

## 2. 组件来源（commit chain）

| 组件 | 实现 commit | 验证 |
|------|-------------|------|
| KV Cache 复用（R13 canonical） | `f298c10` + omni.cpp `OMNI_KV_CACHE_REUSE` | R13_CANONICAL_KV_CACHE 30/30 PASS（prefill 2.4×，206→85ms p50） |
| 静态前缀 KV A/B + 首音 | R13（`ec6dbc7` per-gen active 等） | R13_CANONICAL_KV_CACHE / R13 E2E 30/30 PASS |
| HTTP token cap | `3f130c1` | S13_FROZEN_STRICT_BASELINE PASS_120_OF_120（eos=111, max_tokens=9, 0 runaway） |
| 持久上下文生命周期 | `91bbcc9`（drain-before-stop 状态机）+ `ec6dbc7`（per-gen active） | P7.3 150/150 rc0_without_audio=0；R13 生命周期 100% IDLE→…→IDLE；F6 生命周期修复（3 顺序 decode 通过） |
| CANN Flow/Vocoder 设备放置 | `3fc0ed5`（worker 线程内 CANN）+ `0828de2`（fail-fast）+ 环境开关 | CANN_T2W_CANDIDATE STRONG_INTERNAL_PASS（P2S6 32/32, W0 4798→894ms）；**T4 19/19 correlation + T2W-only delta 全负** |
| T3 请求级事件关联埋点 | `510a9f0` | T3 smoke + T4 FULL 19/19 全渠道 value-bound 一致 |
| T4 wav_count 修复 | `b043257`（is_final 不再提前 last_round_idx） | T4 wav_count gate 19/19 |

## 3. 已通过门禁汇总（组件级，均为实测）

```text
S13_FROZEN_STRICT_BASELINE        = PASS_120_OF_120   (120/120, eos=111, max_tokens=9, 0 err/timeout)
R13_STATIC_PREFIX_PREFILL         = PASS              (30/30, prefill 2.4×)
R13_STATIC_PREFIX_E2E             = PASS              (30/30 first-audio, prefill 2.5×)
R13_CANONICAL_KV_CACHE            = PASS              (30/30, 130 tokens reused, 0 collision)
R13_LIFECYCLE                     = PASS              (3 sequential decode, ctx 保持有效)
P7.3_DRAIN                        = PASS              (150/150, 0 rc0_without_audio)
CANN_T2W_CANDIDATE                = STRONG_INTERNAL_PASS (W0 4798→894ms, −81.4%, 32/32)
T4_STRICT_CANN_T2W_REVERIFY       = PASS              (19/19 correlation, T2W-only delta 全负)
```

## 4. 组合级状态（候选，未经 T6 回归不得宣称 FINAL）

```text
FINAL_INTEGRATED_CANDIDATE = INTERNAL_PASS   ← 组件组合已冻结，待 T6
OFFICIAL_ACCURACY          = PENDING
OFFICIAL_BENCHMARK         = PENDING
COMPETITION_COMPLETE       = NOT_CLAIMED
```

## 5. 未验证边界（诚实披露，T6 覆盖一部分，官方 Harness 覆盖其余）

- duplex 模式（候选只验证 simplex）
- 多并发 / 多请求并发（本门禁为顺序请求）
- 其他模型 / 其他量化
- 官方 Harness 的精度/质量对照（T7 外部资产缺失 → PENDING_EXTERNAL_ASSETS）
- 长时间 soak（6h+）作为单独 P2 项 defer

## 6. 再冻结规则

- 任何源码变更 → 需重建 + 重算 SHA + 重跑 T6，否则不得沿用本冻结编号。
- 冻结证据锚点：本文件 + `docs/f6-s13-closure/phase2/t4_strict_cann_t2w.json` +
  T6 回归报告（T6 完成后追加）。
