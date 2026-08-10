# MiniCPM-o 4.5 on Ascend 910C

> 基于 `llama.cpp-omni` 的全模态模型部署与推理优化项目，面向单卡 Ascend 910C 环境，
> 重点优化从模型完成文本推理到生成首段语音的 Decode-to-Speak 链路。
>
> **当前状态 (2026-08-10):** 🟡 FROZEN — 等待官方统一测评分支

---

## 目录

- [项目背景](#项目背景)
- [当前状态矩阵](#当前状态矩阵)
- [Roadmap](#roadmap)
  - [里程碑与决策点](#里程碑与决策点)
- [推进全记录](#推进全记录)
  - [第一阶段：基线校准](#第一阶段基线校准7月23日7月28日)
  - [第二阶段：CANN T2W 迁移](#第二阶段cann-t2w-迁移7月28日8月1日)
  - [第三阶段：服务稳定性](#第三阶段服务稳定性8月1日8月3日)
  - [第四阶段：深度性能优化](#第四阶段深度性能优化8月3日8月5日)
  - [第五阶段：Demo 准入与文本接口](#第五阶段demo-准入与文本接口8月5日8月6日)
  - [第六阶段：比赛收口与官方对齐](#第六阶段比赛收口与官方对齐8月6日8月8日)
  - [当前阶段：Accuracy 收口](#当前阶段accuracy-收口8月8日至今)
- [分支地图](#分支地图)
- [性能指标](#性能指标)
- [快速开始](#快速开始)
- [文档索引](#文档索引)
- [明天行动计划](#明天行动计划)

---

## 项目背景

本项目来自全模态大模型在昇腾算力平台上的部署优化比赛，对应 **llama.cpp-omni 子赛道**。

比赛要求参赛方案在统一昇腾环境中完成模型部署，并依次通过五道关卡：

```text
框架与环境可运行
        ↓
三项 Benchmark 精度降幅 ≤ 2 个百分点（准入条件）
        ↓
官方 Demo 端到端稳定可用（准入条件）
        ↓
每个 audio chunk 的 RTF（排名依据）
        ↓
主办方在官方环境中重新复现
```

**精度和 Demo 可用性属于准入条件。只有通过这两项检查后，优化版本才会进入性能评测。**
仅能运行 Benchmark、但无法正常接入官方 Demo 的方案，不满足本赛道的准入要求。

目前已完完成内部冻结候选、二进制复现、稳定性回归和比赛工具链准备工作。
Accuracy 评测暂停，等待官方明天（8月11日）提供统一测评分支。性能优化已完成（RTF=0.452 LOCAL_BEST_EFFORT）。

**关键约束：**
- 单卡: 1× Ascend 910C (dual-die, 2× Ascend910 chips)
- 后端: CANN Community Edition 8.5.0.alpha002
- 框架: llama.cpp-omni (FORK from ggml-org/llama.cpp)
- 模型: MiniCPM-o-4_5-F16.gguf (自研 GGUF 转换, 8B 参数)
- 基线: commit `051e993`, 二进制 SHA `768614ab`

---

## 当前状态矩阵

| 维度 | 状态 | 关键指标 |
|------|------|----------|
| **性能** | ✅ COMPLETE | RTF=0.452 (Flow ∥ Vocoder, OMNI_T2W_PIPELINE_OVERLAP=1) |
| **稳定性** | ✅ COMPLETE | 50-reuse + 100-soak, 0 failures |
| **Demo Text** | ✅ COMPLETE | 30/30 valid Chinese UTF-8 via Gateway |
| **Demo Audio** | ✅ COMPLETE | valid WAV output via Gateway |
| **Accuracy** | ⏸️ FROZEN | 等待明天官方统一测评分支 |
| **WS NaN** | 🔬 TRACED | mel 预处理 160/2400 NaN → 等官方分支验证 |
| **Q8_0 contiguous-y** | 🔬 TRACED | [4096,17] multi-token → CANN 算子限制 → 等官方分支验证 |
| **提交就绪** | ❌ NO | 等官方 Accuracy 结果 |

---

## Roadmap

```text
已完成的                                          今天 / 明天                         未来
══════════════════════════════════════════════  ═══════════════════════  ═══════════════════════════
                                                🟡 等待官方统一测评分支
Phase 1: 基线校准 (7/23–7/28)                   │
  ✅ F16 runnable baseline @ ecee7de            │
  ✅ 双锚点校准                                 │
  ✅ 6 CANN RoPE fixes                          │
                                                │
Phase 2: CANN T2W 迁移 (7/28–8/1)               │
  ✅ T2W CPU→NPU (Amdahl 93%)                   │
  ✅ cann-flow-only lazy-init                   │
  ✅ W0 p50 −81.4%                              │
                                                │
Phase 3: 服务稳定性 (8/1–8/3)                    │
  ✅ libgomp × httplib 线程泄漏                 │
  ✅ WS lifecycle 状态机修复                     │
  ✅ CV notify drain                            │
  ✅ Fault injection 5/5                        │
                                                │
Phase 4: 深度性能优化 (8/3–8/5)                  │
  ✅ KV Cache 2.4×                              │
  ✅ Q8_0 ACCEPT / Q4_K_M REJECT                │
  ✅ TTS KV guard + per-gen active              │
  ✅ R13 30/30 + S13 120/120                    │
                                                │
Phase 5: Demo 准入 (8/5–8/6)                    │
  ✅ Gateway→Worker→Backend E2E                  │
  ✅ UTF-8 30/30                                │
  ✅ SSE crash fix                              │
  ✅ 非流式 text 字段                           │
                                                │
Phase 6: 比赛收口 (8/6–8/8)                      │
  ✅ 源码冻结 bdd4550                           │  ┌─────────────────────────┐  ┌─────────────────────────┐
  ✅ T6 冻结二进制 11/11                        │  │ 明天 (8/11)              │  │ 最终                    │
  ✅ 文档 8 份 2,276 行                         │  │                          │  │                         │
  ✅ vLLM 迁移 10 份                            │  │ ① 拉官方统一分支        │  │ ✅ Accuracy 准入通过     │
  ✅ Flow ∥ Vocoder −37.6%                      │  │ ② F16 accuracy 基准     │  │ ✅ Demo 端到端可用       │
  ✅ Gate 工具链就绪                             │  │ ③ Q8_0 accuracy         │  │ ✅ RTF 排名              │
  ✅ Frozen @ 051e993                            │  │ ④ Bug triage            │  │ ✅ 官方环境复现          │
                                                │  │ ⑤ 提交决策              │  │                         │
Phase 7: Accuracy 收口 (8/8–至今)                │  │                          │  │ 提交 🏁                  │
  🔬 NaN 全链追踪完成                           │  └─────────────────────────┘  └─────────────────────────┘
  🔬 Q8 contiguous-y 已定位                     │
  ⏸️  Accuracy 暂停                              │  → 按下 runbook 逐步执行
                                                │    docs/tomorrow-runbook.md
        我们在这里 🟡                             │
────────────────────────────────────────────────┘
```

### 里程碑与决策点

| 日期 | 事件 | 决策 / 结果 |
|------|------|------------|
| 7/23 | 开始 | 确认以 llama.cpp-omni fork 参赛 |
| 7/28 | 发现 T2W CPU 瓶颈 | 停止 LLM decode 优化，全力做 CANN T2W 迁移 |
| 8/1 | CANN T2W 完成 | cann-flow-only 为主力，FM+CANN / Vocoder+CPU |
| 8/3 | 线程泄漏定根 | `-t 4` 固化，修复 lifecycle，稳定性路线图 |
| 8/5 | Q4_K_M REJECT | 确认量化精度天花板，不再探索更激进方案 |
| 8/6 | 源码冻结 | `bdd4550` 锁定，启动冻结二进制回归 |
| 8/8 | 官方规范发布 | 校准 SPEAK 定义、精度阈值、RTF 口径 |
| **8/11** | **官方统一分支** | **开始正式 accuracy + RTF 测量** |
| 8/?? | 提交截止 | 提交最终方案包 |

---

## 推进全记录

> 按时间推进顺序记录每一步的关键发现和累积进展。"攒"起来的过程。

### 第一阶段：基线校准（7月23日–7月28日）

**Commit 考古 —— 找到最早可运行 F16 的提交**：`ecee7de`，包含 6 个 CANN RoPE 正确性修复（aab7964→fa73697→94bb580→5fdcddf→6ec3e1b→ecee7de）。确认不包含任何 F6 性能优化标记（12 个 marker 全部 absent），是纯平台支撑基线。

**关键发现**：此前 "TTS crash fix"（tts_gpu_layers=99→0）在 ecee7de 上不需要且有害——F16 TTS 在 CPU 上产生 zero-norm embedding。RoPE 修复后，tts_gpu_layers=99（GPU TTS）完全正常工作。

**双锚点校准**：Pipeline RTF = (26.2s LLM + 18.2s T2W + 0.7s prefill) / 98s audio = 0.46。P0-D Fitness Gate ALL PASS。

✅ F16 可运行 baseline 锁定 | ✅ 双锚点方法论验证 | ✅ P0-D 全部通过

### 第二阶段：CANN T2W 迁移（7月28日–8月1日）

**瓶颈发现**：T2W（Flow + Vocoder）在 CPU 上运行，占首音延迟 93%。这说明**"先优化 LLM decode"是错误方向**——decode 只占端到端 ~2.9%。

**cann-flow-only 发现**：`OMNI_T2W_DEVICE=cann-flow-only` 将 CANN backend 初始化推迟到 worker thread。T2W RTF 4.23→0.63（**6.7×**）。流式模式下 CANN context 跨线程共享，普通模式 CANN 与 httplib 线程冲突导致 fallback 到 CPU。

**Request-to-first-WAV**：32 strict matched pairs，p50 4798ms→894ms（**−81.4%**），CI95 [−4220,−3732]ms 不含 0。WAV 逐 bit 校验无损。

**理论注记**：CANN 的 stream/context 有线程亲和性——在 thread A 创建的 context 不能在 thread B 使用。cann-flow-only 的关键 trick 是把 CANN 初始化从主线程推迟到 T2W worker thread，绕过了 httplib worker 线程的冲突。

✅ 首音延迟 −81.4% | ✅ 全链路 RTF 0.685 | ✅ 零源码修改

### 第三阶段：服务稳定性（8月1日–8月3日）

**线程泄漏根因**：libgomp 为每个 httplib worker 创建 319-thread OpenMP team（319 = cpuparams.n_threads-1 = 320-1）。这是一个**框架交互型泄漏**：OpenMP 的线程池与 httplib 的请求线程模型不兼容。`-t 4` 降至 3 threads/session。5-6 session 后触发 cgroup pid 上限（pids.max=10000）。

**WS Session 生命周期修复**：`CTX_STATE_REUSABLE` 在 session 结束后未被重置，导致新 session 看到"有活跃 session"而拒绝。根因是 ws_handler.cpp 缺少统一的 finalizer。修复后 3 连续 E2E session 全部通过。

**Drain Timeout 归因**：DRAIN_TIMEOUT 是线程争用的**症状**而非数据丢失。确认 final_dequeued==final_completed，无数据丢失。改成 CV notify 替代纯 polling，500ms polling 退化为安全网。

**Fault injection**：5 种注入模式全部恢复（突然断连、快速循环、无效输入、异常序列、并发冲突）。

**理论注记**：libgomp 的线程模型是 fork-join——每次 `#pragma omp parallel` 创建一个线程 team。httplib 为每个请求创建新线程，导致每次请求触发新的 OpenMP team 创建。这在高并发场景下是灾难性的。修复的本质是限制 OpenMP 线程数（-t 4）和减少不必要的 parallel region。

✅ 线程泄漏已修复 | ✅ 连续 session 生命周期验证 | ✅ 故障注入 5/5

### 第四阶段：深度性能优化（8月3日–8月5日）

**Static Prefix KV Cache**：首次 save → 后续 load。系统提示词 + 音频格式前缀是固定的（130 tokens），这部分 KV 可以在 session 间复用。Prefill p50 206ms→85ms（**2.4×** 加速比）。30 组 KV 完整性校验全部通过。

**理论注记**：Prefill 阶段的计算量是 O(n²)（所有 token attend to 所有之前的 token），而 decode 阶段是 O(n)。Static Prefix 复用的本质是把 O(n²) 中的固定部分缓存，只计算新增部分。

**LLM 量化 A/B**：Q8_0 RTF=0.565（−17.5% vs F16），0% LISTEN → **ACCEPT**。Q4_K_M 27-40% LISTEN → **REJECT**。关键发现：vocoder 在 CPU 上（432ms），量化 LLM 加速被 vocoder 瓶颈掩盖——LLM 越慢，vocoder 的相对占比越大，量化的实际收益越小。

**Per-generation active + TTS KV guard**：消除跨请求 polling 竞争；prefill 阶段 cap 上限（256）。

**R13/S13 验证**：30/30 KV Cache A/B PASS；120/120 valid baseline，4 case types。`S13_STRICT_BASELINE` 120/120 成功（eos=111, max_tokens=9, 0 error）。

✅ KV Cache 2.4× | ✅ Q8_0 +17.5% | ✅ R13/S13 全部通过

### 第五阶段：Demo 准入与文本接口（8月5日–8月6日）

**Demo E2E**：Gateway→Worker→Backend 三层全链路验证。这是比赛准入条件之一——官方 Demo 必须端到端可用。

**UTF-8 中文**：30/30 PASS（L1 Backend 10/10 + L2 Worker 10/10 + L3 Gateway 10/10）。之前出现 `?` 编码腐败的根因是 SSE 流式响应的 worker-once 生命周期问题——worker 在响应中途被销毁导致 sink.done 未调用。

**文本接口修复**：非流式 text 字段补齐、SSE crash（std::bad_alloc in httplib write_response_core）修复。多模态 prefill 协议修正（media_type=2 user_text / think-loop 格式）。发现了关键协议陷阱：omni_init 后的第一次 stream_prefill 被 system-prompt 初始化分支吞掉用户内容（omni.cpp:12906），正确的协议是两次 prefill（cnt:0 初始化 → cnt:1 用户内容）。

**SSE Transport**：D3.5-A/B PASS（idle 90s 恢复、长文本不截断），D3.5-C/D 根因定位于 `fix/ws-session-lifecycle`。

✅ Demo E2E 通过 | ✅ UTF-8 30/30 | ✅ Streaming + 非流式均可工作

### 第六阶段：比赛收口与官方对齐（8月6日–8月8日）

**源码冻结**：commit bdd4550（candidate source）。**T6 冻结二进制回归 11/11 PASS**（28/30 KV + 2 A_ERR pairs documented）。SOURCE_FREEZE=PASS, REPRODUCIBLE_BINARY=PASS。

**文档体系**：8 份顶层文档 2,276 行。涵盖 Quickstart、架构、方法论、复现指南、证据索引、限制与 Gate。

**比赛工具链**：RTF 解析器 + valid_audio 判定（10 种排除原因）+ Gate --dry-run（0/2/3/4）+ 私有路径清除。

**vLLM 迁移文档**：10 份文档在 `docs/vllm-migration/`，覆盖组件映射、经验迁移、执行计划、风险矩阵、团队交接。

**性能冻结**：Flow ∥ Vocoder pipeline (OMNI_T2W_PIPELINE_OVERLAP=1) 将串行 T2W 改为流水线并行，601→375ms/window (−37.6%)。最终 F16 候选二进制 SHA 768614ab @ commit `051e993`。

✅ 源码冻结 + 二进制复现 | ✅ 完整文档体系 | ✅ 比赛工具链就绪

### 当前阶段：Accuracy 收口（8月8日–至今）

**状态**：🟡 FROZEN，等待官方统一测评分支。

官方 organizer 确认："预计明天上午提供有统一测评的分支"。当前所有 Cookbook/自定义 evaluator 的结果不作为最终 Accuracy 结论。

**已完成的 P0 调查**：

- **WS 多模态 NaN logits**：已追踪至 mel 频谱预处理阶段（`whisper_input_mel` 160/2400 NaN）。NaN 传播链已完整记录。根因在 `log_mel_spectrogram_worker_thread()` 中——mel filterbank 输出产生 NaN 值，经 Whisper encoder 全量传播到 LLM logits。详见 [WS NaN 调查报告](docs/ws-nan-investigation.md)。

- **Q8_0 contiguous-y 错误**：Prompt Bundle 开启时 `[4096,17]` 多 token prefill 触发 CANN `aclnnWeightQuantBatchMatmulV2` 的 contiguous y 约束。属于后端 layout 兼容性问题。此错误与官方评测路径可能无关。

**明天计划**：拉官方统一分支 → 先 F16 → 再 Q8_0 → 重新评估所有 Accuracy 项。只有在官方分支上复现的 bug 才是真 P0。

⏳ Accuracy 最终结果 | ⏳ 提交就绪判定

---

## 分支地图

> 所有分支的完整地图，含理论背景说明。详见 [docs/branch-map.md](docs/branch-map.md)。

### 核心链路（依赖顺序）

```text
eval/official-baseline (官方 Demo 基线)
  └─ fix/f003-cann-rope-repeat-interleave (CANN RoPE → GPU TTS 可用)
      └─ fix/ws-session-lifecycle (WS 生命周期 → persistent server)
          └─ fix/tts-thread-lifecycle (线程泄漏 → libgomp OpenMP 模型)
              └─ fix/full-duplex-request-max-tokens (full_duplex max_tgt_len=0)
                  └─ perf/f6-decode-to-speak (CANN T2W 设备放置)
                      └─ perf/flow-chunk-rtf (Flow chunk RTF 离线)
                          └─ main ← 051e993 (FROZEN BASELINE)
                              └─ fix/ws-multimodal-nan (NaN 调查, NOT merged)
```

### 分支分类速览

| 类别 | 分支 | 用途 | 关键理论点 |
|------|------|------|-----------|
| **主** | `main` | 提交主分支 @ 051e993 | F16 冻结 + 全部优化已合入 |
| **稳定性** | `fix/ws-session-lifecycle` | WS 生命周期修复 | CTX_STATE_REUSABLE 状态机 + CV 通知替代轮询 |
| | `fix/tts-thread-lifecycle` | 线程泄漏修复 | libgomp fork-join 与 httplib 线程模型不兼容 |
| | `fix/full-duplex-request-max-tokens` | duplex max_tgt_len=0 | full_duplex 路径遗漏 request_max_tokens 传播 |
| | `fix/f003-cann-rope-repeat-interleave` | CANN RoPE fix | CANN 算子不支持非标准 interleave 模式 |
| | `fix/ws-multimodal-nan` | NaN 调查 | mel 预处理 NaN → Whisper → LLM 全链传播 |
| **性能** | `perf/f6-decode-to-speak` | CANN T2W | CANN stream 线程亲和性 + 设备放置 |
| | `perf/flow-chunk-rtf` | Flow chunk RTF | 离线测量每 chunk RTF 不依赖服务 |
| | `perf/kv-cache-production-gates` | KV Cache | Static prefix 复用 O(n²)→O(n) 计算量转移 |
| | `perf/operator-decode-speak` | 算子分解 | decode→speak 子组件级 profiling |
| | `perf/ngl8-e2e-stage-profiling` | E2E profiling | NGL8 多卡 stage 级性能追踪 |
| **实验** | `exp/token2wav-cann-runtime` | CANN runtime | FM+CANN vs CPU fallback 对比 |
| | `exp/f003-neox-layout` | NeoX layout | GPT-NeoX 权重布局的 CANN 适配 |
| | `exp/f004-precision-ablation` | precision ablation | FP16→FP32→Q8 精度衰减链 |
| **优化** | `opt/r4.2-t2w-trt` | T2W TRT | TensorRT 后端替换方案 |
| | `opt/r4.3-vit-trt` | ViT TRT | Vision encoder TRT 优化 |
| **功能** | `feat/omni-duplex-r2` | 全双工 R2 | duplex session 状态机重构 |
| | `feat/ascend-cann` | CANN backend | Ascend NPU 算子适配全链路 |
| | `feat/web-server` | HTTP API | RESTful 推理接口 |
| | `feat/web-demo` | Web Demo | Gateway + Worker 双层架构 |
| | `feat/speed-test` | 测速工具 | 标准化延迟/吞吐 benchmark |

---

## 性能指标

### F16 最终候选 (051e993)

```
SPEAK→WAV RTF (LOCAL_BEST_EFFORT): 0.452
  └─ Flow ∥ Vocoder pipeline:      1.60× speedup (601→375ms/window)
  └─ CANN T2W placement:           −81.4% W0 latency (4798→894ms p50)
  └─ KV Cache static prefix:       2.4× prefill speedup (206→85ms p50)
  └─ -t4 thread config:            optimal (vs -t8: decode 14% slower)

Sub-component breakdown (per chunk):
  LLM decode:       ~142ms (2.9%)
  T2W (Flow+CANN):  ~189ms
  T2W (Vocoder+CPU): ~432ms (bottleneck — 76% of T2W)
  Prefill (KV hit): ~85ms
```

### 硬件

| 项目 | 规格 |
|------|------|
| 平台 | 1× Ascend 910C (dual-die) |
| 芯片 | 2× Ascend910 chips |
| CANN 版本 | Community Edition 8.5.0.alpha002 |
| NPU 内存 | ~60 GB HBM |
| CPU | Kunpeng 920 |

---

## 快速开始

### 构建

```bash
cd /workspace/llama.cpp-omni-session-fix
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON
cmake --build . --target llama-omni-server -j$(nproc)
```

### 启动服务（F16 最终候选）

```bash
OMNI_T2W_PIPELINE_OVERLAP=1 \
OMNI_T2W_DEVICE=cann-flow-only \
build/bin/llama-omni-server \
  -m /workspace/models/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf \
  --host 127.0.0.1 --port 18094 \
  -ngl 999 --device CANN0 \
  --ctx-size 4096 --batch-size 512 --ubatch-size 512 \
  --split-mode layer -t 4
```

### 诊断环境变量

| 变量 | 默认 | 作用 |
|------|------|------|
| `OMNI_T2W_PIPELINE_OVERLAP=1` | 0 | 开启 Flow ∥ Vocoder 流水线并行 |
| `OMNI_T2W_DEVICE=cann-flow-only` | (空) | T2W Flow 模块放 CANN NPU |
| `OMNI_T2W_DRAIN_TIMEOUT_MS=5000` | 自动 | T2W drain 超时毫秒 |
| `OMNI_NAN_DIAG=1` | 0 | NaN 诊断追踪（零开销 gating） |
| `OMNI_T2W_QUEUE_DIAG=1` | 0 | T2W 队列积压诊断 |
| `OMNI_ENCODING_DIAG=1` | 0 | UTF-8 编码链路诊断 |
| `GGML_CANN_W8A8=1` | 0 | W8A8 量化 MatMul（opt-in，非默认） |
| `OMNI_KV_CACHE_REUSE=1` | 0 | 静态前缀 KV Cache 复用 |

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [STATUS.md](STATUS.md) | 实时项目状态（更新最频繁） |
| [docs/branch-map.md](docs/branch-map.md) | 26 分支完整地图（HEAD、依赖链） |
| [docs/ws-nan-investigation.md](docs/ws-nan-investigation.md) | WS 多模态 NaN 调查报告 |
| [docs/w8a8-cann-quant-matmul.md](docs/w8a8-cann-quant-matmul.md) | W8A8 量化 MatMul (Phase C) |
| [docs/F6_S13_FINAL_GATE_CLOSURE.md](docs/F6_S13_FINAL_GATE_CLOSURE.md) | 最终 Gate 收口 |
| [docs/F6_PHASE2_STEP6_CANN_T2W_AB.md](docs/F6_PHASE2_STEP6_CANN_T2W_AB.md) | CANN T2W A/B 详细 |
| [docs/F6_PHASE2_BASELINE_DEVICE_AUDIT.md](docs/F6_PHASE2_BASELINE_DEVICE_AUDIT.md) | 基线设备放置审计 |
| [docs/vllm-migration/README.md](docs/vllm-migration/README.md) | vLLM 迁移文档入口 |

---

## 明天行动计划

1. 拉取官方统一测评分支 → 记录官方 commit SHA
2. 按官方命令不变运行
3. **先 F16**（Accuracy 基准）
4. **再 Q8_0**
5. 重新评估：
   - Daily-Omni / VideoMME / TTS-Seed accuracy
   - WS NaN（`OMNI_NAN_DIAG=1`）
   - Q8_0 contiguous-y 错误
6. 只有在官方分支上**复现**的 bug 才升级为 P0 提交阻塞项
7. 不在官方分支上复现 → 分类为 `ARTIFACT_OF_NON_UNIFIED_EVAL_PATH` → 关闭

---

> 冻结时间: 2026-08-10 | 基线: 051e993 | 二进制: 768614ab | 状态: `WAIT_OFFICIAL_UNIFIED_EVAL_BRANCH`
