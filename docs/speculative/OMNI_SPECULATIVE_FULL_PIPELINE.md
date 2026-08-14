# Omni 全链路 Speculative 适用性地图

> 目的：**不要把 speculative decoding 当成 Omni 全局优化**。逐 stage 标注 DSpark 是否适用。
> 依据：实测 core stage_rtf（官方 RTF 1.0904）+ 历史 profiler（`f6-cross-stage-npu-profile` / `f6-decode-profile-result`）。

---

## 1. 全链路图（实际 llama.cpp-omni pipeline）

```
Request
  ↓
Media preprocessing
  ├─ Vision Encoder      (SigLIP 系)
  └─ Audio Encoder       (Whisper 系)
  ↓
Main LLM Prefill         (Qwen 4096/36L/32h，一次性并行前向)
  ↓
Main LLM Decode          (每步 1 token，autoregressive)
  ↓
duplex LISTEN / SPEAK 决策
  ↓
Talker / TTS autoregressive decode   (speech token，autoregressive)
  ↓
semantic / speech tokens
  ↓
Token2Wav
  ├─ Encoder
  ├─ Flow Matching
  └─ Vocoder
  ↓
WAV
```

## 2. Speculative 适用性逐 stage

| Stage | DSpark 适用? | 理由 |
|---|---|---|
| Vision Encoder | **NO** | 非 autoregressive，并行前向 |
| Audio Encoder | **NO** | 同上 |
| Main Prefill | **NO direct draft acceleration** | prefill 并行，draft 无「预测下一个」的空间 |
| **Main LLM Decode** | **YES** | autoregressive，draft 预测 γ 步 + target verify |
| **Talker / TTS Decode** | **MAYBE / target-dependent** | 也是 autoregressive，但 latent 是 speech token |
| Token2Wav Encoder | NO | 并行前向 |
| Flow Matching | NO | 迭代 ODE 求解，非 token 级 autoregressive |
| Vocoder | NO | 并行前向 |

## 3. 关键问题：draft 训的是哪个 target？

```
Teammate draft 训的是 A / B / C ?

A. Main LLM（text token，vocab 151748）
B. Talker/TTS（speech token，不同 vocab + latent）
C. 一个 draft 同时加速两者 —— 不可能
```

**结构性结论**：一个 DSpark draft **不可能同时加速主 LLM 和 Talker** —— 两者 vocab、latent 空间、block 结构都不同。主 LLM 的 draft 输出 text token，Talker 输出 speech token。

在队友确认 draft target 之前，`MAIN_LLM_DSPARK_FEASIBLE` 与 `TTS_DSPARK_FEASIBLE` 的取值：

```
MAIN_LLM_DSPARK_FEASIBLE = STRUCTURALLY_YES / AMDAHL_BOUNDED (~6.5% 上限)
TTS_DSPARK_FEASIBLE      = UNKNOWN / LIKELY_NO（除非队友明确说 draft 是 speech-token 空间）
```

## 4. Stage 占比与 Amdahl（实测）

| Stage | core RTF | 占比 |
|---|---|---|
| encode | 0.189 | 17.3% |
| llm_prefill | 0.2236 | 20.5% |
| **llm_decode** | **0.142** | **13.0%** |
| tts (Talker) | 0.2974 | 27.3% |
| token2wav | 0.2384 | 21.9% |

- **主 LLM decode 只占 13.0%**。DSpark 让它 2× 也只能省 ~6.5%，现实 ~3–5%。
- **Talker + Token2Wav 合计 49.2%** 才是大头 —— 但这两段不是「token 级 autoregressive decode」可被 DSpark 加速的形态（Talker 是，但需 speech-token draft；Token2Wav 不是）。

## 5. 结论：DSpark 在 Omni 里的真实位置

DSpark 是**主 LLM decode 段的局部加速**，只对「长文本 SPEAK turn、decode steps 多」的场景有意义。它**不是** Omni 全链路的优化点 —— 真正的端到端瓶颈在 Talker/TTS 与 Token2Wav（Flow+Vocoder），这两段需要的是**调度/并行/算子**优化（对应本项目 Phase 4/5-7 已做的 Flow∥Vocoder、CANN 放置），不是 speculative decoding。

## 6. 与其他优化的关系

| 优化 | 作用段 | 状态 |
|---|---|---|
| KV cache reuse | main prefill | 已投产（R13 / OMNI_KV_CACHE_REUSE=1） |
| Flow ∥ Vocoder pipeline | token2wav | 已投产（Phase 4，`OMNI_T2W_PIPELINE_OVERLAP=1`） |
| CANN flow-only + voc gpu:0 | tts+token2wav | 已投产（Config D） |
| FA NaN workaround | main decode/prefill | 已投产（`OMNI_CANN_FA_MAX_UBATCH=16`） |
| **DSpark speculative** | **main decode** | **规划中，Amdahl 上界 ~6.5%** |
