# 官方 Demo 验证计划（OpenBMB/MiniCPM-o-Demo）

> llama 子赛道 Demo = `https://github.com/OpenBMB/MiniCPM-o-Demo`。
> 主办方检查：服务启动 / Demo 连接 / 文本-音频-视频输入 / 输出完整 / 音频连续 / 卡顿中断崩溃 / 完整交互流程 / 连续运行稳定。
> 服务侧能力已由 T6（11/11）与 T10 pilot（服务器链 6/6 门）证明；本计划是**官方 Demo 前端实际接入**的验收矩阵。

---

## 12 用例矩阵

| case_id | 场景 | 输入 | 预期 |
|---|---|---|---|
| D1 | 服务冷启动 | 无 | server 启动成功，health OK，端口可连 |
| D2 | Demo 连接 | 浏览器连接推理服务 | 连接成功，无握手错误 |
| D3 | 纯文本对话 | 文本问题 | 完整文本输出 |
| D4 | 单图理解 | 一张图 + 问题 | 图像相关作答 |
| D5 | 单音频输入 | 一段音频 | 可理解并作答 |
| D6 | 视频/视听输入 | 视频 + 音频 | 视音频理解作答 |
| D7 | 文本 + 语音输出 | 文本问题（TTS 开） | 连续流式语音 chunk |
| D8 | 连续多轮 | 多轮对话 | 每轮独立正确，上下文保持 |
| D9 | 中长输入 | 较长音频/长文本 | 完整处理不截断不崩溃 |
| D10 | 10 分钟连续运行 | 持续交互 | 无崩溃、无性能退化 |
| D11 | 断连重连 | 中断后重新连接 | 服务器存活，可继续新会话 |
| D12 | 错误输入恢复 | 空输入/损坏媒体 | 返回明确错误，服务不崩，后续请求正常 |

## 每用例记录 schema

```text
case_id | 输入 | 预期 | 实际 | text完整性 | audio完整性 | 首包耗时
chunk数量 | 是否连续 | 错误 | server health | NPU health | 通过与否
```

## 脚本与文档

| 文件 | 用途 |
|---|---|
| `submission/scripts/start_demo.sh` | 启动 Demo 前端 + 推理服务（含环境检查） |
| `submission/scripts/demo_smoke.sh` | 跑 D1–D12 冒烟（服务侧可自动化部分） |
| `submission/scripts/run_demo.sh` | 完整 Demo 演示驱动（录像辅助） |
| `docs/competition-submission/DEMO_USER_GUIDE.md` | Demo 使用说明（启动/访问/交互流程） |
| `docs/competition-submission/DEMO_VIDEO_SCRIPT.md` | 录像脚本（展示 commit/SHA、npu-smi、各模态、连续语音、稳定性） |
| `submission/demo/video_manifest.md` | 视频清单（文件名/时长/内容/时间戳） |

## 录像要求（抄送主办方检查项）

- 展示候选 commit（fd3dd36）与二进制 SHA（4694cb58… / 3f3e1e63…）
- 展示服务启动日志 + `npu-smi`
- 覆盖纯文本 / 单图 / 单音频 / 视频视听 / 连续多轮 / 持续语音输出
- 覆盖较长运行（≥10 min）与异常后恢复
- 日志区无错误（cpu_fallback=0 / cann_error=0）

## 当前状态

- 服务侧：`INTERNAL_PASS`（T6 11/11 + T10 6/6）
- 官方 Demo 前端接入：`NOT_RUN`（阻塞项 = 需要按官方 Demo 的接口规范接入；GitHub 仓库可拉取）
- OFFICIAL_DEMO_GATE：`NOT_RUN`
