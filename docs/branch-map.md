# Branch Map — llama.cpp-omni 昇腾赛道仓库分支导读

> 更新: 2026-08-14 · 共 **42 支本地分支**。
> **最终仓库生命周期 = 3 支活跃分支**（下表）。其余 ~39 支均为历史（已合入 final / 证据链收口 / 未采用 / 废弃），**勿再开发**。

## 最终生命周期（3 支，活跃）

| 分支 | 用途 | 状态 | 入口 |
|---|---|---|---|
| `competition/final-ascend-track-a` | 赛道一最终提交（源码冻结 `fd3dd36` + 提交文档） | 🔒 FREEZE | `README.md` → `README-COMPETITION.md` |
| `feat/dspark-llama-port` | DSpark 投机解码 backport（赛道二） | 队友 draft 到位后继续 | `README.md` → `README-DSPARK.md` |
| `docs/specdecode-migration` | llama / vLLM / DSpark 迁移研究 | 文档研究 | `README.md`（导读） |

## 关键 commit 身份（导航锚点）

| commit | 含义 | 所在分支 |
|---|---|---|
| `fd3dd36` | **冻结 runtime**（tag `competition-final-20260814`，跑出最终数据） | `fix/cann-fa-nan-ubatch16` |
| `c9785cc` | **pristine 基线**（组织方 bench/huawei，无 NaN） | `fix/fa-mask-semantics`、`perf/decode-profile`、`perf/kv-fast-write` |
| `051e993` | 旧 FROZEN BASELINE（F16 + Flow∥Vocoder pipeline） | `perf/vocoder-cann` |
| `b6b6af0` | FA mask 回归（raw -Inf→pseShift 引入 NaN，已回滚） | `integration/bench-huawei-port` |

## 主分支

| 分支 | 用途 | 说明 |
|---|---|---|
| `main` | 项目介绍（6 阶段推进全记录） | 本 README 所在，**非交付分支** |
| `master` | 原始上游 master | — |

## 正确性修复 `fix/*`（已吸收进 final `fd3dd36`）

| 分支 | 修复内容 | HEAD | 状态 |
|---|---|---|---|
| `fix/cann-fa-nan-ubatch16` | ★ **= 冻结 runtime `fd3dd36`** | `fd3dd36` | FINAL |
| `fix/cann-fa-safe-prefill` | CANN FA 安全 prefill | `ae537a7` | 已吸收 |
| `fix/fa-mask-semantics` | FA mask 语义（= pristine `c9785cc`） | `c9785cc` | 对照基线 |
| `fix/f003-cann-rope-repeat-interleave` | CANN RoPE repeat_interleave（GPU TTS 启用） | `95d3c5c` | 已合入 |
| `fix/full-duplex-request-max-tokens` | full_duplex 未传 request_max_tokens → max_tgt_len=0 | `baee842` | 已合入 |
| `fix/tts-thread-lifecycle` | TTS 线程生命周期（per-gen active） | `e23b8d9` | 已合入 |
| `fix/ws-session-lifecycle` | WS 生命周期（CTX_STATE_REUSABLE + CV） | `cf8dacf` | 已合入 |
| `fix/ws-multimodal-nan` | WS 多模态 NaN 调查 | `8fae469` | 调查（未直接合入） |

## 性能实验 `perf/*`（证据链已收口 → `docs/F6_*`）

| 分支 | 内容 | HEAD | 状态 |
|---|---|---|---|
| `perf/f6-decode-to-speak` | CANN T2W 设备放置（W0 −81.4%） | `8813907` | 证据收口 |
| `perf/vocoder-cann` | Vocoder CANN（= 旧 FROZEN BASELINE `051e993`） | `051e993` | 证据收口 |
| `perf/vocoder-cann-pipeline` | Flow∥Vocoder pipeline（1.60×） | `d661573` | 证据收口 |
| `perf/kv-cache-production-gates` | KV Cache 静态前缀（prefill 2.4×） | `70d342e` | 证据收口 |
| `perf/decode-profile` | decode 分解 profiling（= pristine） | `c9785cc` | 证据收口 |
| `perf/kv-fast-write` | KV fast write（= pristine） | `c9785cc` | 证据收口 |
| `perf/flow-chunk-rtf` | Flow chunk RTF 离线链路 | `cdb4f28` | 证据收口 |
| `perf/operator-decode-speak` | 算子级 decode→speak 分解 | `1bef27a` | 证据收口 |
| `perf/ngl8-e2e-stage-profiling` | NGL8 多卡 stage profiling | `ec7408e` | 证据收口 |
| `perf/exp001-v1-sync-memcpy` | sync memcpy 实验 | `1145688` | 证据收口 |
| `perf/exp005-instrumentation` | 打点 instrumentation | `da2a332` | 证据收口 |
| `perf/exp005-v3b-persistent-worker` | persistent worker 实验 | `801e810` | 证据收口 |

## 实验 `exp/*`（SUPERSEDED）

| 分支 | 内容 | HEAD | 状态 |
|---|---|---|---|
| `exp/token2wav-cann-runtime` | T2W CANN runtime 放置 | `59c5c16` | 已废弃 |
| `exp/f003-neox-layout` | NeoX 权重布局 | `13084d2` | 已废弃 |
| `exp/f004-precision-ablation` | FP16→FP32→Q8 精度衰减链 | `899f982` | 已废弃 |

## 优化候选 `opt/*`（未采用）

| 分支 | 内容 | HEAD | 状态 |
|---|---|---|---|
| `opt/r4.2-t2w-trt` | T2W TensorRT | `7a86d08` | 未采用 |
| `opt/r4.2-t2w-trt-test` | T2W TRT 测试 | `8b7b9c4` | 未采用 |
| `opt/r4.3-vit-trt` | ViT TensorRT | `35bdfc8` | 未采用 |

## 功能 `feat/*`（历史，与 final 无关）

| 分支 | 内容 | HEAD | 状态 |
|---|---|---|---|
| `feat/ascend-cann` | Ascend CANN backend | `b43cabe` | 历史 |
| `feat/omni-duplex-r2` | Omni 全双工 R2 | `dd3001a` | 历史 |
| `feat/speed-test` | 测速工具 | `14d0104` | 历史 |
| `feat/web-server` | Web 服务器（HTTP API） | `a9a6dcb` | 历史 |
| `feat/web-demo` | Web Demo（Gateway + Worker） | `ad3e00c` | 历史 |
| `app` | 早期 app | `0f0c76c` | 历史 |

## 其它

| 分支 | 内容 | HEAD | 状态 |
|---|---|---|---|
| `integration/bench-huawei-port` | 组织方 bench/huawei 移植（= FA 回归 `b6b6af0`） | `b6b6af0` | 已回滚 |
| `release/final-integration` | 最终集成 | `9f260bb` | 历史 |
| `eval/official-baseline` | 官方 Demo 基线 | `7b96e45` | 历史 |
| `backup-pre-filter-20260808` | pre-filter 备份 | `bd67bb9` | 备份 |

## 清理建议

- **保留**：3 支活跃分支 + `main`（介绍）+ `master`（上游）。
- **可删**（已收口/废弃，证据已落 `docs/F6_*`）：全部 `perf/*`、`exp/*`、`opt/*`、
  `feat/*`（除 `feat/dspark-llama-port`）、`app`、`backup-*`、`release/*`、`eval/*`。
- **勿动**：`fix/cann-fa-nan-ubatch16`（= `fd3dd36` 冻结 runtime 的落点）、`fix/fa-mask-semantics`（pristine 对照）。

## 提交仓库（remote 拓扑）

```bash
# 私有工作仓库（读写，push 一律走 SSH）
private/origin: ssh.github.com:Phoenix3334/minicpmo45-ascend-private.git
                认证: ~/.ssh/minicpmo45_ascend_private (deploy key, port 443)

# 官方上游（只读，fetch）
organizer: https://github.com/tc-mb/llama.cpp-omni.git
upstream:  https://github.com/ggml-org/llama.cpp.git   # DFlash/DSpark 上游

# ⚠️ HTTPS 无 credential helper，`git ls-remote <https>` 会挂起；只能用 SSH deploy key。
```
