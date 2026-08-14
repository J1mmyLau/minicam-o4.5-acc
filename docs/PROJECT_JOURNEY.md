# 项目脉络 — MiniCPM-o 4.5 昇腾赛道全记录（2026-07-23 → 08-14）

> 本文件是 llama.cpp-omni 昇腾赛道（华为 Ascend 910C）从开赛到最终交付的**完整项目脉络**。
> 覆盖：**优化 / 实验 / 踩坑 / 官方发资料的节点 / vLLM 迁移**。
> 数据与结论以 `docs/competition-submission/`（权威提交文档）与 `docs/F6_*`（证据链）为准。
> 最终交付分支 = `competition/final-ascend-track-a`（源码冻结 `fd3dd36`）。

---

## 0. 官方发资料的节点（时间轴）

> 官方资料每次到位的节点，决定了我们「从猜着做 → 对齐官方口径」的转折点。

| 日期 | 官方动作 | 对项目的影响 |
|---|---|---|
| **07-23** | 开赛 + 框架 baseline（F16 可运行环境） | 项目启动；锁定最早可运行 F16 基线 `ecee7de` |
| **08-05** | **官方 spec 到位**：SPEAK→WAV RTF 基线 `1.087` + 4 项精度阈值；Demo 仓库克隆 @ `ba7fa9c` | 从「内部优化」转入「对齐官方口径」；RTF 从此有可比基线 |
| **08-06~08** | 官方承诺提供统一测评分支（"预计明天上午"） | 进入 Accuracy 收口阶段（实际持续延迟） |
| **08-14** | **Starter Kit 仍未收到** | 官方 eval 全程 `NOT_RUN`（`BLOCKED_BY_OFFICIAL_STARTER_KIT`），提交完成声明 `NOT_CLAIMED` |

> 关键判断：官方基线 **1.087** 是 08-05 才给的。此前我们自测的 RTF 0.23~0.685 用的是**内部口径**（T2W 线程内部计时 / wall-clock），与官方 1.087 不可比（见 `RTF_PARSER_AUDIT.md`）。官方 RTF 的 SPEAK→WAV 完整链路口径直到 08-05 才明确。

---

## 1. 时间线总览

| 阶段 | 日期 | 关键成果 | 主要踩坑 |
|---|---|---|---|
| ① 基线校准 | 07-23 ~ 07-28 | 锁定 F16 可运行基线 `ecee7de`，双锚点 RTF 0.46 | TTS "crash fix" 有害（见踩坑 1） |
| ② CANN T2W 迁移 | 07-28 ~ 08-01 | T2W 上 CANN，W0 −81.4%（4798→894ms） | CANN 线程亲和性（踩坑 2） |
| ③ 服务稳定性 | 08-01 ~ 08-03 | 线程泄漏修复 + WS 生命周期 | libgomp 线程泄漏（踩坑 3/4） |
| ④ 深度性能优化 | 08-03 ~ 08-05 | KV Cache 2.4× + Q8_0 +17.5% + Flow∥Vocoder | Q8_0 量化反而更慢（踩坑 13） |
| ⑤ Demo 准入与文本接口 | 08-05 ~ 08-06 | Demo E2E + UTF-8 30/30 | SSE worker-once（踩坑 5/6） |
| ⑥ 比赛收口与官方对齐 | 08-06 ~ 08-08 | 源码冻结 + vLLM 迁移文档 + 工具链 | — |
| ⑦ Accuracy 收口 / NaN saga | 08-08 ~ 08-11 | NaN 根因定位 + 修复 | FA mask 回归 + aclnnMm NaN（踩坑 7/8） |
| ⑧ Seed-TTS WER=100% → 1.422% | 08-09 ~ 08-11 | 三污染源修复，2020/2020 PASS | 三污染源（踩坑 9） |
| ⑨ Config D + RTF 解锁 | 08-11 ~ 08-13 | Config D 6 变量 + LISTEN-wedge 修复，RTF AVAILABLE | LISTEN-wedge 楔死（踩坑 10/11） |
| ⑩ 最终交付 | 08-13 ~ 08-14 | 冻结 `fd3dd36` + 提交收口 + push | Starter Kit 缺位 |

---

## 2. 分阶段详述（优化 + 实验 + 踩坑）

### ① 基线校准（07-23 ~ 07-28）

- **Commit 考古**：找到最早可运行 F16 的提交 `ecee7de`（6 个 CANN RoPE 正确性修复 aab7964→…→ecee7de），确认无任何 F6 性能优化标记（12 marker 全 absent）——纯平台支撑基线。
- **关键发现**：此前 "TTS crash fix"（`tts_gpu_layers=99→0`）在 `ecee7de` 上**不需要且有害**——F16 TTS 在 CPU 上产生 zero-norm embedding；RoPE 修复后 GPU TTS（`tts_gpu_layers=99`）完全正常。
- **双锚点校准**：Pipeline RTF = (26.2s LLM + 18.2s T2W + 0.7s prefill) / 98s audio = **0.46**。P0-D Fitness Gate 全 PASS。

### ② CANN T2W 迁移（07-28 ~ 08-01）

- **瓶颈定位**：T2W（Flow + Vocoder）跑在 CPU，占首音延迟 **93%**——「先优化 LLM decode」是错误方向（decode 只占 E2E ~2.9%）。
- **`cann-flow-only` 发现**：`OMNI_T2W_DEVICE=cann-flow-only` 把 CANN 初始化从主线程推迟到 T2W worker 线程，T2W RTF **4.23→0.63（6.7×）**。
- **Request-to-first-WAV**：32 strict matched pairs，W0 p50 **4798→894ms（−81.4%）**，CI95 [−4220,−3732]ms 不含 0，WAV 逐 bit 校验无损。
- **理论注记**：CANN stream/context 有**线程亲和性**——thread A 创建的 context 不能在 thread B 用；httplib 每请求一线程，导致 fallback 到 CPU。

### ③ 服务稳定性（08-01 ~ 08-03）

- **线程泄漏根因**：libgomp 为每个 httplib worker 创建 319-thread OpenMP team（319 = `cpuparams.n_threads-1`）。fork-join 模型 × httplib 请求线程 = 每请求新建 team，5-6 session 后触发 cgroup pid 上限（pids.max=10000）。`-t 4` 降至 3 threads/session。
- **WS 生命周期**：`CTX_STATE_REUSABLE` 未在 session 结束重置 → 新 session 被拒；修复 = ws_handler.cpp 统一 finalizer。
- **Drain timeout 归因**：是线程争用的**症状**而非数据丢失（`final_dequeued==final_completed`）；CV notify 替代纯 polling。
- **故障注入**：5 种注入模式全部恢复。

### ④ 深度性能优化（08-03 ~ 08-05）

- **Static Prefix KV Cache**：系统提示 + 音频格式前缀固定（130 tokens）可在 session 间复用，prefill p50 **206→85ms（2.4×）**，30/30 KV 校验通过。
- **LLM 量化 A/B**：Q8_0 RTF=0.565（−17.5% vs F16，0% LISTEN）→ ACCEPT；Q4_K_M 27-40% LISTEN → REJECT。⚠️ Q8_0 的 −17.5% 其实来自 vocoder-CPU 而非 LLM decode（量化的真实收益被 vocoder 瓶颈掩盖）。
- **Flow∥Vocoder 流水线**：`OMNI_T2W_PIPELINE_OVERLAP=1`，601→375ms/window（**1.60×**，−37.6%）。
- **R13/S13**：30/30 KV A/B + 120/120 valid baseline。

### ⑤ Demo 准入与文本接口（08-05 ~ 08-06）

- **Demo E2E**：Gateway→Worker→Backend 三层全链路（比赛准入条件之一）。
- **UTF-8 中文 30/30**：L1 Backend 10/10 + L2 Worker 10/10 + L3 Gateway 10/10。`?` 编码腐败根因 = SSE 流式响应 worker-once 生命周期（worker 中途销毁 → sink.done 未调用）。
- **协议陷阱**：omni_init 后第一次 stream_prefill 被 system-prompt 初始化分支吞掉用户内容（omni.cpp:12906）；正确协议 = 两次 prefill（cnt:0 初始化 → cnt:1 用户内容）。
- **文本接口**：非流式 text 字段补齐 + SSE crash（httplib `write_response_core` 的 `std::bad_alloc`）修复。

### ⑥ 比赛收口与官方对齐（08-06 ~ 08-08）

- **源码冻结**：candidate source `bdd4550`；T6 冻结二进制回归 11/11 PASS；`SOURCE_FREEZE=PASS` + `REPRODUCIBLE_BINARY=PASS`。
- **文档体系**：8 份顶层文档 2,276 行。
- **比赛工具链**：RTF 解析器 + valid_audio 判定（10 排除原因）+ Gate `--dry-run` + 私有路径清除。
- **vLLM 迁移文档**：10 份文档落地 `docs/vllm-migration/`（见 §4）。
- **性能冻结**：F16 候选二进制 SHA `768614ab` @ `051e993`。

### ⑦ Accuracy 收口 / NaN saga（08-08 ~ 08-11）

> 这是全程最重的一条踩坑链——**四层 NaN 嵌套**，每层都要定位。

- **现象**：所有带 audio/video 的 WS 路径 logits 全 NaN → 文本全 "?"（token 30）；image-only 干净。
- **根因（逐层）**：
  1. **FA mask 回归 `b6b6af0`**：raw `-Inf`→`pseShift`、`mask=nullptr`（vs pristine 的 BOOL-mask+Clamp）→ 长多模态 logits NaN。这是 integrated 分支引入 NaN 的**总根**。
  2. **`aclnnMm` 从 FINITE 输入产生 NaN**：MUL_MAT node_27（attention output projection，weight `[4096,4096]` × act `[4096,15]`），CANN 运行时 execution-context 相关（非值驱动、非 shape 依赖），3 个窄 workaround 全失败。
  3. **FusedInferAttentionScoreV2**：Q≥435 at KV≥768 触发 NaN（text-only 也触发，非 multimodal 专属）。
- **结论**：pristine `c9785cc` + native CANN = **0 NaN**；NaN 全部由 integrated 分支引入。
- **修复**：FA-local Q split（`DO_NOT_PROMOTE`）+ 全局 `OMNI_CANN_FA_MAX_UBATCH=16`（+5.3% 开销）。窄 workaround 不可行 → 接受 +5.3% 换取正确性。

### ⑧ Seed-TTS WER=100% → 1.422%（08-09 ~ 08-11）

- **三污染源**（同时存在，逐个修）：
  1. `gf_enc` 双重计算；
  2. FA Q-split 源码默认 16（不是 0）——旧 9.334% = Q-split16 的 confound；
  3. `ecee7de` 的 memcpy rope 污染。
- **结果**：FULL 2020 PASS，WER **1.422%**（pristine 1.5%，≤1.56）+ SIM **0.969**（≥0.689）。
- **Config D uniform-compat 验证**：MAX_UBATCH=16 + Q-split0 干净。

### ⑨ Config D + RTF 解锁（08-11 ~ 08-13）

- **Config D**（纯环境变量注入，不改 `evaluation/` + 4 保护工具）：
  `OMNI_T2W_DEVICE=cann-flow-only` / `OMNI_VOC_DEVICE=gpu:0` / `OMNI_T2W_PIPELINE_OVERLAP=1` /
  `OMNI_CANN_FA_MAX_UBATCH=16` / `GGML_CANN_WEIGHT_NZ=off` / `GGML_CANN_ACL_GRAPH=off`。
- **RTF 解锁**：**LISTEN-wedge 生命周期修复**——空 duplex LISTEN chunk_end 未完成 drain 记账 → active_gen 楔死 → NOT_REUSABLE 拒绝 → RTF 测不出。修复后 **RTF AVAILABLE = 1.0904**（parity baseline 1.087），n_speak 0→33，0 拒绝。
- **诚实话术**：RTF 可用但**无已证实加速**（1.09–1.17 落在基线 parity 区间）；Config D 的 ~18% wall 是本地 A/B，不是 official RTF −18%。
- **Track B**（RTS RTF）：t2w 缺 duration_ms/src_cnt + per-chunk drain 楔死 SPEAK turn → 结论性受阻关闭。
- **Track D**（稳定性 soak）：2× RTS 0 崩溃 + 无线程泄漏。
- **Track F**（可复现性）：候选重冻结 + 8 项 SHA256 权威表。

### ⑩ 最终交付（08-13 ~ 08-14）

- **最终冻结**：runtime `fd3dd36`（tag `competition-final-20260814`）+ 提交文档 `16ec3500d`（tag `competition-submission-20260814`）。
- **四项精度全 PASS**：Daily-Omni 79.43% / Video-MME 69.8% / TTS-WER 1.422% / TTS-SIM 0.969。
- **提交收口 + push**（私有仓库 Phoenix3334，SSH）。
- **分支生命周期收敛**：3 支活跃分支（competition/dspark/specdecode-migration）。
- **DSpark kickoff**（`feat/dspark-llama-port`）：上游 DFlash→DSpark 两阶段 backport 计划（decode Amdahl 13% → 增益封顶 6.5%）。

---

## 3. 踩坑总表（pitfalls catalog）

| # | 踩坑 | 根因 | 代价 / 修复 | 教训 |
|---|---|---|---|---|
| 1 | TTS "crash fix" 有害 | `tts_gpu_layers=99→0` 在 CPU 产生 zero-norm embedding | RoPE 修复后回滚 | 先考古，别信早期 hack |
| 2 | CANN 线程亲和性 | context/stream 不能在跨线程使用 | cann-flow-only 推迟初始化 | 设备后端有线程模型 |
| 3 | libgomp 线程泄漏 | OpenMP fork-join × httplib 每请求一线程 | `-t 4` | 框架交互型泄漏，非数据 bug |
| 4 | WS 生命周期拒绝 | `CTX_STATE_REUSABLE` 未重置 | 统一 finalizer | 状态机复位要完整 |
| 5 | SSE `?` 腐败 / bad_alloc | worker-once 生命周期，sink.done 未调用 | 流式路径 worker 复用 | 流式响应有生命周期 |
| 6 | 首帧 prefill 吞内容 | system-prompt 初始化分支（omni.cpp:12906） | 两次 prefill 协议 | 协议要摸清，不能想当然 |
| 7 | **FA mask 回归 `b6b6af0`** | raw -Inf→pseShift、mask=nullptr | 回滚 → 干净 | NaN saga 总根，一次 revert 引入 |
| 8 | **`aclnnMm` NaN（finite 输入）** | CANN runtime execution-context bug | MAX_UBATCH=16（+5.3%） | 只能全局 workaround，无法窄修 |
| 9 | **Seed-TTS 三污染源** | gf_enc 双算 + Q-split 默认16 + memcpy rope | 逐个修 → WER 1.422% | 多个 corruption 会叠加 |
| 10 | **LISTEN-wedge 楔死** | 空 LISTEN chunk_end 未完成 drain 记账 | 生命周期修复 → RTF 可测 | 计时/记账状态要覆盖空 chunk |
| 11 | SPEAK turn 楔死 | per-chunk drain + 5s 超时边界 → context_state=3 | 两次修复均回滚（候选级，未解） | 超时边界语义要严 |
| 12 | whisper 音频上限 24-26s | 模型能力上限 | 无法修（Daily-Omni 官方 29.5s → "?"） | 模型上限要诚实标注 |
| 13 | Q8_0 量化更慢 | CANN 量化路径 `aclnnWeightQuantBatchmatmulV2` 慢 10.3% | 拒绝 Q8_0 | 量化在 CANN 上不是免费 |
| 14 | W8A8 V5 dead-end | 无 int8×int8→fp16 kernel | 拒绝（V3 1.27× 但不稳） | 算子能力要 micro-benchmark |
| 15 | flow ACL graph 净损 | E2E +11% 净损 | 冻结 OFF | capture 不一定赢 |
| 16 | Q4_K_M LISTEN 27-40% | 量化过头 | 拒绝 | 精度/RTF 要一起看 |

---

## 4. vLLM 迁移（track）

> 从 llama.cpp-omni 比赛经验迁移到 vLLM-Omni（官方 Thinker→Talker→Token2Wav 多 Stage pipeline）的完整文档集，在 `docs/vllm-migration/`（10 份）。
> **最重要的纪律**：llama 侧数字只是参考标尺，不是 vLLM 结果；vLLM 未源码核实的一律 `TO_AUDIT`；内部结果 ≠ 官方结果。

| 文档 | 内容 |
|---|---|
| `README.md` | 迁移文档集入口（30 秒版 / 10 分钟阅读序） |
| `LLAMA_TO_VLLM_EXPERIENCE_MIGRATION.md` | 12 条核心经验（每条 10 点）+ 4 决策树 + 请求路径图 |
| `LLAMA_RAW_EVIDENCE_APPENDIX.md` | 所有 llama 数字的精确出处（数值/CI95/样本/来源） |
| `LLAMA_VLLM_COMPONENT_MAPPING.md` | 13 组件逐一映射 + 6 条 rg 源码导航 |
| `VLLM_OPTIMIZATION_EXECUTION_PLAN.md` | 动手路线 V0–V12，每阶段 16 字段 |
| `VLLM_RISK_AND_VALIDATION_MATRIX.md` | 16 条证据 + 25 条风险 + 候选决策 |
| `VLLM_TEAM_HANDOFF.md` | 队友第一周计划 + 第一个小时 5 件事 + 交付清单 |
| `EXPERIMENT_TEMPLATES.md` | 4 种实验模板（Run Manifest / Per-request / 决策 / A/B） |

**核心迁移结论（llama 实测，供 vLLM 参考）**：
- decode 只占 E2E ~2.9%，语音合成链（T2W）占 ~93% → **别先优化 decode**。
- 设备放置 CPU→NPU 使首音 −81.4% → 先做 Stage 打点 + 设备放置审计。
- 静态前缀复用使 prefill 2.4× → Prefix Cache A/B 是第三个优先项。
- 三个陷阱：① 别把 memory-slot 错误全归主模型 KV（Talker/Token2Wav 有独立上限 4096）；② 别把"命中缓存"当"端到端收益"；③ 别先优化 decode。

---

## 5. 最终交付与状态

| 块 | 状态 |
|---|---|
| 四项精度指标（三个 Benchmark） | ✅ 4/4 PASS |
| 官方 SPEAK→WAV RTF | ⚖️ AVAILABLE（1.09–1.17，parity baseline 1.087，无已证实加速） |
| 二进制可复现 | ✅ PASS（重建 SHA 逐字节一致） |
| 稳定性 | ✅ PASS（2× RTS soak 0 崩溃、无线程泄漏） |
| Demo | 🟡 服务侧 PASS / 官方前端 NOT_RUN |
| 官方 eval（G1→G8） | 🟡 NOT_RUN（`BLOCKED_BY_OFFICIAL_STARTER_KIT`） |
| 提交完成声明 | 🟡 NOT_CLAIMED（以主办方正式提交为准） |

---

## 6. 证据链索引

- 权威提交文档：`docs/competition-submission/`（RESULTS / OPTIMIZATIONS / OFFICIAL_GATE_STATUS / VERSION_MANIFEST …）
- 证据链（性能/精度/稳定性追踪）：`docs/F6_*.md`
- 分支导读：`docs/branch-map.md`（42 支分支）
- 原始 llama.cpp-omni README：`README-llama-cpp-omni.md`
