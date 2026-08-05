# F6 Decode-to-Speak 优化项目

> **文档 HEAD**: `DOCUMENTATION_HEAD`（非候选源码 commit）
> **候选源码 commit**: `bdd4550`
> **状态**: `FINAL_INTERNAL=PASS` / `OFFICIAL_GATES=BLOCKED_BY_OFFICIAL_STARTER_KIT`

## 一句话

在 llama.cpp-omni（MiniCPM-o 4.5）上，针对 Ascend 910C 单卡 + CANN 9.1.0-beta.1，通过**设备放置修正**（T2W Flow/Vocoder 从 CPU 搬到 CANN NPU）和 **KV Cache 生产化**（静态 prefix 复用），将 Request→W0（HTTP 请求到首个 WAV 文件）p50 从 4,798ms 降至 894ms（−81.4%，32 对严格配对，CI95 [−4220,−3732]），并完成内部冻结。

> ⚠️ **−81.4% 是 Request→W0 p50 的配对 A/B 结果，不是官方 chunk RTF、不是全请求 E2E、不是 vLLM 结果。详见下方完整指标定义。**

---

## 比赛任务与正式指标

```
任务: Ascend 硬件适配与优化（MiniCPM-o 全模态推理）
官方指标: per-chunk RTF / Daily-Omni 准确率 / Seed-TTS-Eval / Video-MME
当前状态: 内部冻结候选已完成；三项官方 Benchmark NOT_RUN (BLOCKED_BY_OFFICIAL_STARTER_KIT)
```

---

## 当前冻结版本

| 资产 | SHA256 | 状态 |
|------|--------|------|
| 候选源码 | `bdd4550` | `FROZEN`（不得修改） |
| llama-omni-server | `db258375c3d2185ca2181da2a5c8f99a95d381413fcb7ab92a771850ba3a4a21` | `REPRODUCIBLE_BINARY=PASS` |
| libomni.so | `c4b169376bced6bc3107cfda2f77abf35a634c1e146eed313a193e99e3739ea1` | `REPRODUCIBLE_BINARY=PASS` |
| 模型 | `d1e69845…`（MiniCPM-o-4_5-F16.gguf, 16.38 GB） | `FROZEN` |

---

## 请求与生成链路

```
Client HTTP/WS
  → omni_init (模型加载, KV cache 初始化)
  → Prefill (Vision/Audio encode → prompt embedding)
  → Main LLM Decode → "<|speak|>" decision
  → Talker (text→speech tokens, 复用主 LLM KV cache)
  → T2W Queue → Flow (DiT) → Vocoder (HiFi-GAN)
  → WAV chunk → Streaming HTTP response
```

---

## 内部验证状态表

| 项目 | 状态 | 关键证据 |
|------|------|---------|
| 环境部署 (910C + CANN 9.1.0-beta.1) | `PASS` | env_check.sh |
| 模型加载 (MiniCPM-o-4_5-F16.gguf) | `PASS` | SHA d1e69845 |
| CANN 主模型 (LLM decode) | `PASS` | `supports_op` 全覆盖, 0 CPU fallback |
| Static Prefix KV Cache | `PASS` | 30/30 strict pairs, prefill 2.4× |
| Persistent 生命周期 | `PASS` | 3 seq requests ok, ctx valid |
| CANN Flow/Vocoder (T2W) | `PASS` | W0 4798→894ms (−81.4%), 32/32 pairs |
| TTS KV bounds | `PASS` | T13 boundary test PASS, guard=39 |
| 非流式 text 输出 | `PASS` | T9 fix: text field + worker-once |
| SSE 稳定性 | `PASS` | T9 fix: sink.done crash resolved |
| T6 集成回归 | `PASS` | **11/11 gates, ACCEPT=True** |
| Daily-Omni 内部 pilot | `PASS` | 6/6 server gates |
| 二进制可复现构建 | `PASS` | build-twice-same-dir byte-identical |
| 提交工具链 | `PASS` | selftest 14/14 |
| CANN CPU/NPU 放置审计 | `PASS` (static) | `docs/audit/` 5 docs |
| 官方 Daily-Omni | `NOT_RUN` | `BLOCKED_BY_OFFICIAL_STARTER_KIT` |
| 官方 TTS-Seed | `NOT_RUN` | `BLOCKED_BY_OFFICIAL_STARTER_KIT` |
| 官方 Video-MME | `NOT_RUN` | `BLOCKED_BY_OFFICIAL_STARTER_KIT` |
| 官方 Demo | `NOT_RUN` | `BLOCKED_BY_OFFICIAL_STARTER_KIT` |
| 官方 per-chunk RTF | `NOT_RUN` | `BLOCKED_BY_OFFICIAL_STARTER_KIT` |

---

## 核心优化摘要

| # | 优化 | 方法 | 决策 |
|---|------|------|------|
| 1 | CANN T2W (Flow+Vocoder) | env-only: `OMNI_T2W_DEVICE=cann-flow-only` `OMNI_VOC_DEVICE=gpu` | **ACCEPT** |
| 2 | Static Prefix KV Cache | prefetch prompt → prefill → save → reuse across requests | **ACCEPT** (30/30) |
| 3 | Persistent Server 生命周期 | 多请求复用同一 ctx, 修复 drain/timeout | **ACCEPT** |
| 4 | TTS KV bounds guard | n_past cap + deterministic boundary test | **ACCEPT** |
| 5 | 非流式 text + SSE 修复 | worker-once + sink.done | **ACCEPT** |
| 6 | B6b (早期 TTS 阈值 10→5) | Chunk scheduling threshold | **REJECT** (CI 跨 0) |

---

## 核心结果摘要

### T2W 设备放置（Phase 2, Step 6）

| 指标 | Baseline (CPU T2W) | Candidate (CANN T2W) | Δ |
|------|-------------------:|---------------------:|----:|
| Request→W0 p50 | 4,798 ms | 894 ms | **−3,904 ms (−81.4%)** |
| CI95 | — | [−4,220, −3,732] | 不含 0 |
| 样本 | 32 pairs | 32 pairs | 同 binary/硬件/模型/输入 |
| 证据 | `docs/F6_PHASE2_STEP6_CANN_T2W_AB.md` | `docs/f6-s13-closure/phase2/step6_cann_t2w_ab.json` | `INTERNAL` |

> **计时口径**: HTTP request arrival → 首个 WAV 文件写入完成的墙上时钟。同 binary (e159b3ee 早期 commit，后续 commit 保持此收益)、同 910C 硬件、同 MiniCPM-o-4_5-F16.gguf 模型、同 32 组 prompt 输入、同 HTTP 协议。
>
> ### −81.4% 完整指标定义
>
> | 字段 | 值 |
> |------|-----|
> | **Metric** | Request→W0 p50（HTTP request arrival → first WAV file mtime，wall clock） |
> | **计时起点** | HTTP POST /v1/stream/decode arrival |
> | **计时终点** | 首个 WAV chunk 文件写入完成（mtime） |
> | **Baseline** | 4,798 ms（CPU T2W: `OMNI_T2W_DEVICE` unset，`OMNI_VOC_DEVICE` unset） |
> | **Candidate** | 894 ms（CANN T2W: `OMNI_T2W_DEVICE=cann-flow-only`，`OMNI_VOC_DEVICE=gpu`） |
> | **绝对变化** | −3,904 ms |
> | **相对变化** | −81.4% |
> | **CI95** | [−4,220, −3,732]（bootstrap，10,000 resamples），不含 0 |
> | **样本** | 32 strict matched pairs（同 binary/硬件/模型/输入/协议/计时边界） |
> | **Hardware** | Ascend 910C dual-die，CANN 9.1.0-beta.1 |
> | **Commit** | e159b3ee（早期 Phase 2 commit；收益在后续 commit 包括 bdd4550 中保持） |
> | **Raw** | `docs/f6-s13-closure/phase2/step6_cann_t2w_ab.json` |
> | **Report** | `docs/F6_PHASE2_STEP6_CANN_T2W_AB.md` |
> | **Status** | `HISTORICAL_INTERNAL_RESULT` — 非官方 chunk RTF、非全请求 E2E、非 vLLM 结果 |
> | **适用范围** | 内部 Phase 2 瓶颈验证；不得描述为"官方 chunk RTF −81%"或"首包语音总时延 −81%" |

### Static Prefix KV Cache（Phase 3, R13）

| 指标 | MISS (无 cache) | HIT (有 cache) | Δ |
|------|----------------:|---------------:|----:|
| Prefill p50 | 206 ms | 85 ms | **−121 ms (−58.7%, 2.4×)** |
| 样本 | 30 strict matched pairs | 30 strict matched pairs | — |
| 证据 | `docs/f6-s13-closure/phase2/T6_INTEGRATED_REGRESSION_REPORT.md` | `docs/tracking/f6_lifecycle/R13_CANONICAL_STATIC_PREFIX_AB_FINAL.md` | `INTERNAL` |

### 稳定性回归

| Gate | 结果 |
|------|------|
| T6 集成回归 | **11/11 PASS** (S13 120/120, KV A/B 28/30 valid, Extended 30/30, Voice 5/5, Disconnect 5/5, Smoke 5/5, cpu_fallback=0, cann_error=0) |
| S13 120 Baseline | **120/120 valid**, p50=17.0s, p95=121.6s |

---

## 不要误解

- **`-ngl 999` ≠ 零 CPU 参与** — input/index/control tensor、KV metadata、D2H logits/hidden、sampler、tokenizer 仍在 CPU/Host。详见 `docs/audit/CANN_CPU_NPU_PLACEMENT_AUDIT.md`。
- **内部 RTF ≠ 官方 chunk RTF** — 内部 RTF（G7 日志 p50=0.23, S13 p50=0.28）使用 `T2W线程` 日志行自测，不等同于官方 Harness 产出的 per-chunk RTF。
- **Daily-Omni pilot ≠ 官方准确率** — pilot 仅验证 6/6 server gates 和链路通畅，非官方全量评测。
- **`FINAL_INTERNAL` ≠ `COMPETITION_COMPLETE`** — 内部冻结候选已闭环；官方比赛完成需三项 Benchmark + Demo + chunk RTF 全部 PASS。

---

## 文档导航

### 分层阅读

| 时间 | 文档 |
|------|------|
| 5 分钟 | `F6_README.md`（你在这里） |
| 15 分钟 | + `F6_QUICKSTART.md` + `F6_OPTIMIZATION_AND_RESULTS.md` |
| 30 分钟 | + `F6_ARCHITECTURE.md` + `F6_METHODOLOGY.md` |
| 完整交接 | + `F6_REPRODUCTION_GUIDE.md` + `F6_EVIDENCE_INDEX.md` + `F6_LIMITATIONS_AND_OFFICIAL_GATES.md` |
| vLLM 队友 | `docs/vllm-migration/` |

### 完整索引

```
docs/
├── F6_README.md                          ← 项目入口（你在这里）
├── F6_QUICKSTART.md                      ← 5 分钟跑起来
├── F6_ARCHITECTURE.md                    ← 全模态链路架构
├── F6_OPTIMIZATION_AND_RESULTS.md        ← 每项优化的证据与决策
├── F6_METHODOLOGY.md                     ← 方法论与工程纪律
├── F6_REPRODUCTION_GUIDE.md              ← 从 clean checkout 到结果核验
├── F6_LIMITATIONS_AND_OFFICIAL_GATES.md  ← 已证明 / 未证明 / 被阻塞
├── F6_EVIDENCE_INDEX.md                  ← 每个结论→raw/commit/源码
│
├── f6-s13-closure/                       ← 冻结证据归档 (DO NOT MODIFY)
├── tracking/                             ← 170+ 工程追踪
├── audit/                                ← CANN CPU/NPU 放置审计
├── competition-submission/               ← 比赛提交文档
├── vllm-migration/                       ← vLLM 迁移文档
└── experiments/                          ← 实验记录
```

---

## 最短执行入口

```bash
cd /workspace/llama.cpp-omni-f6

# 1. 环境检查
MODEL_PATH=/path/to/MiniCPM-o-4_5-F16.gguf \
  bash submission/environment/env_check.sh

# 2. 离线自检（不起服务）
SELFTEST_MODEL_PATH=/path/to/MiniCPM-o-4_5-F16.gguf \
  bash submission/tests/run_selftest.sh

# 3. 构建
cmake -B build -DGGML_CANN=ON -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON
cmake --build build --target llama-omni-server

# 4. 启动 + 冒烟
# 详见 F6_QUICKSTART.md
```

---

## 已知限制

- 官方三项 Benchmark（Daily-Omni / TTS-Seed / Video-MME）尚未执行 — `BLOCKED_BY_OFFICIAL_STARTER_KIT`
- 官方 Demo 尚未接入
- 内部 pilot 样本规模有限（非全量官方评测集）
- SSE + `use_tts=true` 有已知边界（duplex/slide 交互复杂度）
- Whisper 音频编码输入上限
- 单会话并发限制（非多用户并发优化）
- 二进制 SHA 仅在目标环境两次 clean rebuild 确认逐字节一致；不同环境可能因工具链/rpath 不同而有差异
