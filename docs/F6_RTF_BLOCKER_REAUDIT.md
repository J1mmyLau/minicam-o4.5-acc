# F6 — Official RTF Blocker Re-Audit（只读溯源 + 分类）

Date: 2026-08-14 · Candidate: `a77d6a8` (`fix/cann-fa-nan-ubatch16`) + `trackA_fixes.patch` + Config D
Directive: 【BYPASS — REMOVE STALE STARTER-KIT BLOCKER + AUDIT OFFICIAL RTF】

> **⚠️ 已由 `docs/F6_OFFICIAL_RTF_RESOLVED.md` 解决并修正分类**：真实根因不是「发射缺失」（Class A），
> 而是 LISTEN-wedge 生命周期 bug（生产 `tools/omni/omni.cpp` 可修）。修复后官方 RTS 首次产出
> `rtf.core.rtf_aggregate`，n_speak 0→33，0 拒绝。`RTF_BLOCKER_CLASS = A → RESOLVED`。本文件保留为溯源记录。

## 结论速览（TL;DR）

| 判定 | 值 |
|---|---|
| `STARTER_KIT_BLOCKER` | **REMOVE**（stale）— 官方统一评测分支 `tc-mb/llama.cpp-omni` (`bench/huawei`) 已到达并已跑通全量准确率 |
| `OFFICIAL_UNIFIED_EVAL_BRANCH` | **AVAILABLE** |
| `RTF_BLOCKER_CLASS` | **A — RUNTIME_EMISSION_MISSING**（生产 C++ 不吐计时字段，**非**受保护评测器不完整） |
| `OFFICIAL_RTF` | **FIXABLE**，无需修改 `evaluation/` 或 4 个受保护工具 |
| `benchmark_client.py` | **不存在 / 不在 RTS 链上**（旧 Track B 口径作废） |

**一句话结论**：官方 RTF 拿不到数值，**不是**因为官方 harness 是占位符，而是因为我们候选二进制
（生产 C++，`tools/omni/omni.cpp` + `tools/server/server-omni.cpp`，**均不在受保护清单**）没有把
`stage_timing.jsonl` 和 SSE `metrics` 事件吐出来。官方 judge（`evaluation/judge-final/`）是**完整**的，
它已经定义好了 RTF 的精确口径和字段 schema，只等 C++ 端按 schema 供数。

---

## 1. 官方 RTS 真实入口（推翻 benchmark_client.py 占位说法）

`find . -name "benchmark_client.py"` = **空**。旧 Track B 结论里的"官方 RTF 入口
benchmark_client.py 是 WS adapter 占位"指向的是**旧 starter kit**，与当前统一评测分支无关。

真实 RTS 链路（全部读自 `evaluation/`）：

```
./run_all.sh --tasks rts
  └─ run_eval.sh rts
       └─ run_eval.py task_rts()                       # evaluation/run_eval.py:296
            ├─ 配置：RTS_MODEL_LLM / RTS_VIDEO / RTS_MAX_DURATION / OMNI_SERVER_BIN
            ├─ 注入 env：OMNI_T2W_DEVICE / OMNI_T2M_DEVICE / OMNI_VOC_DEVICE / OMNI_SAMPLER_SEED
            └─ run_judge_direct.py --video <RTS_VIDEO> --model <RTS_MODEL_LLM>
                 └─ DuplexSession.start(duplex_mode=True)   # 由 judge 自己拉起 llama-omni-server
                 └─ run_direct_eval()                       # runner/duplex_eval_runner.py
                      ├─ duplex_prefill() / duplex_generate()   # HTTP /v1/stream/decode
                      ├─ DuplexE2ETiming.log_chunk()/log_wav()  # → e2e_timing.jsonl
                      └─ _analyze_e2e()                        # → eval_e2e_report.json（含 rtf 段）
                 └─ average_latency_reports() → batch_avg_report.json
       └─ _collect_rts_metrics() → metrics_rts.json（读 rtf.core.rtf_aggregate）
```

关键点：**judge 自己拉起 server**（`DuplexSession.start`），并把
`os.environ["CPP_STAGE_TIMING"] = session.output_dir / "stage_timing.jsonl"` 作为 server 应产出的文件路径。
`session.output_dir = <llamacpp_root>/tools/omni/output_<cpp_port>`（`omni_client/duplex.py:86`），
对应 C++ 端 `ctx_omni->base_output_dir`。

---

## 2. 官方 RTF 口径与字段依赖图

`eval_duplex_e2e_latency.py::_analyze_rtf()` 是 RTF 的唯一生产者。核心公式：

```
每帧 compute_ms = max(VPM, APM) + LLM_prefill + LLM_decode + TTS + token2wav
每帧 RTF       = compute_ms / audio_ms（= 该帧产出的音频时长）
主指标         = core.rtf_aggregate = Σcompute / Σaudio（掐头去尾：按 is_final 切轮次，剔首帧+flush 尾帧）
```

依赖三路数据，缺一即 `available=False`：

### 2.1 SSE `metrics` 事件 → `encode / llm_prefill / llm_decode`

- 来源：`/v1/stream/decode` 响应流中的 `event=="metrics"` 事件（**由 `server-omni.cpp` 产出**）。
- 消费者：`duplex.py::duplex_generate()` 把 `metrics` 事件字段 `vpm_ms / apm_ms / llm_prefill_ms /
  cost_llm_ms / cost_tts_ms / cost_token2wav_ms / cnt` 解析进 `DuplexGenerateResult`。
- 再经 `duplex_eval_runner.py` 的 `stage_extra` 写入 `e2e_timing.jsonl` 的 chunk 事件。
- `_analyze_rtf(stage, chunks_by_cnt)` 用 `chunks_by_cnt[cnt]` 取 `vpm_ms/apm_ms/llm_prefill_ms/cost_llm_ms`。

### 2.2 `stage_timing.jsonl` 的 `t2w` 事件 → `token2wav` + 音频分母 `duration_ms`

- 来源：`ctx_omni->base_output_dir + "/stage_timing.jsonl"`（**由 `omni.cpp` 的 T2W/vocoder 线程产出**）。
- 必需字段（`_analyze_rtf` 硬依赖）：
  - `duration_ms` — **缺失则整段 RTF `available=False`**（`t2w_events = [e for e in stage["t2w"] if e.get("duration_ms")]`）。
  - `src_cnt` — 帧号，与 chunk 事件的 `cnt` 对齐归帧（`by_cnt[int(cnt)]`）。
  - `token2wav_ms` — token2wav 阶段耗时。
  - `wav` — wav 文件名（integrity check 用）。
  - `is_final` — turn_eos flush 尾包标记（切轮次 + 掐尾帧用）。

### 2.3 `stage_timing.jsonl` 的 `tts` 事件 → `tts` 阶段

- 必需字段：`src_cnt`、`tts_ms`。
- `_analyze_rtf`：`by_cnt[int(cnt)]["tts"] += tts_ms`。

### 2.4 归帧 join key：`src_cnt` == `cnt` == `effective_round_idx`

- chunk 事件的 `cnt` = judge 侧 `DuplexSession._duplex_chunk_counter`（prepare 系统/ref = 0，用户 chunk 从 1 起）。
- `cnt` 随 prefill 请求 `{"cnt": cnt}` 发到 server，落到 T2WOut 队列项的 `round_idx`，
  进而在 T2W/vocoder 线程读为 `effective_round_idx`。
- wav 命名 `wav_{effective_round_idx * 1000 + wav_idx}.wav`，judge 的 `wav_src_cnt()` 反向解析 `src_cnt = wav_id / 1000`。
- **因此 `src_cnt = effective_round_idx` 必须等于 judge 的 `cnt`**，否则归帧失败 → RTF 缺 LLM 段。

---

## 3. 逐字段缺失分类（directive step 4）

每个字段都在生产 C++ 运行时**可用**，只是没写出来：

| 缺失字段 | 类别 | C++ 侧现成取值点 |
|---|---|---|
| `duration_ms` | **A RUNTIME_EMISSION_MISSING** | `audio_duration = chunk_wav.size()/sample_rate`（omni.cpp:12252 / vocoder 线程） |
| `src_cnt` | **A** | `effective_round_idx`（= `received_round_idx` = `t2w_out->round_idx`） |
| `is_final` | **A** | `is_final` / `is_last_window`（omni.cpp:12131 / `task->is_final`） |
| `token2wav_ms` | **A** | serial: `t2w_ms`（omni.cpp:12204）；pipeline: vocoder 线程计时 |
| `tts_ms` | **A** | pipeline: `feed_window_mel` 的 flow 计时；serial: 需拆 flow |
| `vpm_ms / apm_ms` | **A** | 编码线程 `vpm_task()/apm_task()`（omni.cpp:12834-12851，现只打 stderr） |
| `llm_prefill_ms / cost_llm_ms` | **A** | decode 路径的 prefill/decode 计时 |
| `stage_timing.jsonl` 本身 | **A** | 整段 `append_stage_timing_jsonl` 机制缺失 |
| SSE `metrics` 事件 | **A** | server-omni.cpp 无 `event=="metrics"` 发射 |
| `benchmark_client.py` | **F UNKNOWN/MOOT** | 仓库不存在；不在 RTS 链上 |

**无任何字段属于 B（HARNESS_IMPLEMENTATION_MISSING）或 E（DATA_MISSING）。**

---

## 4. 合法性（能否从生产 C++ 补 emit）

受保护清单（`evaluation/README.md` §5）：

```
evaluation/
tools/omni/omni-eval-cli.cpp
tools/omni/omni-eval-daily-cli.cpp
tools/omni/omni-tts-eval.cpp
tools/omni/CMakeLists.txt
```

需要的发射点全部落在：

```
tools/omni/omni.cpp          ← 可改（stage_timing.jsonl 生产点：T2W 线程 + vocoder 线程）
tools/omni/omni.h            ← 可改（辅助字段/锁）
tools/server/server-omni.cpp ← 可改（SSE metrics 事件发射）
```

**三者均不在受保护清单 → 补 emit 合法。** 判断依据与 `git diff --stat c9785cc HEAD` 限定
`evaluation/` + 4 保护工具 = 0 行的既有 Gate 0 结论一致。

---

## 5. 历史溯源（为何 HEAD 缺这些）

- commit `2109473` `feat(bench): add duplex stage profiling and HTTP sampling config`
  （organizer `tc-mb`，Jul 29）**曾**添加 `append_stage_timing_jsonl` + SSE `metrics` 事件
  （`tools/omni/omni.cpp` 131 行 / `omni.h` 18 行 / `server-omni.cpp` 87 行）。它是 HEAD 的祖先。
- 该代码后来在候选分支的重构中被移除；当前 HEAD 的 `omni.cpp` 里 `vpm_ms/apm_ms` 仍在算
  （omni.cpp:12834）但只 `print_with_timestamp` 到 stderr，未写 JSONL / SSE。
- **且 2109473 的原始 schema 本身就不完整**：t2w 事件只有 `wav/token2wav_ms/t2w_queue_wait_ms/
  speak_t2w_acc_ms`，**缺 `duration_ms`/`src_cnt`/`is_final`**；tts 事件用 `chunk_idx` 而非 `src_cnt`。
  这正是旧记忆"t2w 缺 duration_ms/src_cnt"的直接来源——即使按 2109473 恢复，也仍不满足 judge 口径。

---

## 6. 修复范围（State A → RTF CLOSED 的实现清单）

1. `omni.cpp`：恢复 `append_stage_timing_jsonl(ctx, line)` 写
   `base_output_dir/stage_timing.jsonl`（`fopen(...,"a")`）。
2. `omni.cpp` T2W 线程（serial 路径，omni.cpp:12299 附近）与 **vocoder 线程**（pipeline 路径，
   `t2w_vocoder_thread_func`，Config D 走此路径）各 emit 一条：
   `{"event":"t2w","wav":"wav_<id>.wav","src_cnt":<effective_round_idx>,
     "duration_ms":<audio_duration*1000>,"token2wav_ms":<t2w_ms>,"is_final":<bool>}`。
3. `omni.cpp` Flow 阶段 emit `{"event":"tts","src_cnt":<round_idx>,"tts_ms":<flow_ms>}`。
4. `server-omni.cpp`：在 `/v1/stream/decode` 流末尾 emit
   `{"event":"metrics","vpm_ms":...,"apm_ms":...,"llm_prefill_ms":...,"cost_llm_ms":...,
     "cost_tts_ms":...,"cost_token2wav_ms":...,"cnt":...}`。
5. 验证 `src_cnt == judge cnt` 的对齐（`effective_round_idx` ↔ `_duplex_chunk_counter`）。

---

## 7. 与 SPEAK drain 楔死的关系（directive step 8）

SPEAK turn 楔死（`context_state=3` 导致 24 次拒绝、per-chunk drain TIMEOUT）是**独立已知限制**，
与 RTF 缺字段**不同根**。本审计**不**重试 TOCTOU/headroom 修复；drain 问题继续作为
`KNOWN_RUNTIME_LIMITATIONS` 单列（见 Track B/D 证据），不影响 RTF 字段补全的可行性判断。
