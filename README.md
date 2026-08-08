# MiniCPM-o 4.5 on Ascend 910C — 推进全记录

> 基于 `llama.cpp-omni` 的全模态模型在昇腾 910C 单卡上的部署优化全过程。
> 以下按时间推进顺序记录每一步的关键发现和积累的进展。

---

## 项目起点

**目标**：在单卡 Ascend 910C 上部署 MiniCPM-o 4.5 全模态模型，优化 SPEAK→WAV 链路 RTF，
通过五道比赛关卡（框架可运行 → 精度准入 → Demo 准入 → 性能排名 → 官方复现）。

**起点**：上游 `llama.cpp-omni` 初始代码，模型加载成功但语音生成链路大部分在 CPU，
服务器稳定性未验证，比赛口径和正式评测环境未对齐。

---

## 第一阶段：基线校准（7月23日–7月28日）

### Commit 考古 — 找到最早的 RUNNABLE F16 提交

比赛要求 F16 权重精度。经过完整的 commit 二分搜索，定位到最早可运行 F16 的提交：

```
ecee7de fix(cann): implement correct dual-path ROPE repeat (neox + non-neox)
```

在此之前，CANN 后端 `aclnnRepeatInterleave` 在 TTS prefill 阶段崩溃（SIGABRT），
所有 GPU TTS 请求无法完成。`ecee7de` 包含了 6 个 RoPE 正确性修复提交的累积效果：

```
aab7964 → fa73697 → 94bb580 → 5fdcddf → 6ec3e1b → ecee7de
```

**关键发现**：此前的 "TTS crash fix"（`tts_gpu_layers=99→0`，把 TTS 强制放到 CPU）
在 `ecee7de` 上不需要，而且有害——F16 TTS 在 CPU 上产生 zero-norm embedding，音频质量归零。
RoPE 修复后，`tts_gpu_layers=99`（GPU TTS）完全正常工作。

同时确认：`ecee7de` 不包含任何 F6 性能优化标记（12 个 marker 全部 absent），
是纯平台支撑基线。

### 双锚点校准——验证测量方法论

使用 `ecee7de` 基线，对官方公布的两个锚点进行交叉验证：

| 指标 | 我们的测量值 | 官方锚点 | 误差 |
|------|------------|---------|------|
| Pipeline Compute RTF | 0.46 | 0.618 (ALL_CHUNK) | −25.4% |
| Pipeline Wall RTF | 0.45 | 1.087 (SPEAK) | −59.0% |

Pipeline RTF = (26.2s LLM decode + 18.2s T2W + 0.7s prefill) / 98s audio

**结论**：我们的 compute RTF 只测量活跃计算时间；官方 ALL_CHUNK_RTF 包含 LISTEN chunk 的 wall clock；
官方 SPEAK_RTF 包含完整的 wall-clock 开销。0.46→1.087 的差距来自：协议开销、队列等待、
空闲调度间隙和 LISTEN chunk 处理时间。

**P0-D Fitness Gate**: ALL PASS — 服务启动、TTS GPU 加载、CANN RoPE、Full Duplex、T2W 音频输出全部通过。

**累积进展**：
- ✅ F16 可运行的 baseline commit 已锁定（ecee7de）
- ✅ 双锚点方法论验证通过
- ✅ P0-D 全部通过

---

## 第二阶段：CANN T2W 迁移（7月28日–8月1日）

### 瓶颈发现

通过 profiling 确认 Token2Wav（Flow + Vocoder）在 CPU 上运行，占首音延迟的 93%，
是 Amdahl 第一瓶颈。

### CANN Flow-Only 发现

环境变量 `OMNI_T2W_DEVICE=cann-flow-only` 将 CANN backend 初始化推迟到 worker thread，
避免跨线程所有权冲突。这被分类为平台支撑（Category B），不是性能优化——它只是让 CANN GPU
能够正确执行。

效果：T2W RTF 从 4.23 骤降到 0.63（**6.7×**）。

### 全链路 CANN 迁移

将 Flow Matching 放到 CANN GPU（cann-flow-only），vocoder 保留 CPU
（"CANN 流跨线程需算子适配"）。全链路 RTF 降至 **0.685**。

### Request-to-First-WAV 实验

最完整的实验：32 对 strict matched pairs，覆盖四种场景（短文本/长文本/带图片/带音频）：

| 指标 | CPU T2W Baseline | CANN T2W Candidate | 变化 |
|---|---:|---:|---:|
| p50 首音延迟 | 4,798 ms | 894 ms | **−81.4%** |
| CI95（bootstrap） | — | [−4,220, −3,732] ms | 不含 0 |

32 对全部 matched pairs，降幅范围 −79% 到 −83%，零 CPU fallback。
WAV 输出 16-bit PCM @24kHz 逐 bit 校验无损。

**累积进展**：
- ✅ 首音延迟从 ~4.8s 降至 ~0.9s
- ✅ T2W GPU 迁移验证（env-only，零源码修改）
- ✅ 全链路 RTF 从 >4 降至 0.685

---

## 第三阶段：服务稳定性（8月1日–8月3日）

### 发现问题

基线服务在连续请求下暴露出多个稳定性问题：
- **线程泄漏**：每 session 增加 ~320 线程（libgomp OpenMP team），
  5-6 session 后触发 cgroup pid 上限（pids.max=10000）导致服务崩溃
- **Drain timeout**：全双工解码不终止，导致 context 失效
- **WS Session 生命周期**：`CTX_STATE_REUSABLE` 未在 session 结束时正确重置

### 修复

- 线程泄漏根因定位：libgomp 为每个 httplib worker 创建 319-thread OpenMP team
  （319 = cpuparams.n_threads-1 = 320-1）。`-t 4` 将 pool 降至 3 线程/session
- WS Session 生命周期统一 finalizer：3 个连续 E2E session 全部通过
- Drain timeout 修复：`OMNI_T2W_DRAIN_TIMEOUT_MS=5000`，CV notify 替代纯 polling
- Fault injection 验证：5 种注入模式全部恢复，服务器在突然断连/快速循环/无效输入下稳定

**累积进展**：
- ✅ 线程泄漏已修复（319→3 per session）
- ✅ 连续 session 生命周期验证通过
- ✅ 故障注入全部通过

---

## 第四阶段：深度性能优化（8月3日–8月5日）

### Static Prefix KV Cache

每次请求开头有一段固定的 system prompt + reference audio embedding，即使内容不变，
prefill 阶段也要重复计算（p50 约 206ms）。

实现 prefix KV cache 复用：首次 save → 后续 load，跳过 prefill 阶段：

| 模式 | Prefill p50 |
|---|---:|
| Cache MISS | 206 ms |
| Cache HIT | 85 ms |
| 加速比 | **2.4×** |

30 组 strict matched pairs 全部通过 KV 完整性校验。

### LLM 量化探索

| 精度 | RTF | LISTEN 占比 | 判定 |
|------|-----|------------|------|
| F16 (baseline) | 0.685 | 0% | — |
| Q8_0 | 0.565 | 0% | **ACCEPT** |
| Q4_K_M | — | 27-40% | **REJECT** |

Q8_0 比 F16 快 17.5%，0% LISTEN（speech generation 行为不变）。Q4_K_M 导致 27-40%
chunk 被模型判定为 LISTEN（speech generation 退化），被明确 REJECT。

### Per-Generation Active + TTS KV Guard

- **per-generation active 计数**：消除跨请求 polling 竞争
- **TTS KV bounds guard**：prefill 阶段 cap 上限，防止长请求上下文越界
- **Drain predicate**：`active_gen==0 || active_gen>N`，正确判断 drain 时机

### 端到端验证

R13 Canonical KV Cache A/B: **30/30 PASS**，FP16+CANN0 server，
prefill 2.4× speedup (206→85ms p50)。

S13 120 Baseline: **120/120 valid**，4 种 case types，p50=17.0s, p95=121.6s，TTS WAV confirmed。

**累积进展**：
- ✅ Static Prefix KV Cache 2.4× prefill 加速
- ✅ Q8_0 量化通过（+17.5% RTF 改善）
- ✅ Per-generation 粒度的 active 追踪
- ✅ TTS KV 边界保护

---

## 第五阶段：Demo 准入与文本接口（8月5日–8月6日）

### Demo 端到端验证

Demo 需要完整的 HTTP/WS 链路：
- Gateway → Worker → Backend 三层架构
- WebSocket Transport 层稳定性
- 文本输出的正确性和完整性

### 修复

- **非流式 text 输出**：非流式响应缺少 text 字段 → 补齐
- **SSE crash**：worker 退出后 `bad_alloc` → worker-once + sink.done guard
- **多模态 prefill 协议**：media_type=2 user_text / think-loop 格式修正
- **Python WS keepalive**：Python WebSocket 默认 ping_interval 导致断连 → `ping_interval=None`
- **UTF-8 中文输出**：L1 Backend 10/10 + L2 Worker 10/10 + L3 Gateway 10/10 = **30/30 PASS**

### SSE Transport Gates

| Gate | 描述 | 结果 |
|------|------|------|
| D3.5-A | Idle 90s 后恢复 | PASS |
| D3.5-B | 长文本不截断 | PASS |
| D3.5-C | 快速切换 session | FAIL（SESSION_CLEANUP_BUG） |
| D3.5-D | 并发 session | FAIL |

D3.5-C/D 的根因已于 `fix/ws-session-lifecycle` 修复（`CTX_STATE_REUSABLE` 重置）。

**累积进展**：
- ✅ Demo 文本 EC 端到端通过
- ✅ 中文 UTF-8 全链路验证（30/30）
- ✅ SSE Transport 稳定性改善
- ✅ 非流式 + 流式文本输出均可工作

---

## 第六阶段：比赛收口与官方对齐（8月6日–8月8日）

### 源码冻结与二进制复现

- **源码冻结**：commit `bdd4550`（candidate source）
- **二进制复现**：`libomni` c4b16937 / `server` db258375
- **T6 冻结二进制回归**：**11/11 PASS**（28/30 KV + 2 A_ERR pairs documented）
- **SOURCE_FREEZE = PASS**，**REPRODUCIBLE_BINARY = PASS**

### 完整文档体系

8 份顶层文档共 2,276 行：
- `F6_QUICKSTART.md` — 快速启动
- `F6_OPTIMIZATION_AND_RESULTS.md` — 完整性能数据
- `F6_ARCHITECTURE.md` — 架构与组件关系
- `F6_METHODOLOGY.md` — 实验方法论
- `F6_REPRODUCTION_GUIDE.md` — 从头复现
- `F6_EVIDENCE_INDEX.md` — 证据索引
- `F6_LIMITATIONS_AND_OFFICIAL_GATES.md` — 已知限制
- `OFFICIAL_GATE_MATRIX.md` — 官方 Gate 矩阵

### 比赛工具链

- RTF 解析器：对齐官方 per-chunk RTF 计算口径
- `valid_audio` 判定：10 种排除原因
- `Gate --dry-run`：支持 0/2/3/4 四种模式
- 私有路径已全部清除

### vLLM-Omni 迁移文档

10 份文档在 `docs/vllm-migration/`，覆盖从 llama.cpp 到 vLLM-Omni 的优化迁移。

### 提交骨架

30 个骨架文件在 `submission/`，覆盖所有比赛提交要求类别。

### 官方 Gate 状态矩阵

```
FINAL_INTERNAL                       = PASS
REPRODUCIBLE_BINARY                  = PASS

OFFICIAL_DAILY_OMNI                  = NOT_RUN  (BLOCKED_BY_OFFICIAL_STARTER_KIT)
OFFICIAL_TTS_SEED                    = NOT_RUN  (BLOCKED_BY_OFFICIAL_STARTER_KIT)
OFFICIAL_VIDEO_MME                   = NOT_RUN  (BLOCKED_BY_OFFICIAL_STARTER_KIT)
OFFICIAL_DEMO_GATE                   = NOT_RUN  (BLOCKED_BY_OFFICIAL_STARTER_KIT)
OFFICIAL_CHUNK_RTF                   = NOT_RUN  (BLOCKED_BY_OFFICIAL_STARTER_KIT)

OFFICIAL_GATES                       = BLOCKED_BY_OFFICIAL_STARTER_KIT
COMPETITION_COMPLETE                 = NOT_CLAIMED
```

**累积进展**：
- ✅ 源码冻结 + 二进制复现验证
- ✅ 完整文档体系（2,276 行，8 份顶层文档）
- ✅ 比赛工具链就绪
- ✅ vLLM 迁移文档（10 份）
- ✅ 提交骨架（30 份文件）
- ⏳ 官方评测全部待运行（等待 Starter Kit）

---

## 不包含的内容

模型权重（MiniCPM-o-4_5-F16.gguf, ~16 GB）、编译产物、音频 profiling 数据、
Demo 视频和官方 Benchmark 结果均不在本仓库中。

## 上游与许可证

本项目基于 [llama.cpp](https://github.com/ggml-org/llama.cpp) 和
[llama.cpp-omni](https://github.com/ggml-org/llama.cpp-omni)，保留上游 MIT License
（[`LICENSE`](LICENSE)）。

模型：[MiniCPM-o 4.5](https://github.com/OpenBMB/MiniCPM-o) by ModelBest & Tsinghua University。

---

> **本仓库为内部比赛交接状态**，不代表官方最终提交。
> `COMPETITION_COMPLETE = NOT_CLAIMED`。最终比赛成绩以主办方在官方环境中重新复现为准。
