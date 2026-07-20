# METRIC_CONTRACT — 指标定义协议

> **状态：provisional**  
> 以下定义是当前对官方指标的理解。starter kit 到来后必须逐项核对并更新。

---

## 计时基准

| 事件 | 定义 | 正式 |
|------|------|------|
| `request_start` | 客户端发送请求的时间戳 | 待官方确认 |
| `first_text_token` | 客户端收到第一个 text token 的时间戳 | 待官方确认 |
| `first_audio_chunk` | 客户端收到第一个 audio chunk 的时间戳 | 待官方确认 |
| `chunk_N` | 客户端收到第 N 个 chunk 的时间戳 | 待官方确认 |
| `request_end` | 客户端收到最后一个 chunk 或服务端发送 [DONE] | 待官方确认 |

## 核心指标

| 指标 | 计算方式 | 单位 | 正式 |
|------|---------|------|------|
| **TTFT** | `first_text_token - request_start` | ms | 待官方确认 |
| **First Audio Latency** | `first_audio_chunk - request_start` | ms | 待官方确认 |
| **Chunk Interval** | `chunk_N - chunk_{N-1}` | ms | 待官方确认 |
| **E2E Latency** | `request_end - request_start` | ms | 待官方确认 |
| **Throughput** | `total_completed_requests / total_wall_time` | req/s | 待官方确认 |

## 统计口径

| 项目 | 当前 | 正式 |
|------|------|------|
| 汇总方式 | median, p90, p99 | 待官方确认 |
| warmup | 前 N 个请求不计入统计 | 待官方确认 N |
| 失败请求 | 保留但标记，不参与统计 | 待官方确认 |
| 超时 | 单请求超时默认 300s | 待官方确认 |
| 并发定义 | 同时活跃的 session 数 | 待官方确认 |

## 正确性

| 项目 | 当前 | 正式 |
|------|------|------|
| 文本校验 | 检查 LLM 返回非空 | 待官方确认 |
| 音频校验 | WAV header valid, duration > 0 | 待官方确认 |
| NaN/Inf | 输出不得含 NaN/Inf | 待官方确认 |

## Starter Kit 核对清单

- [ ] 接口协议（WebSocket / HTTP / gRPC）
- [ ] 输入格式（JSON schema, 字段名, 数据类型）
- [ ] 输出格式（SSE / binary / JSON lines）
- [ ] 计时起点和终点
- [ ] chunk 定义（text chunk? audio chunk? 服务端帧?）
- [ ] 并发定义（同时连接数? 同时 active session 数?）
- [ ] 正确性判定规则
- [ ] 超时设置
- [ ] 提交包格式
- [ ] 资源限制（CPU / NPU / memory）
- [ ] 是否允许 warmup / 预热
- [ ] 输入数据（固定测试集? 随机? 自选?）
