# llama.cpp-omni → vLLM-Omni 组件映射（代码审计入口）

> **用途**：这是队友在 vLLM-Omni 源码中的审计地图，**不是函数一一对应**。
> 每个组件给出 13 个字段；**未源码审计的 vLLM 类/函数一律标 `TO_AUDIT`**，禁止把猜测写成 CONFIRMED。
> 验证实验编号对应 `VLLM_OPTIMIZATION_EXECUTION_PLAN.md` 的 V0–V12。

---

## 0. 13 字段说明

`llama对象 / llama owner / llama生命周期 / vLLM候选对象 / vLLM可能目录 / vLLM可能类/函数 / 状态 / 必须回答的问题 / 建议grep关键词 / 建议runtime日志 / 验证实验 / 风险 / 备注`

---

## 1. Serving（HTTP 入口）

| 字段 | 值 |
|---|---|
| llama 对象 | `server-omni.cpp` HTTP handler（`/v1/stream/decode`、SSE） |
| llama owner | 主线程 handler；请求级 state 存 `omni_context` |
| llama 生命周期 | 每请求：decode → drain → response；断连 → abort |
| vLLM 候选对象 | OpenAI `chat/completions` API；`chat/` 路由；Request 对象 |
| vLLM 可能目录 | `vllm_omni/`（api/entrypoints）、`vllm/entrypoints/` |
| vLLM 可能类/函数 | ChatCompletion handler / OpenAI api_server / RequestQueue | `TO_AUDIT` |
| 状态 | 端点 CONFIRMED_FROM_DEPLOY_DOC；类名 TO_AUDIT |
| 必须回答 | streaming 与 non-streaming 是否同一解码路径？TTS 模板开关如何透传？错误如何变成 HTTP 状态码（有无类似 llama httplib 静默 500 的坑）？ |
| 建议 grep | `rg -n "chat.completions|Completions|async def chat|@app.post"` |
| 建议 runtime 日志 | 每请求 request_id + HTTP status + 耗时 |
| 验证实验 | V1（冒烟） |
| 风险 | 接口字段缺省 → 官方判分不可用（llama F7/T7 教训） |

---

## 2. Scheduler（调度/入队）

| 字段 | 值 |
|---|---|
| llama 对象 | 请求级 `request_generation` 守卫；`REQ_*` 状态机（REQ_RESPONDING/REQ_IDLE…） |
| llama owner | handler + drain 协作；CV 通知 |
| llama 生命周期 | admit → enqueue → prefill/decode → drain_complete → REUSABLE |
| vLLM 候选对象 | Scheduler；RequestQueue；SequenceGroup |
| vLLM 可能目录 | `vllm/core/scheduler.py`、`vllm/engine/` |
| vLLM 可能类/函数 | Scheduler.add_seq_group / RequestQueue | `TO_AUDIT` |
| 状态 | TO_AUDIT |
| 必须回答 | 何时才算"完成"？被 cancel 的请求如何出队？资源何时释放？ |
| 建议 grep | `rg -n "class Scheduler|def add_seq|class RequestQueue|finished"` |
| 建议 runtime 日志 | enqueue/dequeue 时间戳 + queue depth |
| 验证实验 | V6 |
| 风险 | queue empty ≠ worker inactive（llama R7） |

---

## 3. Thinker（主模型）

| 字段 | 值 |
|---|---|
| llama 对象 | Main LLM `stream_decode` / `stream_prefill` |
| llama owner | 主 decode 线程 |
| llama 生命周期 | prefill → decode 至 speak 决策 → 持续到 EOS |
| vLLM 候选对象 | Thinker Stage；`MiniCPM-O` 文本+视觉部分 |
| vLLM 可能目录 | `vllm_omni/` thinker stage |
| vLLM 可能类/函数 | ThinkerModel / ThinkerProcessor | `TO_AUDIT` |
| 状态 | TO_AUDIT |
| 必须回答 | prefill/decode 可否独立打点？TTFT 是否受系统前缀 prefill 主导？KV 归谁管理？ |
| 建议 grep | `rg -n "class .*Thinker|thinker|def prefill|def decode"` |
| 建议 runtime 日志 | prefill begin/end、first token、speak decision |
| 验证实验 | V3 |
| 风险 | 把 thinker decode 误当第一瓶颈（llama 2.9%） |

---

## 4. Talker（音频 token 生成）

| 字段 | 值 |
|---|---|
| llama 对象 | Talker thread / `generate_audio_tokens_local_simplex` / `sample_tts_token_simplex` |
| llama owner | TTS 生成线程；per-generation 隔离 |
| llama 生命周期 | speak 决策后启动 → 生成 audio token 直至 EOS → chunk 提交 T2W |
| vLLM 候选对象 | Talker Stage；`MiniCPM-O` 音频 decoder |
| vLLM 可能目录 | `vllm_omni/` talker stage |
| vLLM 可能类/函数 | TalkerModel | `TO_AUDIT` |
| 状态 | TO_AUDIT |
| 必须回答 | Talker 是否真"完成"了？输出是否带 request_id？Talker KV 独立上限多少（llama 4096）？ |
| 建议 grep | `rg -n "class .*Talker|talker|sample_tts|audio_token"` |
| 建议 runtime 日志 | admit、first token、context usage、complete |
| 验证实验 | V3 / V7 |
| 风险 | Talker context 满 / 旧音频混入新请求（llama G1） |

---

## 5. Token2Wav（语音合成下游）

| 字段 | 值 |
|---|---|
| llama 对象 | T2W worker + queue；`token2wav`（CANN flow + vocoder） |
| llama owner | T2W 线程；`t2w_thread_info` |
| llama 生命周期 | 收 token → Flow → Vocoder → WAV → 推流 |
| vLLM 候选对象 | Token2Wav Stage；`step_audio2_core`；HiFT/HiFiGAN |
| vLLM 可能目录 | `vllm_omni/` token2wav stage；依赖 `step-audio2` |
| vLLM 可能类/函数 | Token2WavProcessor / MiniCPMO45Token2wav | `TO_AUDIT` |
| 状态 | TO_AUDIT；依赖名 CONFIRMED_FROM_DEPLOY_DOC |
| 必须回答 | 运行设备（CPU/NPU）？host-device copy 在哪？buffer 上限？dequeue 后是否真完成？ |
| 建议 grep | `rg -n "Token2Wav|token2wav|HiFT|HiFiGAN|step_audio2"` |
| 建议 runtime 日志 | admit、Flow begin/end、Vocoder begin/end、first audio、complete |
| 验证实验 | V3 / V4 / V7 |
| 风险 | 设备放置主导首音（llama 93%）；Token2Wav backlog |

---

## 6. Prefix Cache（静态前缀复用）

| 字段 | 值 |
|---|---|
| llama 对象 | Persistent Server + KV cache 指纹（`OMNI_KV_CACHE_REUSE=1`） |
| llama owner | 请求首次 prefill 时保存；后续请求按 key 命中 |
| llama 生命周期 | 请求1 MISS（保存）→ 请求2+ HIT（复用） |
| vLLM 候选对象 | Prefix Caching / Automatic Prefix Caching（APC）；KV cache manager |
| vLLM 可能目录 | `vllm/worker/cache_engine.py`、`vllm/model_executor/layers/`（kv） |
| vLLM 可能类/函数 | BlockSpaceManagerV1/V2、PrefixCachingBlockAllocator | `TO_AUDIT` |
| 状态 | 机制 CONFIRMED_FROM_DEPLOY_DOC；实现 TO_AUDIT |
| 必须回答 | 是否覆盖多模态 embedding / reference audio / TTS template？Cache Key 组成？ |
| 建议 grep | `rg -n "prefix|PrefixCaching|cache_hit|reused_tokens|block_table"` |
| 建议 runtime 日志 | reused blocks/tokens、prefill latency、TTFT |
| 验证实验 | V5 |
| 风险 | false HIT / cache collision / 只缓存 thinker 文本 KV |

---

## 7. KV Manager / 8. Block Table

| 字段 | 值 |
|---|---|
| llama 对象 | `llama_memory_seq_rm` / `llama_kv_cache`（TTS 与 LLM 各一份） |
| llama owner | llama context 内部；TTS KV 4096 上限 |
| llama 生命周期 | 每请求 TTS chunk0 清 KV；LLM 常驻复用 |
| vLLM 候选对象 | KV Cache Manager + Block Table |
| vLLM 可能目录 | `vllm/worker/cache_engine.py`、`vllm/worker/block_manager.py` |
| vLLM 可能类/函数 | CacheEngine、BlockTable、KVBlockAllocator | `TO_AUDIT` |
| 状态 | TO_AUDIT |
| 必须回答 | 每 Stage 是否独立 KV？块何时回收？Talker/Token2Wav 用哪套 KV/block？ |
| 建议 grep | `rg -n "class BlockTable|class CacheEngine|kv_cache|allocate|free"` |
| 建议 runtime 日志 | kv blocks free/used、每 Stage context usage |
| 验证实验 | V6 / V7 |
| 风险 | block leak（HBM 单调增长）；memory-slot 误归因 |

---

## 9. Output Processor（输出后处理）

| 字段 | 值 |
|---|---|
| llama 对象 | `text_queue` drain（非流式 `text` 字段）；WAV 聚合；`__END_OF_TURN__` |
| llama owner | handler（非流式） / T2W（音频） |
| llama 生命周期 | 生成结束 → drain → 响应字段 → 判分 |
| vLLM 候选对象 | OutputProcessor / chat 响应构造 / audio field |
| vLLM 可能目录 | `vllm_omni/`（response）、`vllm/engine/output_processor.py` |
| vLLM 可能类/函数 | OutputProcessor / ChatCompletion response builder | `TO_AUDIT` |
| 状态 | TO_AUDIT |
| 必须回答 | text 与 audio 字段是否都存在？空文本/空音如何表示？ |
| 建议 grep | `rg -n "audio|choices|message.content|output_processor|finish_reason"` |
| 建议 runtime 日志 | 输出字段完整性、输出长度 |
| 验证实验 | V1 |
| 风险 | 非流式无 text / 空音（llama F7/T7 教训） |

---

## 10. Streaming（流式输出）

| 字段 | 值 |
|---|---|
| llama 对象 | SSE handler（`stream:true`）；`sink.done()` |
| llama owner | SSE worker（每请求一次） |
| llama 生命周期 | worker 生成 → chunked 推流 → `[DONE]` → releaser join |
| vLLM 候选对象 | OpenAI streaming / async generator |
| vLLM 可能目录 | `vllm_omni/` streaming、`vllm/engine/async_llm_engine.py` |
| vLLM 可能类/函数 | AsyncStream / stream generator | `TO_AUDIT` |
| 状态 | TO_AUDIT |
| 必须回答 | `[DONE]` 后 provider 是否真终结？流结束是否触发下游资源回收？ |
| 建议 grep | `rg -n "stream|async def|\[DONE\]|finish"` |
| 建议 runtime 日志 | 流开始/结束、chunk 数 |
| 验证实验 | V1 / V6 |
| 风险 | 流式崩溃服务器（llama F7-1 bad_alloc 教训） |

---

## 11. Cancel/Abort（断连/取消）

| 字段 | 值 |
|---|---|
| llama 对象 | 断连检测 + `break_event` + drain 协作；弃用 recovery `omni_free` 竞争 |
| llama owner | handler / decode 线程 |
| llama 生命周期 | 断连 → 在途 decode 平息 → 常驻上下文复用 |
| vLLM 候选对象 | abort/cancel path；client disconnect 处理 |
| vLLM 可能目录 | `vllm_omni/`（abort）、`vllm/engine/` |
| vLLM 可能类/函数 | abort_request / cancel | `TO_AUDIT` |
| 状态 | TO_AUDIT |
| 必须回答 | 断连后谁取消下游 Stage？被取消请求是否留 orphan task？ |
| 建议 grep | `rg -n "abort|cancel|disconnect|disconnected|is_cancelled"` |
| 建议 runtime 日志 | cancel 事件、残留任务 |
| 验证实验 | V6 |
| 风险 | use-after-free（llama 曾因 omni_free 竞争崩溃）；orphan future |

---

## 12. Stage Channel（阶段间传输）

| 字段 | 值 |
|---|---|
| llama 对象 | T2W queue + `tts_token_buffer` + CV 通知 |
| llama owner | 生产端（Talker）/ 消费端（T2W worker） |
| llama 生命周期 | token 入队 → 消费 → buffer 滑动（lookahead） |
| vLLM 候选对象 | Stage channel / task queue / asyncio queue |
| vLLM 可能目录 | `vllm_omni/`（stage 间通信） |
| vLLM 可能类/函数 | Stage queue / channel 类 | `TO_AUDIT` |
| 状态 | TO_AUDIT |
| 必须回答 | queue empty 是否 = 无 active work？backlog 是否可观测？ |
| 建议 grep | `rg -n "Queue|channel|put_nowait|get_nowait|async for"` |
| 建议 runtime 日志 | queue depth、wait time |
| 验证实验 | V3 / V6 |
| 风险 | queue empty ≠ 完成；Token2Wav backlog |

---

## 13. Duplex Session（全双工会话）

| 字段 | 值 |
|---|---|
| llama 对象 | duplex 分支（`omni_duplex_*`）；`__IS_LISTEN__`/`__END_OF_TURN__` 标记 |
| llama owner | 双工消费路径（与 simplex 分离） |
| llama 生命周期 | 会话 TTL / 断开 grace / turn 边界 |
| vLLM 候选对象 | Duplex Session；`/v1/realtime?duplex=1`、`/v1/duplex` |
| vLLM 可能目录 | `vllm_omni/` duplex 模块；`minicpmo_4_5_duplex.yaml` |
| vLLM 可能类/函数 | RealtimeSession / DuplexSession | `TO_AUDIT` |
| 状态 | experimental（文档标）；实现 TO_AUDIT |
| 必须回答 | 会话 TTL / disconnect grace / replay TTL / pending turn limit / max sessions？speak-listen 决策与 barge-in？ |
| 建议 grep | `rg -n "duplex|realtime|barge_in|session_id|ttl"` |
| 建议 runtime 日志 | session 创建/过期、turn 边界 |
| 验证实验 | V11 |
| 风险 | Duplex 实验线阻塞 Simplex 主线；断线恢复不完整 |

---

## 14. 代码导航命令模板（不修改 vLLM 源码）

每条命令：`目的 → 期望找到 → 找到后回答什么`

```bash
# 1. 定位多阶段 pipeline 与 T2W 依赖
rg -n "MiniCPM|MiniCPMO|Token2Wav|step_audio2" vllm_omni
# 目的: 找到 Thinker/Talker/Token2Wav stage 定义与依赖
# 期望: 类名、模块路径、依赖引用
# 找到后回答: stage 边界在哪; Token2Wav 依赖哪个库

# 2. 定位 Prefix Caching
rg -n "prefix.cach|enable_prefix|block_table|kv_cache" .
# 目的: 确认是否开启、缓存粒度
# 期望: 配置项 + block allocator 实现
# 找到后回答: 是否覆盖多模态/TTS 前缀; Cache Key 组成

# 3. 定位请求身份与取消
rg -n "request_id|abort|cancel|finish|finished" vllm_omni
# 目的: 找 request identity 贯穿 + abort 路径
# 期望: request_id 字段、abort 调用点
# 找到后回答: 取消后谁负责下游 Stage; 状态是否 per-request

# 4. 定位设备布局与 batch 配置
rg -n "stage_id|device|devices|max_num_seqs|max_num_batched_tokens" vllm_omni/deploy vllm_omni
# 目的: 确认每 Stage 设备与容量配置
# 期望: YAML 字段 + stage device 逻辑
# 找到后回答: Flow/Vocoder 设备; max_num_seqs 是否合理

# 5. 定位音频指标与完成语义
rg -n "audio_ttfp|audio_rtf|first.*audio|response.done" .
# 目的: 找音频指标埋点与完成判定
# 期望: 指标定义 + 完成事件
# 找到后回答: "完成"是哪个 Stage 判定的

# 6. 定位 Flow/Vocoder 实现与设备
rg -n "Flow|Vocoder|HiFT|HiFiGAN|step_audio2_core" .
# 目的: 找语音合成算子的实际设备
# 期望: 实现 + tensor.device 位置
# 找到后回答: CPU 还是 NPU; host copy 在哪
```

> 注意：`vllm_omni` 路径名来自部署文档约定，是否与实际仓库一致需以实际 checkout 为准。
