# 性能报告模板（比赛提交用）

> 提交的性能报告**必须是"问题→分析→优化→证据→官方口径"主线**，不是 commit 堆砌。
> 每条数字必须标注：`metric definition · sample count · hardware · configuration · source · raw path · internal 或 official`。
> 本模板最终落 `submission/performance/PERFORMANCE_REPORT.md`。

---

## 章节

### 1. 系统与环境
- NPU 拓扑（1× Ascend 910C dual-die）、CANN 9.1.0-beta.1、OS、driver。
- 候选：source `fd3dd36` / server `4694cb58…` / libomni `3f3e1e63…` / model `d1e69845…`。
- 完整 `npu-smi`、`ASCEND_HOME_PATH` / `ASCEND_OPP_PATH`。

### 2. 官方基线
- 对应框架官方基线（llama.cpp-omni）精度与性能数字来源；**无官方数字处如实标注 NOT_AVAILABLE**。

### 3. 请求和音频生成链路
- MiniCPM-o 4.5 → Main LLM → Talker → Token2Wav → Flow → Vocoder → streaming audio。
- 状态机/请求生命周期（persistent context、drain、per-generation active）。

### 4. 原始瓶颈
- T2W CPU 设备放置 = 93%（4490ms）；decode→speak 仅 2.9%（142ms）。
- 依据：Phase 2 STEP2/STEP3/STEP6 证据（`docs/f6-s13-closure/`）。

### 5. Profiling 方法
- 端到端拆解：Prefill / Decode-to-Speak / Talker / Queue / Flow / Vocoder / Serialization。
- 说明为何不再盲目优化 Decode-to-Speak（Amdahl：T2W 占 93%）。

### 6. 静态前缀 KV Cache
- prefill 206→85ms p50（2.4×），R13 canonical 30/30 严格配对。
- 属工程优化（非核心评分项），写为优化亮点。

### 7. Persistent Server 生命周期
- generation-scoped per-generation active、drain 语义、断连恢复、常驻上下文第 2 次请求。

### 8. CANN Flow/Vocoder
- W0 p50 4798→894ms（−81.4%），32/32，CI95 [−4220,−3732]；T4 严格复核 19/19。

### 9. TTS KV bounds
- 单请求 TTS KV 溢出到 4096 → guard（eval_tokens_tts + prefill_with_emb_tts）；T13 边界测试 PASS（guard=39）。

### 10. 被拒绝的 B6b 方向
- 机械提前触发 Talker 无稳定收益；决策记录：REJECT（保留分析，证明不盲目优化）。

### 11. chunk RTF 正式结果
- **逐 chunk**：`submission/performance/chunk_rtf_summary.json`（count/mean/p50/p90/p95/p99/max/首/中/尾 chunk）。
- baseline vs candidate 对比；官方口径为准（见 CHUNK_RTF_MEASUREMENT_SPEC.md）。

### 12. 精度结果
- Daily-Omni / TTS-Seed / Video-MME 三项：baseline accuracy、candidate accuracy、绝对降幅 pp、失败与排除、分类别、分桶。
- 未跑官方项 → 如实 `NOT_RUN / BLOCKED_BY_OFFICIAL_STARTER_KIT`。

### 13. Demo 稳定性
- 12 用例结果（DEMO_VALIDATION_PLAN.md）+ 10min 连续运行 + 断连重连 + 异常恢复。
- 视频清单（demo/video_manifest.md）。

### 14. 资源使用
- CPU / NPU HBM / RSS 采样；cpu_fallback=0、cann_error=0。

### 15. 已知限制
- whisper 编码上限 ~24-26s（29.5s 音频 → "?"，模型限制非服务器 bug）。
- SSE+use_tts=True 的 T2W drain 未接入（已知边界）。
- KV A/B 28/30（2 对 A_ERR 客户端异常排除，机制 30/30）。

### 16. 复现步骤
- 从零到结果的一键路径（REPRODUCTION_GUIDE.md）；每条结果可复现。

---

## 数字注记规则（强制）

每个数字表项下方注明：

```text
metric:    （定义）
n:         （样本数）
hardware:  （910C / 1×）
config:    （env、ngl、c -c 等）
source:    （R13 / T4 / T6 / 官方…）
raw path:  （JSON/CSV 路径）
kind:      internal | official
```

## 当前状态
- 章节 1–10：内部证据齐备（可回填）。
- 章节 11–13：管线就绪，待官方口径/资产。
- 章节 14–16：数据齐备。
