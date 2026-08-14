# llama.cpp-omni → vLLM-Omni 优化机制迁移地图

> 目的：**不是**「llama 用 X，vLLM 用 Y」的罗列；而是**按优化机制**解释迁移。
> 适用于 Omni 全链路（MiniCPM-o 系：Vision/Audio → Thinker → Talker → Token2Wav），非 vLLM 专属。
> 状态：**架构映射 + 路线**，未迁移任何代码。

---

## 12.1 全链路 stage 对比与 ownership

| llama.cpp-omni | vLLM-Omni | stage ownership / 调度差异 |
|---|---|---|
| media → vision/audio encoder | request → multimodal preprocessing | llama 在 server 内同步预处理；vLLM 用 multimodal input processor（HF processor + 前端 tokenizer） |
| main LLM prefill/decode | Thinker（LLM engine） | llama 手动管理 slot/KV；vLLM engine 统一调度 prefill/decode |
| duplex LISTEN/SPEAK 状态机 | Thinker→Talker 的 stage 边界 | llama 在 `omni.cpp` 手工状态机；vLLM 用 engine 的 request lifecycle + 显式 stage 切换 |
| TTS/Talker autoregressive | Talker（第二个 LLM） | llama 在同一 server 里跑 Talker；vLLM 把 Talker 当独立 LLM engine 或同 engine 的多 model |
| Token2Wav (Flow+Vocoder) | Token2Wav stage | 两者都是「speech token → WAV」的独立算子段，非 LLM |

**关键差异**：llama.cpp-omni 是**单进程、手工状态机、显式 context 生命周期**；vLLM-Omni 是**引擎化、request 调度、paged KV**。迁移时，「LLM decode 加速」这类机制可直接映射；「duplex 状态机 / T2W drain」这类语义要求必须重写为 vLLM 的调度原语（见 §12.7）。

---

## 12.2 KV / Prefix

| 维度 | llama.cpp-omni | vLLM-Omni |
|---|---|---|
| KV 结构 | 连续 buffer，per-slot | Paged KV（block 表） |
| prefix 复用 | `OMNI_KV_CACHE_REUSE`（save/load，session 级） | prefix caching（hash → block 复用） |
| 分配 | 手动 slot，`n_ctx=4096` | 动态 block 分配 |
| 复用粒度 | 整个 session 的 KV | 任意 token 前缀 |
| eviction | 手动 clear（session 结束） | LRU / 容量驱逐 |
| multimodal prefix | 视频帧 prefix 需手动对齐 | multimodal placeholder + cached prefix |
| 正确性 | 本项目修过「session 复用 → 上下文污染」类 bug | 依赖 engine 的 KV 一致性保证 |

**迁移要点**：把「session 级 KV save/load」映射为「prefix caching」—— 但 llama 的 session 复用是**整段 KV**（含 duplex 状态），vLLM 的 prefix caching 是**纯 token 前缀**，两者不等价。multimodal prefix（视频/音频 embedding）在 vLLM 里要靠 placeholder 对齐，不能直接搬 llama 的 cache key 策略。

---

## 12.3 Batching / Scheduling

| 维度 | llama.cpp-omni | vLLM-Omni |
|---|---|---|
| 调度模型 | slot + ubatch + 显式生命周期 | continuous batching + scheduler |
| prefill/decode 混合 | 手工区分（`is_prefill` / `is_chunk_end`） | scheduler 自动决定 batch 组成 |
| 批大小 | `-b 512 -ub 512` 固定 | 动态（按 KV/memory 预算） |
| 时延/吞吐权衡 | 手动调 ubatch / drain timeout | scheduler 自适应（chunked prefill） |
| 多请求 | 单 session 串行（本项目还修过 thread 泄漏） | 天然多请求并发 |

**迁移要点**：llama 的「explicit lifecycle + slot」在 vLLM 里对应「request 进/出 engine」。llama 的 duplex 单请求模型 vs vLLM 的多请求并发，是架构级差异 —— 迁移后能天然获得并发吞吐，但会失去 llama 侧对单个 session 时延的精细控制。

---

## 12.4 Speculative Decoding

| 维度 | llama.cpp-omni | vLLM-Omni |
|---|---|---|
| 基础设施 | `common/speculative`（SIMPLE/EAGLE3/MTP/ngram，**无 DSpark**） | `SpeculativeConfig` + 各 draft 方法 |
| DSpark | 需 backport（本计划） | `method=dspark`（若上游已支持） |
| draft 加载 | draft GGUF（llama.cpp） | draft HF/safetensors（vLLM） |
| 参数 | `--spec-draft-n-max` | `num_speculative_tokens` |
| 校验 | batched target verify + accept/reject | 同（rejection sampling） |
| 动态 speculation | 无（固定 γ） | `dynamic speculation`（可变 γ） |

**关键**：**同一份训练产物不能不改就跨框架加载** —— llama.cpp 吃 GGUF，vLLM 吃 HF/safetensors（见 §4 转换）。draft TP、`num_speculative_tokens`、动态 speculation 是 vLLM 侧的额外能力。

---

## 12.5 Graph / Launch Optimization

| 维度 | llama.cpp-omni | vLLM-Omni |
|---|---|---|
| 图 | ggml graph / ACL graph（CANN） | CUDA graph / NPU graph（vLLM） |
| launch 开销 | 本项目 profile：logits-sync + embeddings-sync 占 decode 大头 | CUDA graph 捕获消除 launch 开销 |

**本项目血泪教训（必须写入方法论）**：

```
local stage speedup ≠ E2E speedup
```

- 本项目 Phase 7 做过 flow ACL graph 捕获：flow p50 降 20.4%，但 E2E **+11%**（capture tail + CPU vocoder contention）→ **回滚**。
- 任何 graph 优化**必须配对的 E2E A/B**，禁止只报 stage 级数字。

---

## 12.6 Quantization

| llama 经验 | vLLM 对应 |
|---|---|
| Q8_0（W8A16，weight-only） | AWQ / GPTQ / Marlin（W4A16 系） |
| W8A8（本项目 C4 调研，未投产） | FP8（W8A8，vLLM FP8 kv + linear） |
| F16（当前参赛基线） | BF16（vLLM 默认） |

**不要照搬 llama 的量化策略** —— kernel 和 weight format 都不同。迁移后用**官方 accuracy + performance gate** 重新验证，不沿用 llama 的量化结论。

---

## 12.7 Full-duplex 生命周期

llama.cpp-omni 修过的一系列 bug → vLLM-Omni 的映射：

| llama bug/fix | 迁移后是否消失 | 原因 |
|---|---|---|
| LISTEN/SPEAK 状态机楔死（本 session 修的 LISTEN-wedge） | **语义要求仍在** | vLLM 无此状态机，但 duplex 的 turn 边界语义必须重新实现 |
| session 复用上下文污染 | **消失** | vLLM prefix caching 自动保证 KV 一致性 |
| T2W drain 超时/队列 | **语义要求仍在** | Token2Wav 是独立 stage，drain 语义需映射到 vLLM stage scheduler |
| context 复用 | 消失（→ prefix caching） | — |
| thread 泄漏（libgomp per-worker） | 消失 | vLLM engine 无 per-request 新开 OpenMP team |

**结论**：因为 engine 架构而**消失**的 bug（KV 一致性、thread、context 复用）直接受益；**语义要求仍在**的（duplex turn 边界、T2W drain）必须重写为 vLLM 调度原语。

---

## 12.8 Token2Wav 放置

Config D（本项目）→ vLLM-Omni stage 放置：

| Config D | vLLM-Omni |
|---|---|
| Flow CANN（`OMNI_T2W_DEVICE=cann-flow-only`） | Token2Wav stage 设备放置 |
| Vocoder CANN（`OMNI_VOC_DEVICE=gpu:0`） | deploy YAML 指定 device |
| pipeline overlap（`OMNI_T2W_PIPELINE_OVERLAP=1`） | stage 流水线 / 异步调度 |

评估维度：同 NPU / 分 NPU / pipeline overlap / resource contention。

**不要假设更多卡一定更快**（本项目实测 CPU vocoder 在部分配置下反而主导时延）。

---

## 12.9 统一指标表（跨框架可比）

```
TTFT / TPOT / ITL / TTFP
SPEAK→WAV / audio RTF
throughput
acceptance rate / accepted length（speculative）
HBM / CPU / NPU utilization
```

**同一个实验要在两框架下可比** —— 见 `CROSS_FRAMEWORK_PERFORMANCE_METHODOLOGY.md`。
