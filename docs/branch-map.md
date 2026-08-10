# Branch Map — MiniCPM-o 4.5 昇腾优化

> 所有分支的完整地图。每个分支一行：用途、状态、HEAD、README 状态。
>
> 生成时间: 2026-08-10

---

## 分支总览 (26 branches, 20 已推送至 private remote)

### 主分支 (main)

| 分支 | 用途 | HEAD | README |
|------|------|------|--------|
| `main` | 提交主分支, 冻结 @ 051e993 | `051e993` | ✅ |
| `master` | 原始上游 master | `origin/master` | ✅ |

### 稳定性修复 (fix/*)

| 分支 | 修复内容 | HEAD | README | 状态 |
|------|---------|------|--------|------|
| `fix/ws-session-lifecycle` | WS 生命周期 (CTX_STATE_REUSABLE, drain, thread leak) | `7a9519a` | ✅ | MERGED |
| `fix/tts-thread-lifecycle` | TTS 线程生命周期 (per-gen active, drain predicate, fault injection) | `e23b8d9` | ✅ | MERGED |
| `fix/full-duplex-request-max-tokens` | full_duplex 未设置 request_max_tokens → max_tgt_len=0 | `baee842` | ✅ | MERGED |
| `fix/f003-cann-rope-repeat-interleave` | CANN RoPE repeat_interleave (GPU TTS 启用) | `95d3c5c` | ✅ | MERGED |
| `fix/ws-multimodal-nan` | WS 多模态 NaN 调查 (已追踪至 mel 预处理) | `8fae469` | ❌ | INVESTIGATION |

### 性能优化 (perf/*)

| 分支 | 优化内容 | HEAD | README | 状态 |
|------|---------|------|--------|------|
| `perf/f6-decode-to-speak` | CANN T2W 设备放置 (W0 −81.4%) | on private | ✅ | MERGED |
| `perf/flow-chunk-rtf` | Flow chunk RTF 离线链路 | `fc687f7` | ✅ | COMPLETE |
| `perf/kv-cache-production-gates` | KV Cache 静态前缀 (prefill 2.4×) | `c0b58c3` | ❌ | COMPLETE |
| `perf/operator-decode-speak` | 算子级 decode→speak 分解 | `1bef27a` | ❌ | COMPLETE |
| `perf/ngl8-e2e-stage-profiling` | NGL8 E2E profiling | `04ce85b` | ❌ | COMPLETE |

### 实验 (exp/*)

| 分支 | 实验内容 | HEAD | README | 状态 |
|------|---------|------|--------|------|
| `exp/token2wav-cann-runtime` | T2W CANN runtime 放置 | `59c5c16` | ✅ | EXPERIMENTAL |
| `exp/f003-neox-layout` | NeoX layout 实验 | `f694e28` | ❌ | EXPERIMENTAL |
| `exp/f004-precision-ablation` | Precision ablation | `faa2554` | ❌ | EXPERIMENTAL |

### 优化候选 (opt/*)

| 分支 | 内容 | HEAD | README | 状态 |
|------|------|------|--------|------|
| `opt/r4.2-t2w-trt` | T2W TRT optimization | `7a86d08` | ✅ | OPTIMIZATION |
| `opt/r4.3-vit-trt` | ViT TRT optimization | `35bdfc8` | ✅ | OPTIMIZATION |

### 功能分支 (feat/*)

| 分支 | 内容 | HEAD | README | 状态 |
|------|------|------|--------|------|
| `feat/omni-duplex-r2` | Omni 全双工 R2 | `dd3001a` | ✅ | FEATURE |
| `feat/ascend-cann` | Ascend CANN backend | `5e23913` | ✅ | FEATURE |
| `feat/web-server` | Web 服务器 (HTTP API) | `a9a6dcb` | ✅ | FEATURE |
| `feat/web-demo` | Web Demo (Gateway + Worker) | `ad3e00c` | ❌ | FEATURE |
| `feat/speed-test` | 速度测试工具 | `14d0104` | ❌ | TOOLING |

### 基准 & 快照

| 分支 | 内容 | HEAD | README | 状态 |
|------|------|------|--------|------|
| `eval/official-baseline` | 官方 Demo 基线 (ba7fa9c clone) | on private | ✅ | BASELINE |
| `release/final-integration` | 最终集成候选 | on private | ✅ | INTEGRATION |
| `backup-pre-filter-20260808` | 2026-08-08 pre-filter 快照 | `bd67bb9` | ❌ | SNAPSHOT |
| `app` | 应用层入口 | `0f0c76c` | ❌ | APP |

---

## 分支依赖链

```
eval/official-baseline (官方 Demo 基线)
  └─ fix/f003-cann-rope-repeat-interleave (CANN RoPE → GPU TTS)
      └─ fix/ws-session-lifecycle (WS lifecycle → persistent server)
          └─ fix/tts-thread-lifecycle (线程泄漏修复)
              └─ fix/full-duplex-request-max-tokens (full_duplex token cap)
                  └─ perf/f6-decode-to-speak (CANN T2W)
                      └─ perf/flow-chunk-rtf (Flow chunk RTF)
                          └─ main (051e993, frozen)
                              └─ fix/ws-multimodal-nan (NaN 调查, NOT merged)
```

---

## 提交仓库

```bash
# 私有工作仓库 (读写)
private: ssh.github.com:Phoenix3334/minicpmo45-ascend-private.git
         认证: ~/.ssh/minicpmo45_ascend_private (deploy key, port 443)

# 官方上游 (只读)
origin:  https://github.com/tc-mb/llama.cpp-omni.git
```

---

> 更新时间: 2026-08-10 | 作者: Claude (Co-Authored-By)
