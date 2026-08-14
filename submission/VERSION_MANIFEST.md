# VERSION_MANIFEST — 版本溯源清单（唯一权威）

> 每次 run / 每次复现都以此为准。任何结果必须能回溯到本清单的一行。

## 候选冻结（2026-08-05）

| 项 | 值 |
|---|---|
| CANDIDATE_SOURCE_COMMIT | `bdd4550de931407ff5c1536fef50847e6c8332eb` |
| EVIDENCE_DOCS_COMMIT | `adb9bb6a3a5459c80929c3a443d685718b293261`（+`d5cc978…`+`f26323f…`） |
| Branch | `perf/f6-decode-to-speak` |
| llama-omni-server SHA256 | `db258375c3d2185ca2181da2a5c8f99a95d381413fcb7ab92a771850ba3a4a21` |
| libomni.so SHA256 | `c4b169376bced6bc3107cfda2f77abf35a634c1e146eed313a193e99e3739ea1` |
| model SHA256 | `d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de` |
| REPRODUCIBLE_BINARY | PASS（两次干净重建 SHA 逐字节一致） |

## 环境基线

| 项 | 值 |
|---|---|
| NPU | 1× Ascend 910C（dual-die，2× Ascend910 芯片，单卡合规） |
| CANN | 9.1.0-beta.1（ASCEND_HOME_PATH 见 env_check.sh 输出） |
| Model | `MiniCPM-o-4_5-F16.gguf`（-ngl 999，--device CANN0） |
| T2W 模型 | token2wav-gguf（CANN flow-only，OMNI_VOC_DEVICE=gpu） |
| 数据版本 | Daily-Omni qa.json（1197 项）/ seed-tts-eval / Video-MME 以官方最终版本为准 |

## 冻结启动参数（run 基线）

```text
stdbuf -oL -eL build/bin/llama-omni-server -m <MODEL> -ngl 999 --device CANN0
        -c 4096 -b 512 -ub 512 --split-mode layer --port <PORT>
env: OMNI_KV_CACHE_REUSE=1 OMNI_KV_CACHE_PATH=<run_dir>/kv_cache
     OMNI_T2W_DEVICE=cann-flow-only OMNI_VOC_DEVICE=gpu ASCEND_RT_VISIBLE_DEVICES=0
```

## run_id 约定

```text
run_yyyymmdd_hhmmss_<tag>（tag = baseline|candidate|perf|demo|repro）
每次 run 记录：完整命令 + 完整环境 + 原始输出路径 + binary_sha + model_sha
```

## 修改规则

- **不得**修改冻结性能源码（`bdd4550`）与冻结二进制。
- 只允许新增/修正：benchmark 脚本、Demo 适配、统计脚本、提交目录、复现文档、官方结果文档。
- 源码/二进制任何变化 → 重建 + 重 SHA + 更新本清单 + 重跑对应 T6。
