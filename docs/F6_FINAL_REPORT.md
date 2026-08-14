# F6 — FINAL REPORT（BYPASS — FINAL OFFICIAL GATE THEN FLOW OPTIMIZATION）

Date: 2026-08-13 · Commit: `a77d6a8` (`fix/cann-fa-nan-ubatch16`)
Directive: 【BYPASS — FINAL OFFICIAL GATE THEN FLOW OPTIMIZATION】 Gates 0-4 + Phases 5-8

> ⚠️ **本报告为历史记录**（Gate 0-4 + Phases 5-8 指令）。下方 §Gate 2 的 libomni.so SHA256
> `1e5b01039cabf04f` 是 **trackA_fixes.patch 应用前**的值。最终候选（`a77d6a8` + patch）
> 的权威 SHA256 见 **`F6_TRACK_F_REPRODUCIBILITY_PACKAGE.md`**：libomni.so = `b600ce5277be4eeb`。

## 结论速览

| Field | Value |
|---|---|
| EVALUATION_DIR_PRISTINE | **PASS** — `evaluation/` + 4 保护工具 byte-identical to c9785cc |
| CONFIG_D_EXTERNAL_INJECTION | **PASS** — `config_d_official.env`（EVAL_CONFIG 钩子），0 evaluator 改动 |
| CURRENT_COMMIT | `a77d6a8` |
| ALL_4_BINARIES | server / tts-eval / eval-cli / eval-daily-cli，SHA256 与 Gate 2 逐字节一致 |
| OFFICIAL_SMOKE | **PASS**（4/4 任务 rc=0，结果与 Gate 3 一致） |
| SEED_TTS_STATUS | WER=100.0% / SIM=0.918（无数值已 RESOLVED；WER=100% 独立精度问题，deferred） |
| RTS_SPEAK_STATUS | SPEAK=3/37，SPEAK→wav 均值 2681.3ms（SPEAK=0 已 RESOLVED；RTF 仍无数值） |
| CONFIG_D_STATUS | **VERIFIED**（未优化，flow opt 已 revert） |
| FLOW_PROFILE | FLOW_TOTAL=145ms serial / 202.5ms Config D；FLOW_DEVICE≈41ms；FLOW_HOST≈104–160ms |
| FLOW_OPT_SELECTED | Flow-scoped ACL graph capture（`GGML_CANN_FLOW_ACL_GRAPH`） |
| FLOW_OPT_E2E_GAIN | **NEGATIVE**（flow −20.4% p50 但 E2E +11% 净损）→ DO NOT SHIP |
| OFFICIAL_POST_OPT | **= Config D 未优化**（flow opt revert，二进制与 Gate 2 一致） |
| NEXT_ACTION | 交付 Config D（VERIFIED）；Seed-TTS WER=100% 单独立项 |

---

## Gate 0 — 保护资产 Pristine

`git diff --stat c9785cc HEAD` 限定 `evaluation/` + 4 保护工具 = **0 行**。改动仅落于
`tools/omni/omni.cpp`（Fix 1/3/4）+ `tools/server/server-omni.cpp`（Fix 2）。

## Gate 1 — Config D 零评测器改动注入

`config_d_official.env`（repo 根，外部）经 `EVAL_CONFIG` 钩子注入 Section 9：
`OMNI_T2W_DEVICE=cann-flow-only`、`OMNI_VOC_DEVICE=gpu:0`、`OMNI_T2W_PIPELINE_OVERLAP=1`、
`OMNI_CANN_FA_MAX_UBATCH=16`。Duplex RTS 日志逐条证明（flow=gpu voc=gpu:0 defer=TRUE overlap=TRUE）。
Fix 4 将 CANN flow/vocoder 限定 duplex-only，simplex Seed-TTS 保持 pristine CPU 路径 → 精度零副作用。

## Gate 2 — 4 目标构建 + SHA256（最终，flow opt revert 后复现）

| binary | SHA256（前 16） |
|---|---|
| libomni.so | 1e5b01039cabf04f |
| llama-omni-server | c330dc5aec2a334c |
| llama-omni-tts-eval | 0208071b329bb0c4 |
| llama-omni-eval-cli | 640aa777d0e79755 |
| llama-omni-eval-daily-cli | 1b06868cae6f0e30 |

→ 与 Gate 2 原始记录逐字节一致，证明 revert 后复现无漂移。

## Gate 3 + Phase 8 — 官方 smoke 分类（final stamp `20260813_173229`，post-flow-opt）

| task | result | classification |
|---|---|---|
| Video-MME | 0/2 = 0.0% | 2-sample smoke；两个答案均有效、0 NaN；相对 frozen 69.8% 无统计意义 |
| Daily-Omni | 2/2 = 100.0% | **PASS**（FA mask fix + MAX_UBATCH=16 仍成立） |
| Seed-TTS | 4 WAV, WER=100.0%, SIM=0.918 | 无数值 RESOLVED；WER=100% = 早期 EOS 截断（独立，deferred） |
| RTS | SPEAK=3/37, SPEAK→wav 均值 2681.3ms / 中位 1307.2ms | SPEAK=0 RESOLVED；RTF 无数值（缺 t2w stage_timing，非回归） |

Gate 3（`20260813_164502`）与 Phase 8（`20260813_173229`）两次 smoke 结果一致，确认
post-revert 二进制与 Gate 3 smoke 二进制功能等价。

## Phase 5 — Flow Profile

FLOW_TOTAL=145ms serial / 202.5ms Config D（contended）；FLOW_DEVICE≈41ms（仅 5.7% 花在
Cube 矩阵乘）；FLOW_HOST≈104–160ms（graph build + 188k kernel launch）；launch 开销 ~73%。

## Phase 6 — First-Cut 筛选

Rank 1=Flow-scoped ACL graph（SELECT）> Rank 2=persistent graph（按需）> Rank 3/4=SKIP
> Rank 5=全局 ACL graph（REJECT，破坏 vision encode）。

## Phase 7 — Flow 候选实测（NEGATIVE）

clean 30-chunk A/B（flow=CANN0, voc=CPU, REPEAT=8）：

| metric | EAGER | capture | Δ |
|---|---|---|---|
| `t2m.compute` p50 | 138.1ms | 109.6ms | −20.7% |
| `token2mel` p50 | 147.5ms | 117.3ms | −20.4% |
| `t2m.compute` p95/p99 | 141/142ms | 362/461ms | +156%/+226% |
| `vocoder` p50（CPU） | 349ms | 389ms | +11.5% |
| **infer E2E（mean）** | **14286ms** | **15863ms** | **+11%** |

**结论：DO NOT SHIP。** capture 只消 kernel launch（~30ms），不消 graph build（~50–70ms，
需 Rank 2 持久化图，高风险）；一次性 capture 造成 p95/p99 尾部爆炸；CPU vocoder 竞争。
→ revert `ggml-cann.cpp`，`USE_ACL_GRAPH` 恢复 OFF，二进制复现 Gate 2。

## 术语与状态（Gate 4）

SAME_FA_SUBSYSTEM=YES；SAME_ROOT_CAUSE=NO；FA_SHAPE_BUG=separate（非 FA-mask 回归）；
FA_MASK_REGRESSION=fixed @ a77d6a8。CONFIG_D_STATUS: **VERIFIED**（未优化）。

## 交付物

- `docs/F6_GATE0-4_CONFIG_D_OFFICIALIZATION.md`
- `docs/F6_PHASE5-6_FLOW_PROFILE_SCREENING.md`
- `docs/F6_PHASE7_FLOW_OPT_RESULT.md`
- `docs/F6_FINAL_REPORT.md`（本文）
- `config_d_official.env`（外部注入配置）
- 最终二进制：build/bin 下 4 目标（SHA256 见 Gate 2）

## NEXT_ACTION

Config D 作为最终候选交付（VERIFIED，未优化）。Seed-TTS WER=100%（早期 EOS 截断）为
独立精度问题，单独立项跟进；官方 RTF 无数值（缺 t2w stage_timing + 官方 benchmark_client
placeholder）保持 NOT_RUN 口径。
