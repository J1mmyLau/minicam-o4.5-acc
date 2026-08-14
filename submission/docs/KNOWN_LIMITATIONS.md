# 已知限制（提交物）

## 候选级限制（`fd3dd36`，tag `competition-final-20260814`）

- **SPEAK turn 楔死（context_state=3）**：候选 per-chunk drain 语义，SPEAK turn 残留 TTS
  （flow+vocoder）超过 5s 默认超时（`t2w_get_drain_timeout_ms` = 5000 + pending×15000）时，
  谓词在超时边界触发 → handler 置 `context_state=3`（NOT_REUSABLE）→ 拒绝后续请求。
  两次修复（TOCTOU 返回 bool / producer 活跃 +60s 头room）均失败或回归（后者纯 LISTEN gen
  谓词永不满足致挂起），已逐字回滚。证据：`docs/F6_TRACK_B_RTS_RTF_EVIDENCE.md`。
- **官方 SPEAK→WAV RTF 已恢复（core.rtf_aggregate 1.09–1.17，parity baseline 1.087）**：
  LISTEN-wedge 生命周期 bug 已修（`tools/omni/omni.cpp` 生产 patch，非受保护）——
  空 duplex LISTEN chunk_end 未完成 drain 记账 → active_gen 楔死 → NOT_REUSABLE 拒绝。
  修复后 n_speak 0→33，0 拒绝。见 `docs/F6_OFFICIAL_RTF_RESOLVED.md`。
  ⚠️ 诚实口径：RTF 可用（1.0904/1.1653），但**无相对 1.087 的已证实加速**；Config D 的
  ~18% wall 改善是本地配对 A/B（`docs/F6_*`），**不是** official RTF −18%。

## 模型能力限制（非服务器 bug）
- **whisper 音频编码上限 ~24-26s**：超过该时长的输入音频可能输出 `?`×256。Daily-Omni 官方 29.5s 音频即触发。
  证据：`docs/f6-s13-closure/phase2/daily_omni_pilot/`（threshold.json）。

## 服务器已知边界
- **SSE + use_tts=True 的 T2W drain 未接入**：SSE 流式路径无 omni_duplex_drain_tts_audio；非流式路径完整。
- **KV A/B 28/30 valid**：2 对（C2-R2 / C5-R3）为 decode POST 客户端 HTTP 异常（A_ERR 预声明排除），
  机制层 30/30 正常；R13 canonical 30/30 官方速度结论不受影响。
- **无音频 drain stall 罕见边界**：极少数无音频响应会触发有界超时（自恢复），本轮干净运行 0 次。

## 优化边界
- B6b（机械提前触发 Talker）冻结为 OFF：无稳定收益（决策记录 REJECT）。
- FA Q-split 源码默认 `16 → 0`（OFF，trackA_fixes.patch）；长多模态 NaN 由
  `OMNI_CANN_FA_MAX_UBATCH=16` 保护（+5.3% 开销，唯一可靠 workaround）。
- flow ACL graph capture（`GGML_CANN_FLOW_ACL_GRAPH`）冻结为 OFF（E2E 净损 +11%）。
