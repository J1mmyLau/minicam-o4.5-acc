# 已知限制（提交物）

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
- CHUNK_SIZE=25 冻结；FA/speculation/operator fusion 冻结为 OFF。
