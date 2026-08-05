# Demo Gate Checklist — D1–D12

> 官方 Demo: [MiniCPM-o-Demo](https://github.com/OpenBMB/MiniCPM-o-Demo)
> 准入条件: Demo 必须端到端可用，否则不进入性能评测。
> 当前: **全部 NOT_RUN**（官方 Demo 资产未到位）。

---

## 官方检查维度

主办方将重点检查:

- 模型服务能否正常启动
- Demo 能否正常连接推理服务
- 音频、视频和文本输入是否能够正常处理
- 模型输出是否完整
- 流式语音输出是否连续
- 是否存在明显卡顿、中断或异常退出
- 是否能够完成官方指定的完整交互流程
- 连续运行过程中是否保持稳定

---

## D1–D12 检查表

| ID | 检查项 | 预期 | 命令 | 输入 | 实际结果 | 日志路径 | 截图/视频 | 状态 |
|----|-------|------|------|------|---------|---------|----------|------|
| **D1** | Server start | 服务成功启动, health 可达 | `submission/scripts/start_server.sh` | server.env | — | — | — | `NOT_RUN` |
| **D2** | Health check | `/health` 返回 200 | `curl /health` | — | — | — | — | `NOT_RUN` |
| **D3** | Demo frontend start | Demo 前端成功启动 | 参照 MiniCPM-o-Demo README | — | — | — | — | `NOT_RUN` |
| **D4** | Demo ↔ server | 前端成功连接推理服务 | Demo 界面操作 | OAI chat/completions | — | — | — | `NOT_RUN` |
| **D5** | Text input | 文本输入正常处理 | Demo 界面输入 | 纯文本 | — | — | — | `NOT_RUN` |
| **D6** | Image input | 图像输入正常处理 | Demo 界面上传 | 图片文件 | — | — | — | `NOT_RUN` |
| **D7** | Audio input | 音频输入正常处理 | Demo 界面上传 | 音频文件 | — | — | — | `NOT_RUN` |
| **D8** | Video input | 视频输入正常处理 | Demo 界面上传 | 视频文件 | — | — | — | `NOT_RUN` |
| **D9** | Output completeness | text + audio 输出完整 | 检查 SSE stream | — | — | — | — | `NOT_RUN` |
| **D10** | Streaming audio continuity | chunk index 连续, 时间戳单调, 无重复/空/截断/长停顿 | 检查 WAV chunks | — | — | — | — | `NOT_RUN` |
| **D11** | Full interaction flow | 完成官方指定完整交互 | Demo 全流程 | 官方交互脚本 | — | — | — | `NOT_RUN` |
| **D12** | Continuous stability | 长时间运行无卡顿/中断/异常退出 | 30min+ 连续运行 | — | — | — | — | `NOT_RUN` |

---

## 音频连续性检查（D10 补充）

| 检查项 | 方法 | 状态 |
|--------|------|------|
| chunk index 连续 | 解析 WAV timestamp / sequence | `NOT_RUN` |
| 时间戳单调递增 | 逐 chunk 比较 mtime | `NOT_RUN` |
| 无重复 chunk | hash 去重 | `NOT_RUN` |
| 无空音频 | WAV duration > 0 | `NOT_RUN` |
| 无截断 | 最后 chunk 完整 | `NOT_RUN` |
| 无长时间停顿 | inter-chunk gap < 阈值 | `NOT_RUN` |
| 请求结束状态正确 | SSE stream 正常关闭 | `NOT_RUN` |
| 后续请求仍正常 | 同 session 再发请求 | `NOT_RUN` |

---

## 运行方式

```bash
# 完整 Demo Gate（需官方资产到位后运行）
bash submission/scripts/run_demo_gate.sh

# 冒烟（服务侧可自动化部分）
bash submission/scripts/demo_smoke.sh

# dry-run（检查资产是否到位，不生成伪结果）
bash submission/scripts/run_demo_gate.sh --dry-run
```

---

## 当前阻塞清单

| 阻塞项 | 说明 |
|--------|------|
| MiniCPM-o-Demo 前端代码 | `git clone https://github.com/OpenBMB/MiniCPM-o-Demo.git third_party/MiniCPM-o-Demo` |
| 官方 Demo 交互素材 | 文本/图片/音频/视频输入样例 |
| 官方完整交互流程定义 | 预期的交互步骤和验证标准 |
| 演示视频录制 | D1-D12 全部 PASS 后方可录制 |

---

> **NOT_RUN**: D1-D12 全部标记 NOT_RUN，无伪 PASS。
> 官方 Demo 资产到位后，按行填写命令、输入、实际结果、日志路径和截图/视频时间点。
