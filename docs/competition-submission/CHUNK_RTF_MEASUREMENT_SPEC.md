# 逐 chunk RTF 测量规范

> llama 子赛道**唯一公开排名核心指标 = per-audio-chunk RTF**：
>
> ```
> chunk_rtf = chunk_compute_ms / audio_duration_ms
> ```
>
> **禁止**用以下口径代替：全请求 RTF / Flow 内部 RTF / Vocoder 内部 RTF / 平均每个 WAV 耗时 / request E2E ÷ 整段音频时长。

---

## 1. 关键事实：冻结二进制已逐 chunk 输出 RTF

冻结候选（server `db258375…`）日志原生打印每个音频 chunk 的计时行，**无需修改正式推理路径**：

```
T2W线程: wav_1002.wav | 1.00s audio | 232.4ms inference | RTF=0.23 | t=1744ms | queue_wait=110.5ms | req=1 gen=1
```

| 字段 | 值 | 对应官方定义 |
|---|---|---|
| `wav_1002.wav` | chunk 文件名（req=1, chunk=002） | chunk 身份 |
| `1.00s audio` | 该 chunk 音频时长（2 位小数，s） | `audio_duration_ms` |
| `232.4ms inference` | 该 chunk 生成耗时（compute） | `chunk_compute_ms` |
| `RTF=0.23` | 该 chunk RTF（inference ÷ 时长，打印取 2 位） | `chunk_rtf` |
| `t=1744ms` | 生成累计耗时（首 chunk 起） | 分析用，非 RTF 基础 |
| `queue_wait=…ms` | 入队等待 | 分析用 |
| `req=N gen=G` | 请求 / 生成轮次绑定 | 关联用 |

配套首响行：
```
🎉 首响时间 (First Audio Response): 1269ms (decode_to_first_audio) | 0ms (request_to_first_audio) | req=1 gen=1
```

配套 drain 行（用于判定 final chunk）：
```
T2W drain: complete (wav_count=12, notify=1 poll=0 fast=0 gen=1)
```

## 2. 统一记录 schema（chunk_rtf_raw.csv 列）

```
run_id, request_id, generation, chunk_index, is_first_chunk, is_final_chunk,
chunk_compute_begin_ns, chunk_compute_end_ns, chunk_compute_ms,
sample_count, sample_rate, audio_duration_ms, chunk_rtf,
valid_audio, exclusion_reason, error, server_pid, binary_sha, model_sha
```

| 列 | 来源 | 口径 |
|---|---|---|
| run_id | 脚本生成 | run_yyyymmdd_hhmmss |
| request_id | 日志 `req=` | 服务端请求 id |
| generation | 日志 `gen=` | 同请求第几代（is_final_chunk 按 (req, gen) 求 max） |
| chunk_index | wav 文件名解析（`wav_{req*1000+cidx}`，取 %1000） | 0-based |
| is_first_chunk | chunk_index==0 | — |
| is_final_chunk | 该 (req, gen) 的最大 chunk_index | — |
| chunk_compute_ms | 日志 `inference` | **RTF 计算基础** |
| audio_duration_ms | 日志 `X.XXs audio` ×1000 | **RTF 计算基础**（亦可用 wave 模块核对） |
| chunk_rtf | `chunk_compute_ms / audio_duration_ms` | 与日志打印 RTF 交叉核对 |
| chunk_compute_begin_ns / end_ns | 日志墙钟时间戳推导 | **近似值，仅时间线分析，不作 RTF 依据**；无法精确获得时填 NULL |
| sample_count / sample_rate | wav 头（或 duration×24000） | 24000 Hz（验证后填） |
| valid_audio | 逐项判定（见下，INTERNAL_VALIDATION_POLICY） | 全部校验通过才为 true |
| exclusion_reason | `\|` 连接的排除原因枚举 | 见排除原因表 |
| error | = exclusion_reason（兼容旧列） | 非空即无效 |
| server_pid / binary_sha / model_sha | run 时采集 | 溯源 |

**排除原因枚举**（valid_audio=false 时至少一个）：

```
EMPTY_PAYLOAD / ZERO_SAMPLES / INVALID_SAMPLE_RATE / DECODE_FAILURE / NAN_INF /
MISSING_REQUEST_ID / MISSING_CHUNK_INDEX / INVALID_TIMESTAMP / DUPLICATE_CHUNK / TRUNCATED_CHUNK
```

判定逻辑见 `submission/scripts/analyze_chunk_rtf.py::validate_chunk`（PCM/WAV 存在时用 `wave` 模块跨查；缺失不判失败）。统计输出含 total/valid/invalid 数 + 排除率 + 各排除原因计数。**排除规则/样本下限均为 INTERNAL_VALIDATION_POLICY，非 OFFICIAL_REQUIREMENT。**

## 3. 统计输出（chunk_rtf_summary.json）

```
count, mean, p50, p90, p95, p99, max
first-chunk 统计 / middle-chunk 统计 / final-chunk 统计
invalid/excluded count + exclusion reasons（逐条）
请求数 / chunk 总数 / 每请求 chunk 分布
```

## 4. 执行管线（不改推理路径）

1. `submission/scripts/start_server.sh` 启动（标准冻结 env）。
2. `submission/scripts/run_performance.sh <mode> --dry-run` 预检（MODE=baseline|candidate，同 runner/数据/seed/warmup/count/统计）。
3. `submission/scripts/run_performance.sh <mode>` 驱动 N 个 TTS 请求，落服务器日志；输出隔离到 `${OUTPUT_ROOT}/<run_id>/<mode>/`。
4. `submission/scripts/analyze_chunk_rtf.py <srv.log> <run_id> --warmup <W> --mode <mode>`
   → `<mode>/out/chunk_rtf_raw.csv` + `chunk_rtf_summary.json`（含 total/valid/invalid + 排除率 + 各排除原因计数）。
5. `submission/scripts/check_baseline_candidate_symmetry.py <run_dir>` 比对两 MODE 的 dataset SHA / case count / request IDs / sampling config / model / prompt / 统计代码 SHA，任一不一致退出非零。
6. 交叉核对：对若干 wav 用 `wave` 模块核对 sample_count/sample_rate/duration，确认日志 `X.XXs` 与真实头一致。

## 5. 纪律

- 只允许：日志解析 / 离线分析 / 低开销埋点（若官方口径需要更精确起止，经批准后加埋点，**不得触碰冻结源码**）。
- 官方计时口径（起止点、首 chunk 判定、chunk 语义）以官方 starter kit 为准；本文档先行，到达后对照更新。
- 每批数据必须带 run_id / binary_sha / model_sha，可溯源。
