# T7 质量/比赛 Gate — 诚实可行性评估

**日期**: 2026-08-04
**候选**: 最终集成候选（T5 freeze, binary `e77b43c3` + `libomni` `f1d2f86d`, HEAD `dbb58ac`）
**范围**: 官方 Harness 到达后，评估在**冻结候选**上运行质量/比赛 Gate 的可行性。
**结论**: **Daily-Omni 准确率 = BLOCKED_BY_CANDIDATE_LIMITATION**（文本输出路径损坏）；
seed-tts-eval = PENDING_EXTERNAL_ASSETS（Google Drive 不可达）；
**不伪造任何官方结果**。

---

## 1. 背景与资产状态

| 资产 | 状态 | 说明 |
|------|------|------|
| `/workspace/benchmarks/Daily-Omni/` | ✅ 已到达 | qa.json（1197 项）、main_tester.py、example_videos（3 视频） |
| Daily-Omni 完整数据集 Videos.tar | ✅ 可下载 | hf-mirror.com 可用（3.9GB）；**未下载**（见 §4 结论） |
| `/workspace/benchmarks/seed-tts-eval/` | ⚠️ 已到达 | run_wer.py / cal_wer.sh / cal_sim.sh；**测试集在 Google Drive，不可达** |
| `/workspace/llama.cpp-omni-official-eval/competition/` | ⚠️ provisional | METRIC_CONTRACT 全项“待官方确认”；STARTER_KIT_CHECKLIST 45/45 未勾选 |
| whisper-large-v3 | ⚠️ 可下载 | hf-mirror 可用（作 ASR 变通，非官方偏差） |

---

## 2. 输入可行性 — CONFIRMED（修正协议，实测）

**发现（关键）**：此前误判“用户 audio/image 在 index>=1 不处理”是**测试协议错误**，不是候选缺陷。

`tools/omni/omni.cpp:12906`：

```cpp
if (!ctx_omni->system_prompt_initialized) {
    // runs system prompt init REGARDLESS of passed index
    // (ignores user image/audio/text)
}
```

omni_init 后 `system_prompt_initialized=false`。**第一次 stream_prefill 无论传入 index 是多少，都会进入 system-prompt 初始化分支**（初始化 + 启动 LLM/TTS/T2W 线程），并**吞掉本次调用的所有用户内容**。这是协议设计（注释 12903：omni_init 与测试脚本都可能调用 stream_prefill(…,0)），但对 API 调用方是陷阱。

**修正协议（两次 prefill）**：
1. `prefill {audio_path_prefix:"", cnt:0}` → system prompt 初始化（n_past→113，KV cache HIT 可复用）
2. `prefill {cnt:1, img_path_prefix, audio_path_prefix, text}` → 用户内容进入 async 队列（`omni_embeds`）
3. `decode` → LLM 线程处理 vision/audio/text 嵌入后生成

**实测证据**（`/tmp/f6_t7/srv2.log`，frame_0000.jpg + short_3s.wav）：
```
encode_image_with_vision_chunks: image encoded in 202.05 ms by vision (2 chunks, 128 total tokens, grid: 1x1)
stream_prefill: vision_embed has 2 chunks
stream_prefill: aud_fname:/tmp/f6_t7/prep/short_3s.wav
stream_prefill: audio_embeds->n_pos: 30 ,hidden_size: 4096
```

→ **冻结候选能处理用户图像 + 音频 + 文本输入**（需两次 prefill 协议）。

---

## 3. 输出可行性 — BLOCKED（候选限制，实测崩溃）

**Daily-Omni 准确率判定需要文本答案**：`test_utils.py::evaluate_answer` 用
`extract_choice_letter(api_answer)` 从文本中提取选项字母。模型必须以文本形式返回答案。

**冻结候选的 HTTP 文本输出路径不可用**：

### 3.1 非流式 decode 无文本字段（server-omni.cpp:560-576）

`stream:false` 的响应 JSON 只有 metrics（stop_reason / generated_token_count / wav_count /
decode_to_first_audio_ms …），**无 `text` 字段**。

### 3.2 SSE 流式 decode 崩溃服务器（实测 2/2 可复现）

`stream:true`（SSE）是唯一可能返回文本的路径（text_queue → `{"content": frag}`）。实测：

| 测试 | 输入 | 结果 |
|------|------|------|
| srv2 | 图像+音频+问题 | `std::bad_alloc` in httplib `write_response_core` → **服务器进程终止** |
| srv3 | 纯文本问题 | `std::bad_alloc` in httplib `write_response_core` → **服务器进程终止** |

```
terminate called after throwing an instance of 'std::bad_alloc'
  what():  std::bad_alloc
build/bin/llama-omni-server(_ZN7httplib6Server19write_response_coreERNS_6StreamEbRKNS_7RequestERNS_8ResponseEb+0x11fc)
```

**T6 从未测过 `stream:true`**（f6_phase3_t6_integrated_regression.py 全部 `stream:false`），
故该缺陷未被回归覆盖。**SSE 路径是候选代码缺陷**，不是环境问题（系统内存充足 1943GB available）。

**疑似机制（未完整根因）**：SSE handler 在 httplib chunked content provider 回调内创建
worker 线程（`server-omni.cpp:595-604`），且回调在写完 `[DONE]` 后 `return true`
（应 return false 结束），导致 httplib 反复回调 → 反复创建 worker 线程并发运行
`stream_decode` → 上下文损坏 → bad_alloc。此为假设，未进一步验证（候选冻结，不做源码改动）。

### 3.3 音频变通路径（非官方偏差）

模型用 TTS 音频说出答案。whisper-large-v3 可从 hf-mirror 下载用于 ASR。
但：官方 Daily-Omni 协议要求文本答案；ASR 噪声污染准确率；测试集接口未定。
**视为非官方变通，不作为 Gate 依据。**

---

## 4. 各基准 Gate 状态（诚实判定）

| Gate | 判定 | 依据 |
|------|------|------|
| **Daily-Omni 准确率** | **BLOCKED_BY_CANDIDATE_LIMITATION** | 输入路径确认可用（§2），但文本输出路径损坏（§3）→ 无法提取答案字母 |
| **seed-tts-eval** | **PENDING_EXTERNAL_ASSETS** | 测试集在 Google Drive，不可达（外部资产缺失，不伪造） |
| **Video-MME** | **PENDING_EXTERNAL_ASSETS** | 数据集未下载（且与 Daily-Omni 相同的文本输出阻塞） |
| **OFFICIAL_BENCHMARK** | **BLOCKED_BY_CANDIDATE_LIMITATION + 接口未定** | benchmark_client.py 的 HTTP/SSE adapter 期望 text+audio chunks，SSE 崩溃直接破坏之；METRIC_CONTRACT 全项 provisional |
| **COMPETITION_COMPLETE** | **NOT_CLAIMED** | 官方 Harness/质量门禁未完成，禁止宣称 |

> 未下载 Videos.tar（3.9GB）：候选无文本输出，数据集对准确率评测无意义。
> 若未来 SSE 修复或改走音频+ASR 变通，再下载。

---

## 5. 对冻结候选的新边界（诚实披露）

| 编号 | 边界 | 状态 |
|------|------|------|
| F7-1 | SSE 流式 decode 崩溃服务器（std::bad_alloc，httplib write 路径） | 真实候选缺陷，2/2 可复现 |
| F7-2 | 非流式 decode 响应无文本字段 | 设计如此，阻塞文本评测 |
| F7-3 | 首次 prefill 被 system-prompt 初始化吞掉用户内容 | 协议设计（12903 注释），API 陷阱 |
| F7-4 | 用户图像/音频需两次 prefill 协议才生效 | 协议设计，已确认可用 |

F7-1/F7-2 组合 = 冻结候选无法通过 HTTP 返回可读文本答案，直接阻塞所有
基于文本答案的质量 Gate（Daily-Omni 准确率）。

---

## 6. 结论

- **输入侧**：冻结候选经修正协议（两次 prefill）确认可处理视频帧 + 音频 + 文本。
- **输出侧**：冻结候选的文本输出路径损坏（SSE 崩溃 + 非流式无文本）→
  **Daily-Omni 准确率无法在冻结候选上评测**。
- **外部资产**：seed-tts-eval 测试集不可达；比赛接口 provisional。
- **判定**：`OFFICIAL_ACCURACY = BLOCKED_BY_CANDIDATE_LIMITATION`；
  `OFFICIAL_BENCHMARK = BLOCKED_BY_CANDIDATE_LIMITATION`；
  `COMPETITION_COMPLETE = NOT_CLAIMED`。
- **不伪造**：任何官方 Gate 未宣称 PASS。

证据（已归档）：`t7_evidence/srv2_media_crash.log`（媒体输入，崩溃 + 输入处理证据）、
`t7_evidence/srv3_text_crash.log`（纯文本输入，崩溃）。

---

## 附录 T9 — 接口修复（2026-08-04，用户 P0 指令）

**F7-1 / F7-2 已修复**（server-omni.cpp，libomni.so 保持冻结 `f1d2f86d`）：

- **F7-2（非流式无 text）**：stream_decode 后 drain text_queue（去控制标记）→ 响应新增 `text` 字段。
- **F7-1（SSE 崩溃）**：根因确认 = provider 回调内创建 decode worker + 写 `[DONE]` 后
  `return true` 未 `sink.done()` → httplib `while(data_available)` 反复回调 → 第二次并发
  `stream_decode` → text_queue 字符串损坏 → `std::bad_alloc`（addr2line：回调 lambda +
  `_M_construct<char*>`）。修复 = worker 每请求一次 + `sink.done()` 终止循环 +
  resource releaser join。
- **T7 新边界**：use_tts=False 常驻会话第二次 decode 被 `drain_gen < request_gen` 守卫拒绝
  （drain_complete_generation 仅由 T2W drain 前进）。修复 = 非 TTS decode 完成后
  `drain_complete_generation=request_generation` + `context_state=REUSABLE`。

**媒体协议实测（PASS）**：非流式 text=748/1088 字符（两轮常驻复用），SSE 干净 `[DONE]`
不崩溃。**T6 重跑验证中**（frozen discipline）。SSE + use_tts=True 的 T2W drain 未接入
（SSE 路径无 omni_duplex_drain_tts_audio）→ 仍为已知边界。
