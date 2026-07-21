# Next Baseline Plan — 服务性能基线采集计划

> 工作区：`eval/official-baseline` (commit `a03f7c0`)  
> 冻结 Release：`release/final-integration` (commit `bde403d`) — 禁止修改  
> 状态：**planning — 不在此阶段做性能优化**

---

## 原则

1. **先验证正确性，再测性能**
2. **先 C1，再 C2/C4/C8**
3. **所有 chunk 保存原始时间戳**
4. **并发输出必须验证不串线**
5. **不修改冻结 Release**
6. **不宣称性能收益直到官方口径确认**

---

## Step 1: WebSocket 单 session 指标采集

### 目标

从 `llama-omni-server` 的 WebSocket `/backend` 接口采集完整的 per-chunk 时间戳。

### 记录事件

```
t_request_start        — WebSocket 连接建立
t_session_ready        — omni_init 完成
t_prefill_start        — prefill 请求发送
t_first_text           — 第一个 text token 到达
t_first_audio          — 第一个 audio chunk 到达
t_audio_chunk_1        — 第 1 个 audio chunk
t_audio_chunk_2        — 第 2 个 audio chunk
...
t_response_done        — 流结束 / [DONE] / 连接关闭
```

### 计算指标

```
TTFT        = t_first_text  - t_request_start
First Audio = t_first_audio - t_request_start
Chunk[i]    = t_audio_chunk_i - t_audio_chunk_{i-1}
E2E         = t_response_done - t_request_start
```

### 验证

- [ ] 单请求协议 Smoke（WebSocket 连接、init、prefill、decode 全部走通）
- [ ] 原始时间戳 JSONL 记录完整
- [ ] TTFT > 0, First Audio > 0, E2E > TTFT
- [ ] Chunk intervals 非负且合理（~100ms~500ms 量级）
- [ ] text content 非空
- [ ] audio WAV 可播放

---

## Step 2: C1 正确性基线

### 目标

单 session 连续 N 个请求，验证正确性和稳定性。

### 配置

- concurrency: 1
- warmup: 3 requests
- measured: 20 requests
- 固定输入（同一个 test case）
- timeout: 300s per request

### 输出

- `baseline_c1.jsonl` — 每请求一行，含所有 chunk 时间戳
- `baseline_c1.csv` — 统计汇总
- WAV 文件列表 + 格式校验结果
- 资源监控 CSV（CPU/NPU/HBM/RSS）

### 验证

- [ ] 20/20 success
- [ ] WAV 格式正确（1ch 24000Hz 16-bit）
- [ ] 文本非空
- [ ] 无 session 串线
- [ ] TTFT/FirstAudio/E2E 中位数合理

---

## Step 3: 单进程 C2 session 隔离

### 目标

验证 `llama-omni-server` 单进程是否支持 2 个并发 session，且输出不串线。

### 测试

- 启动 1 个 server
- 2 个 client 同时发送不同输入
- 检查输出归属是否正确（session A 的输出没跑到 session B）

### 验证

- [ ] 2 个 session 同时 active
- [ ] 各 session 输出内容独立
- [ ] 无 crash
- [ ] 无超时
- [ ] 吞吐 vs C1 对比

### 如果单进程不支持多 session

考虑方案 B：

```
NPU 0 → server instance A → port 9060
NPU 1 → server instance B → port 9061
router 分发 session
```

---

## Step 4: 单进程 C4

条件：Step 3 通过。

- concurrency: 4
- warmup: 3
- measured: 20
- 资源监控同步采集

---

## Step 5: 双实例方案（每 NPU 一个 server）

### 目标

验证两实例方案的可行性和吞吐扩展。

### 部署

```bash
# Instance A (NPU 0)
SOC_VERSION=Ascend910 NPU_DEVICE_ID=0 \
  ./llama-omni-server --port 9060 --model ... -ngl 99 &

# Instance B (NPU 1)
SOC_VERSION=Ascend910 NPU_DEVICE_ID=1 \
  ./llama-omni-server --port 9061 --model ... -ngl 99 &
```

### 测试矩阵

| 配置 | 说明 |
|------|------|
| 2 instance × 1 session each (C2 total) | 基础正确性 |
| 2 instance × 2 sessions each (C4 total) | 扩展性 |
| 2 instance × 4 sessions each (C8 total) | 极限并发 |

---

## Step 6: C2/C4/C8 完整矩阵

条件：Step 3~5 全部通过。

```bash
bash competition/run_concurrency_matrix.sh
```

输出：

- `baseline_c1.jsonl`
- `baseline_c2.jsonl`
- `baseline_c4.jsonl`
- `baseline_c8.jsonl`
- `resource_monitor.csv`
- `summary.csv` / `summary.json`

---

## Step 7: CPU/NPU/HBM/RSS 全程监控

每个并发级别同步采集：

```bash
bash competition/resource_monitor.sh <server-pid> &
```

- RSS (MB)
- CPU %
- HBM0 used (MB)
- HBM1 used (MB)
- Thread count
- 采样间隔：5s

---

## Step 8: 生成 official-style baseline 表

填入 `competition/report_template.md`：

| 指标 | C1 | C2 | C4 | C8 |
|------|----|----|----|----|
| TTFT median | | | | |
| First Audio median | | | | |
| Chunk Interval p90 | | | | |
| E2E median | | | | |
| Throughput | | | | |
| Success Rate | | | | |

---

## 当前状态

| Step | 状态 |
|------|------|
| 1. WebSocket 单 session 指标采集 | NOT STARTED |
| 2. C1 正确性基线 | NOT STARTED |
| 3. C2 session 隔离 | NOT STARTED |
| 4. C4 | NOT STARTED |
| 5. 双实例方案 | NOT STARTED |
| 6. C2/C4/C8 完整矩阵 | NOT STARTED |
| 7. 资源监控 | NOT STARTED |
| 8. Official-style baseline 表 | NOT STARTED |

> 启动条件：`competition/STARTER_KIT_CHECKLIST.md` 完成 + `OfficialAdapter` 实现后。
