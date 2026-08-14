# Demo 使用说明（提交物）

> 面向主办方/评审的 Demo 使用指南。基于 `OpenBMB/MiniCPM-o-Demo`（llama 子赛道官方 Demo）。
> 服务侧能力已验证（T6 11/11 + T10 pilot）；前端接入后按本说明操作。

---

## 1. 启动方式

```bash
# 环境检查
bash submission/environment/env_check.sh

# 启动推理服务（冻结候选）
bash submission/scripts/start_server.sh

# 健康检查
bash submission/scripts/health_check.sh

# 启动 Demo 前端
bash submission/scripts/start_demo.sh
```

## 2. 访问方式

- 推理服务：`http://<host>:18093`（/health、/v1/stream/decode、/omni/init 等）
- Demo 前端：按官方 MiniCPM-o-Demo README 访问（浏览器）

## 3. 核心交互流程

1. **纯文本**：输入文字 → 文本回答（use_tts=False）；或语音播报（use_tts=True）。
2. **单图**：上传图片 + 问题 → 图文回答。
3. **单音频**：上传音频 → 理解并回答。
4. **视频/视听**：上传视频（含音频轨）→ 视音频理解回答。
5. **语音对话**：语音输入 → 文本/语音输出（TTS 流式 chunk）。
6. **连续多轮**：同一会话多轮，上下文保持（persistent context）。
7. **中断恢复**：停止输入/断连后，服务保持存活，可开新会话。

## 4. 验证点（与评审检查项对应）

| 评审检查项 | 演示位置 |
|---|---|
| 服务正常启动 | 启动日志 + health |
| Demo 正常连接推理服务 | 前端连接成功 |
| 文本/音频/视频输入正常处理 | 用例 D3/D5/D6 |
| 模型输出完整 | text + 完整语音 |
| 流式语音连续 | 逐 chunk 播放无断裂 |
| 无明显卡顿/中断/异常退出 | 录像 |
| 完整交互流程 | 视频脚本覆盖全模态 |
| 连续运行稳定 | 10min 长稳 |

## 5. 已知限制（必须向评审说明）

- whisper 音频编码上限 ~24-26s：超过该时长的输入音频可能输出 `?`（**模型能力限制**，非服务器缺陷）。
- SSE 路径 + use_tts=True 的 T2W drain 未接入（已知边界；非流式路径完整）。
