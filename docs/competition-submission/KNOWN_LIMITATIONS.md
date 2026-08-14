# KNOWN_LIMITATIONS — 已知限制（权威）

> 候选 `fd3dd36` 的诚实限制清单。区分「候选级 bug」「模型能力上限」「优化边界」三类。

## 1. 核心诚实声明

- **官方 RTF 无已证实加速**：core.rtf_aggregate 1.09–1.17 = parity（baseline 1.087）。
  Config D 的 ~18% wall 改善是本地配对 A/B，**不是** official RTF 改善。见 `RESULTS.md` §2。

## 2. 候选级限制

- **SPEAK turn 楔死（context_state=3，候选级，非 Config D）**：候选 per-chunk drain 语义下，SPEAK turn
  残留 TTS（flow+vocoder）超过 5s 默认超时时，谓词在超时边界触发 → handler 置 `context_state=3`
  （NOT_REUSABLE）→ 拒绝后续请求。两次修复（TOCTOU / producer 活跃头room）均失败或回归，已逐字回滚。
  证据：`docs/F6_TRACK_B_RTS_RTF_EVIDENCE.md`。
  （注：官方 RTS 路径的 LISTEN-wedge 已单独修复，RTF 可测；此 SPEAK 楔死是另一候选级边界。）

## 3. 模型能力上限（非服务器 bug）

- **whisper 音频编码上限 ~24-26s**：超过该时长的输入音频可能输出 `?`×256。Daily-Omni 官方 29.5s
  音频即触发。证据：`docs/f6-s13-closure/phase2/daily_omni_pilot/`（threshold.json）。

## 4. 服务器已知边界

- **SSE + use_tts=True 的 T2W drain 未接入**：SSE 流式路径无 `omni_duplex_drain_tts_audio`；非流式路径完整。
- **KV A/B 28/30 valid**：2 对（C2-R2 / C5-R3）为 decode POST 客户端 HTTP 异常（A_ERR 预声明排除），
  机制层 30/30 正常；R13 canonical 30/30 官方速度结论不受影响。
- **无音频 drain stall 罕见边界**：极少数无音频响应会触发有界超时（自恢复），本轮干净运行 0 次。

## 5. 优化边界

- FA Q-split 源码默认 `16 → 0`（OFF）；长多模态 NaN 由 `OMNI_CANN_FA_MAX_UBATCH=16` 保护（+5.3% 开销）。
- flow ACL graph capture（`GGML_CANN_FLOW_ACL_GRAPH`）冻结 OFF（E2E 净损 +11%）。
- B6b（机械提前触发 Talker）冻结 OFF（无稳定收益）。

## 6. 未完成项（诚实标注）

- **官方 Demo 前端接入**：服务侧能力已验（文本/音频/UTF-8 30/30），但 OpenBMB/MiniCPM-o-Demo
  前端**尚未实际接入**。见 `DEMO_REPRODUCTION.md`。
- **官方隐藏测试集 / Overall 分母**：未公开；三条准确率当前 = 统一分支公开子集全量，公开后同脚本复核。
