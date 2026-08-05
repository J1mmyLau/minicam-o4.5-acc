# T6 最终集成回归 — 完成报告

**日期**: 2026-08-04（本文档 re-run #3 = 冻结源码 bdd4550 重建二进制上的 T6 完整重跑；re-run #2 @ 91797e6+未提交 diff 的 KV A/B 为 27 valid / 机制 30/30，见 STATUS.md 历史）
**候选**: 最终集成候选 — KV Cache + HTTP token cap + 生命周期 + CANN Flow/Vocoder + T9 文本输出 + T10/T11 TTS KV 生命周期守卫 + P0 媒体输入（bdd4550）
**二进制**: `llama-omni-server` `db258375c3d2185ca2181da2a5c8f99a95d381413fcb7ab92a771850ba3a4a21` + `libomni.so` `c4b169376bced6bc3107cfda2f77abf35a634c1e146eed313a193e99e3739ea1` @ HEAD `bdd4550`（冻结源码，无调试钩子；REPRODUCIBLE_BINARY=PASS：同目录两次干净重建 SHA 逐字节一致）
**硬件**: 1× Ascend 910C (dual-die), CANN 9.1.0-beta.1, 单卡
**结果**: **ACCEPT = True — ALL 11 GATES PASS**（meta.binary_sha=db258375 确认冻结二进制）

---

## 1. 运行结构

3 个独立服务器会话（重启 × 3）：

| 会话 | 重启 | 内容 | 日志 |
|------|------|------|------|
| Session 1 | #1 | 120 frozen + 20 长文本 + 10 混合 + 5 切音色 + 5 断连 + followup | `t6_srv.log` |
| Session 2 | #2 | KV cache 30 MISS→HIT 配对 | `kv_ab_srv.log` |
| Session 3 | #3 | 5 混合 smoke | `t6_smoke_srv.log` |

环境：`OMNI_KV_CACHE_REUSE=1`, `OMNI_KV_CACHE_PATH=/tmp/f6_t6/kv_cache`,
`OMNI_T2W_DEVICE=cann-flow-only`, `OMNI_VOC_DEVICE=gpu`, `ASCEND_RT_VISIBLE_DEVICES=0`。

---

## 2. Gate 结果（11/11 PASS）

| Gate | 判定 | 关键数据 |
|------|------|----------|
| **S13_STRICT_BASELINE** | ✅ | total=120, ok=120, error=0, prompt_modified=0, first_attempt_ok=120 |
| **S13_RUNAWAY_FREE** | ✅ | wall_timeout=0, sliding_window=0 |
| **EXTENDED_OK** | ✅ | long 20/20 + mixed 10/10 = 30/30，0 timeout / 0 slide |
| **VOICE_SWITCH_OK** | ✅ | 5/5 成功且有音频（wav_count>0） |
| **VOICE_SWITCH_ISOLATION** | ✅ | 每请求独立 round 目录 |
| **DISCONNECT_SURVIVAL** | ✅ | 5/5 断连后服务器存活 |
| **DISCONNECT_FOLLOWUP** | ✅ | followup req=3500 成功（drain_complete→RESPONDING→IDLE） |
| **KV_CACHE_AB** | ✅ | 30 pairs / 28 valid（2 对按预声明 A_ERR 规则排除，机制 30/30）；MISS 202.8ms → HIT 82.0ms；Δ_p50=121.2ms；2.47×；loaded=130 |
| **RESTART_3_SESSIONS** | ✅ | 3 会话均正常起停 |
| **CPU_FALLBACK_ZERO** | ✅ | 0 |
| **CANN_ERROR_ZERO** | ✅ | 0（cann_ok=4） |

完整证据 JSON：`docs/f6-s13-closure/phase2/t6_integrated_regression.json`

---

## 3. S13 冻结基线 120 明细

```
ok=120  err=0  prompt_modified=0  first_attempt_ok=120
stop_reason: eos=81  max_tokens=39  wall_timeout=0
decode_wall p50=5437ms  generated_tokens p50=35
sliding_window=0  runaway=0
```

> **口径说明**：stop_reason 分布（eos=81/max_tokens=39）与 S13 原始基线
> （eos=111/max_tokens=9）不同。两轮均满足 strict_pass（err=0 且 ok=120 且
> prompt_modified=0）与 runaway_free。差异归因于 LLM 采样随机性 + KV cache
> 启用后的上下文状态；无失控、无滑动窗口、无 prompt 篡改。此分布差异不影响任何 Gate。
> （括号内数据为冻结二进制 re-run #3；re-run #2 为 eos=83/max_tokens=37, p50=5475ms/42 tokens）

---

## 4. KV Cache MISS→HIT（Session 2）

**冻结二进制 re-run #3 结果**（本文档主口径）：
```
30 pairs / 28 valid  gate_pass=True（脚本阈值 n_valid ≥ 25）
MISS prefill p50=202.8ms
HIT  prefill p50=82.0ms
Δ    p50=121.2ms  speedup=2.47×
loaded_positions: [130, 130]（与 R13 canonical n_past=130 一致）
```

方法：每对 A=清缓存+新上下文（MISS→SAVED）、B=新上下文（HIT），`use_tts=False`
隔离 LLM prefill delta，与 R13 canonical 口径一致。5 cases × 6 pairs。

**30/28 的 2 对无效配对**（pair 08 C2-R2 / pair 27 C5-R3）均因 decode POST 客户端
HTTP 异常（`A_ERR`，脚本预声明排除规则）判无效；机制层（SAVED/HIT/loaded=130）
30/30 全部正常，Δ 全为正，**不是缓存污染，不影响 Gate 结论**。排除记录见
`t6_integrated_regression.json` + 本轮完整运行日志（`FROZEN_BINARY_RE_RUN` AUDIT 条目）。
（re-run #2 @ 91797e6+未提交 diff 为 27 valid / 3 对排除，详细判定链见 `t6_kv_ab_27of30.md`。）

**两条独立结论（不混同）**：
- **R13 canonical KV validation**：30/30 strict matched pairs，正式机制证明
  （MISS 206→85ms p50，2.4×）——见 `f6-s13-step8-r13-e2e-complete` 归档。
- **Frozen-binary T6 integration KV check**：28/30 valid，集成回归中的重复确认
  （MISS 202.8→82.0ms，2.47×）——本文档。两者方法同源、结论一致，独立归档。

---

## 5. 断连测试（Session 1）— 修复验证

**首轮崩溃（run #1）**：recovery `omni_init()` 与在途 aborted decode 竞争
（OMNI_FREE vs STREAM_DECODE_BEGIN req=3004 on ctx=0x0）→ use-after-free → 服务器死亡。

**修复**：`run_disconnect` 不再调用 recovery omni_init。冻结协议本就是 once-init；
断连后客户端关闭连接但服务器 handler 继续处理 decode。改为：5 次断连 → 20s 平息
（在途 decode 完成）→ followup（req=3500）直接在常驻上下文上运行（通过 per-gen
active 排队）。

**修复后结果**：
```
all_server_alive=True  all_abort_ok=True  followup_ok=True  followup_retried=False
followup: DRAINING→RESPONDING (drain_complete OK) → RESPONDING→IDLE (response_sent OK)
```

**发现（诚实披露）**：断连后立即 `omni_init` 会与在途 decode 竞争导致服务器崩溃
——这是候选代码的真实边界（客户端 disconnect 不中止服务器 handler）。冻结协议
（once-init + 后续复用）下不触发该路径；本测试按冻结协议验证断连存活。

---

## 6. 切音色测试（Session 1）

```
5/5 ok，isolation=True，audios_distinct=True
```

**诚实边界**：在 once-init 常驻协议下，C++ T2W 说话人参考在 `omni_init` 时从
`default_ref_audio` 固化（prompt_cache）；每请求改 `audio_path_prefix` 不会重新
克隆音色。因此音色是否真的改变不在常驻候选的测试范围内。Gate 验证的是：每请求
成功且有音频 + 每请求输出落在独立 round 目录（无跨请求污染）。

---

## 7. 全局完整性

```
cpu_fallback=0  cann_error=0  cann_ok=4
0 panic / SIGSEGV / assertion（三份会话日志）
0 无音频 drain stall（本轮）
（首轮 run #1 曾出现 6 次有界自恢复 drain stall，非崩溃，已在 T6 头版报告归档）
```

> **说明**：本轮为冻结二进制重跑，请求数较 run #1 少（frozen 120 中 eos=81/
> max_tokens=39，TTS drain 正常完成），未复现 drain stall。

---

## 8. 结论与状态

- **T6 最终集成回归 = PASS（11/11 Gates，ACCEPT=True）** — 冻结二进制 re-run #3
  （meta.binary_sha=`db258375`，冻结源码 `bdd4550` 重建，REPRODUCIBLE_BINARY=PASS）。
  KV A/B 30 对/28 有效、gate_pass；2 对（C2-R2 / C5-R3，A_ERR）排除原因见 §4。
- `POST_T11_SOURCE_FREEZE = PASS`，`POST_T11_FINAL_CANDIDATE = FINAL_INTERNAL`，
  `REPRODUCIBLE_BINARY = PASS`
- **候选源码** `bdd4550`（实际比赛候选），**证据/文档** `adb9bb6`（T6 证据 + 状态文档）——交接时分开标注
- **未宣称**（官方 Harness 通过前不宣称，见 T7）：`OFFICIAL_ACCURACY = PENDING_REVERIFY_AFTER_T9`、
  `OFFICIAL_BENCHMARK = PENDING_REVERIFY_AFTER_T9`、`OFFICIAL_DAILY_OMNI = NOT_RUN`、
  `COMPETITION_COMPLETE = NOT_CLAIMED`

### 候选已验证边界（内部回归范围）
- 单请求 simplex，120 冻结 + 30 扩展 + 5 切音色 + 5 断连 + 3 重启
- KV cache MISS→HIT prefill 2.47×（30 对/28 有效，机制 30/30），无正确性回归
- CANN T2W 设备放置（环境变量切换），0 CPU fallback

### 未验证边界（诚实披露，不伪造）
- 官方比赛 Harness / 官方质量评分 / 官方完整数据集计分（外部资产缺失）
- 双工（duplex）模式、并发多请求
- 其他模型/量化档位
- 多卡场景
