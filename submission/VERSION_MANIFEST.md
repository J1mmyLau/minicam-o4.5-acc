# VERSION_MANIFEST — 版本溯源清单（唯一权威）

> 每次 run / 每次复现都以此为准。任何结果必须能回溯到本清单的一行。

## 候选冻结（2026-08-14）

| 项 | 值 |
|---|---|
| CANDIDATE_SOURCE_COMMIT | `fd3dd36870f60829e47cafffacc7027cf8eb21d4`（tag `competition-final-20260814`） |
| 构成 | `a77d6a8` + `trackA_fixes.patch`（4 文件：aclnn_ops.cpp / omni.cpp / token2wav-impl.cpp / server-omni.cpp）+ LISTEN-wedge 生命周期修复 + stage_timing 发射 |
| Branch | `fix/cann-fa-nan-ubatch16` |
| 运行时配置 | Config D（见下） |
| llama-omni-server SHA256 | `4694cb589b61fbc3d9c26508dbfb044ae06f07395ca409659dbb0f066a28815f` |
| libomni.so SHA256 | `3f3e1e636f66e81501eeda9285e1228e14da542211292a67f8bae70fbdf822ec` |
| libggml-cann.so.0 SHA256 | `c083aeea9aa57632d2c89c0f9b8872aff88edfd773dd7c8ecc8cc5a9961429b6` |
| libggml.so.0 SHA256 | `f79467d9ea9ccf26b390cdae4158a5ba803427ab26dd3ff1c6c516deae5f77ec` |
| libllama.so.0 SHA256 | `cf5a0aaf2a68243a4a09a0c230ffb6a0e665262dd1f2fb36e32142a3d7e4e4a4` |
| llama-omni-tts-eval SHA256 | `0208071b329bb0c4e0ccd9680bb8768ec5c233bcad88b1b941b1db0681211591` |
| llama-omni-eval-cli SHA256 | `640aa777d0e79755e8a8cc9bad2d9dbcec8032bedeccf2a9b3cb691db307ecd4` |
| llama-omni-eval-daily-cli SHA256 | `1b06868cae6f0e302ee7c38528f00317223f73dc53825150dfd83130619ec9c1` |
| model SHA256 | `d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de`（未变） |
| REPRODUCIBLE_BINARY | PASS（LISTEN-wedge 修复后 libomni.so 重建 SHA = 3f3e1e63，逐字节一致） |

> 完整 SHA256 权威见 `docs/competition-submission/BINARY_PROVENANCE.md`（本节已列全 64 hex）。

## 环境基线

| 项 | 值 |
|---|---|
| NPU | 1× Ascend 910C（dual-die，2× Ascend910 芯片，单卡合规） |
| CANN | 9.1.0-beta.1（ASCEND_HOME_PATH 见 env_check.sh 输出） |
| Model | `MiniCPM-o-4_5-F16.gguf`（-ngl 999，--device CANN0） |
| T2W 模型 | token2wav-gguf（CANN flow-only，OMNI_VOC_DEVICE=gpu:0） |
| 数据版本 | Daily-Omni qa.json（1196 项）/ seed-tts-eval（2020 项）/ Video-MME 以官方最终版本为准 |

## Config D（运行时环境变量，零评测器改动注入）

```text
OMNI_T2W_DEVICE=cann-flow-only
OMNI_VOC_DEVICE=gpu:0
OMNI_T2W_PIPELINE_OVERLAP=1
OMNI_CANN_FA_MAX_UBATCH=16        # 长多模态 NaN 保护（aclnnMm 有限输入→NaN workaround）
GGML_CANN_WEIGHT_NZ=off
GGML_CANN_ACL_GRAPH=off
```

## 冻结启动参数（run 基线）

```text
stdbuf -oL -eL build/bin/llama-omni-server -m <MODEL> -ngl 999 --device CANN0
        -c 4096 -b 512 -ub 512 --split-mode layer --port <PORT>
env: OMNI_T2W_DEVICE=cann-flow-only OMNI_VOC_DEVICE=gpu:0
     OMNI_T2W_PIPELINE_OVERLAP=1 OMNI_CANN_FA_MAX_UBATCH=16
     GGML_CANN_WEIGHT_NZ=off GGML_CANN_ACL_GRAPH=off
     ASCEND_RT_VISIBLE_DEVICES=0
```

## run_id 约定

```text
run_yyyymmdd_hhmmss_<tag>（tag = baseline|candidate|perf|demo|repro）
每次 run 记录：完整命令 + 完整环境 + 原始输出路径 + binary_sha + model_sha
```

## 修改规则

- **不得**修改冻结候选源码（`fd3dd36`）与冻结二进制。
- 保护资产：`evaluation/` + 4 保护工具（omni-eval-cli.cpp / omni-eval-daily-cli.cpp /
  omni-tts-eval.cpp / omni/CMakeLists.txt）byte-identical to `c9785cc`，0 行改动。
- 只允许新增/修正：benchmark 脚本、Demo 适配、统计脚本、提交目录、复现文档、官方结果文档。
- 源码/二进制任何变化 → 重建 + 重 SHA + 更新本清单 + 重跑对应验证。
