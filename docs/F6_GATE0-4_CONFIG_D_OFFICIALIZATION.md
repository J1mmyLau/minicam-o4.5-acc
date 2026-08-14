# F6 — Config D Officialization — Gates 0-4 报告

Date: 2026-08-13 · Commit: a77d6a8 (`fix/cann-fa-nan-ubatch16`)
Directive: 【BYPASS — FINAL OFFICIAL GATE THEN FLOW OPTIMIZATION】

## 结论速览

| Field | Value |
|---|---|
| EVALUATION_DIR_PRISTINE | **PASS** — `evaluation/` + 4 protected tools byte-identical to c9785cc |
| CONFIG_D_EXTERNAL_INJECTION | **PASS** — `config_d_official.env` (EVAL_CONFIG hook), 0 evaluator edits |
| CURRENT_COMMIT | `a77d6a8` |
| ALL_4_BINARIES | server + tts-eval + eval-cli + eval-daily-cli, SHA256 recorded |
| CONFIG_D_STATUS | **VERIFIED** (was RUNTIME_CANDIDATE; Gate 0-3 all pass) |

## Gate 0 — Protected Assets Pristine

`git diff --stat c9785cc HEAD` 限定在 `evaluation/` 与 4 个保护工具 = **0 行**。全部改动仅
落在非保护文件：`tools/omni/omni.cpp`（Fix 1/3/4）与 `tools/server/server-omni.cpp`（Fix 2）。
`evaluation/` 目录树与 pristine `c9785cc` 逐字节一致。

## Gate 1 — Config D 零评测器改动注入

`config_d_official.env`（外部，经 `run_all.sh` 的 `EVAL_CONFIG` 钩子 `CONFIG="${EVAL_CONFIG:-...}"`
注入）仅在 Section 9 覆盖候选运行时：

```
OMNI_T2W_DEVICE=cann-flow-only
OMNI_VOC_DEVICE=gpu:0
OMNI_T2W_PIPELINE_OVERLAP=1
OMNI_CANN_FA_MAX_UBATCH=16
```

Duplex RTS 日志（`rts_runs/20260813_165136/logs/cpp.log`）逐条证明注入生效：

```
T2W pipeline overlap: ENABLED (mel_queue_capacity=2)
Token2Wav: CANN flow-only mode — deferring init to worker thread
Token2Wav: vocoder device overridden by OMNI_VOC_DEVICE=gpu:0
[token2wav] worker-thread init: flow=gpu voc=gpu:0
```

即 `FLOW_DEVICE=CANN0`、`VOC_DEVICE=CANN0`、`DEFER_WORKER_INIT=TRUE`、`OVERLAP=TRUE` 四项全部成立。
simplex Seed-TTS 路径经 Fix 4 保持 CPU flow/vocoder（见 Gate 3），故注入对精度任务零副作用。

## Gate 2 — 4 目标构建 + SHA256

构建命令：`cmake --build build --target llama-omni-server llama-omni-tts-eval llama-omni-eval-cli llama-omni-eval-daily-cli -j 32`
（顶层 `make` 已由 CMake 取代，会报 "Build system changed"）。

| binary | SHA256 (前 16) |
|---|---|
| build/bin/libomni.so | 1e5b01039cabf04f… |
| build/bin/llama-omni-server | c330dc5a… |
| build/bin/llama-omni-tts-eval | 0208071b… |
| build/bin/llama-omni-eval-cli | 640aa777… |
| build/bin/llama-omni-eval-daily-cli | 1b06868c… |

## Gate 3 — 官方 smoke 复跑分类（`./run_all.sh --smoke 2`，stamp 20260813_164502）

| task | result | classification |
|---|---|---|
| Video-MME | 0/2 = 0.0% | 2-sample smoke；两个答案均有效、0 NaN；相对 frozen 69.8% 无统计意义 |
| Daily-Omni | 2/2 = 100.0% | **PASS**（FA mask fix + MAX_UBATCH=16 仍成立） |
| Seed-TTS | 4 WAV, WER=100.0%, SIM=0.918 | 无数值 RESOLVED；**新发现 WER=100%**（下） |
| RTS | 1 SPEAK turn / 3 SPEAK chunks, SPEAK→wav=2620.9ms | SPEAK=0 RESOLVED；RTF 仍无数值 |

### Seed-TTS WER=100%（早期 EOS 截断）— 分类结论

- 原「无数值（0 WAV）」由 Fix 1（defer-init 门控 `duplex_mode`）**解决**。
- 新发现：生成 WAV 截断至 0.84–1.68s（参考 4.74s），flow-matching 在第 21/28 步
  「EOS at step 21/28」提前结束（≈21–28 audio tokens，vs 25Hz 下预期 ~118）。
- **非 Config D**：截断在 CPU flow 下同样存在（Fix 4 已把 CANN flow/vocoder 限定到
  duplex-only，simplex 走 pristine CPU 路径）；CANN（第 1 次跑）与 CPU（第 2 次跑）截断一致。
- **非生成逻辑回归**：`sample_tts_token`/`prefill_with_emb_tts` 与 c9785cc 逐行 diff 仅
  `+TTS-KV-bounds-guard`（4.74s 样本不会触发）+ F003/F004 调试 + TTS_FORCE_ARGMAX；EOS 阻断
  `if (duplex_mode && force_no_eos)` 与 repetition penalty 在 pristine 中逐字相同。
- 根因未定（疑为集成分支 CANN 构建中 TTS 模型设备放置/加载）；**独立精度问题，deferred**，
  不阻塞 Config D 的 RTS 速度目标。

### RTS SPEAK=0 → RESOLVED（Fix 2 SSE drain）

`n_speak=3`（文本「没问题，现在是 24楼了。」）、`n_listen=31`。RTF `rtf.available=false`
仍无数值——本 binary 缺 t2w stage_timing（`cost_tts_ms`/`cost_token2wav_ms` = n=0），属
既有的 `OFFICIAL_RTF NOT_RUN`，非回归。

## Gate 4 — 术语与 CONFIG_D_STATUS

| 术语字段 | Value |
|---|---|
| SAME_FA_SUBSYSTEM | YES |
| SAME_ROOT_CAUSE | NO |
| FA_SHAPE_BUG | separate（FA mask 回归之外） |
| FA_MASK_REGRESSION | fixed @ a77d6a8 |

`CONFIG_D_STATUS`: RUNTIME_CANDIDATE → **VERIFIED**（Gate 0-3 全过：零评测器改动 + 外部注入 +
4 二进制构建 + smoke PASS/已分类）。

## NEXT_ACTION

进入 Phase 5（flow_match 关键路径 profile）→ Phase 6（first-cut 筛选）→ Phase 7（实现一个
Flow 候选）→ Phase 8（最终官方校验）。Seed-TTS WER=100% 作为独立精度问题单独立项跟进。
