# STARTER_KIT_CHECKLIST — 官方材料核对清单

> 官方 starter kit 到达后逐项核对，未确认项标记为 `[ ]`。

---

## 接口协议

- [ ] 服务启动方式（CLI args, env vars, config file）
- [ ] 通信协议（HTTP / WebSocket / gRPC / 其他）
- [ ] 端点列表（init / prefill / decode / health / 其他）
- [ ] 请求 JSON schema
- [ ] 响应格式（SSE / JSON lines / binary / 其他）
- [ ] 错误码定义

## 输入数据

- [ ] 输入类型（纯文本 / 音频 / 图像 / 混合）
- [ ] 音频格式（采样率、位深、声道数、时长）
- [ ] 图像格式（分辨率、编码、通道）
- [ ] 输入来源（固定测试集 / 随机 / 自选）
- [ ] 是否允许预处理

## 计时规则

- [ ] 计时起点（客户端发送 / 服务端接收 / prefill 完成）
- [ ] TTFT 定义（首个 text token / 首个 chunk 任意类型）
- [ ] First Audio 定义（首个 audio chunk / 首个完整 WAV）
- [ ] Chunk 定义（text chunk? audio chunk? 服务端帧? 固定间隔?）
- [ ] E2E 终点（最后 chunk / [DONE] 信号 / 连接关闭）
- [ ] Warmup 允许（多少个请求 / 是否计入统计）

## 并发规则

- [ ] 并发定义（同时连接数 / 同时 active session / 同时 decode）
- [ ] 并发级别（1, 2, 4, 8? 其他? 仅指定最大值?）
- [ ] 是否允许多实例 / 多进程
- [ ] 是否允许设备独占或共享

## 正确性判定

- [ ] 文本正确性（BLEU / ROUGE / exact match / 人工 / 不考核）
- [ ] 音频正确性（MOS / WER / SNR / WAV header / 不考核）
- [ ] 功能完整性（vision 必测 / optional / 不考核）
- [ ] 是否允许降级（如纯文本模式 / CPU fallback）

## 资源限制

- [ ] NPU 数量限制
- [ ] CPU 核心 / NUMA 限制
- [ ] 内存限制（RSS / HBM）
- [ ] 是否允许 swap
- [ ] 是否允许 offload 到 CPU

## 提交包格式

- [ ] 源码还是二进制
- [ ] Docker / Singularity / 裸机
- [ ] 需要什么文件（Dockerfile / build.sh / run.sh / 报告）
- [ ] 目录结构要求
- [ ] 命名规范

## 超时和失败

- [ ] 单请求超时
- [ ] 整体 benchmark 超时
- [ ] 失败请求是否重试
- [ ] 失败是否计入统计

## 其他

- [ ] 是否有官方 baseline 分数
- [ ] 是否有参考实现
- [ ] 是否有禁止使用的技术 / 库 / 优化
- [ ] 是否需要提交 Profiling 证据

---

## 核对结果

| 分类 | 总项 | 已确认 | 待确认 |
|------|------|--------|--------|
| 接口协议 | 7 | 0 | 7 |
| 输入数据 | 6 | 0 | 6 |
| 计时规则 | 7 | 0 | 7 |
| 并发规则 | 4 | 0 | 4 |
| 正确性判定 | 4 | 0 | 4 |
| 资源限制 | 4 | 0 | 4 |
| 提交包格式 | 5 | 0 | 5 |
| 超时和失败 | 4 | 0 | 4 |
| 其他 | 4 | 0 | 4 |
| **合计** | **45** | **0** | **45** |

> starter kit 到达后逐项标记 `[x]`。
