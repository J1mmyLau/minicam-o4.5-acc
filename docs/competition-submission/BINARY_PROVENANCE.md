# BINARY_PROVENANCE — 二进制溯源（SHA256 权威表）

> 提交物的**唯一二进制溯源权威**。任何结果必须能回溯到本表一行。
> 候选源码：commit `fd3dd36870f60829e47cafffacc7027cf8eb21d4`（tag `competition-final-20260814`）。

## 1. 冻结二进制 SHA256（8 项 + model）

| 产物 | SHA256（64 hex） |
|---|---|
| `llama-omni-server` | `4694cb589b61fbc3d9c26508dbfb044ae06f07395ca409659dbb0f066a28815f` |
| `libomni.so` | `3f3e1e636f66e81501eeda9285e1228e14da542211292a67f8bae70fbdf822ec` |
| `libggml-cann.so.0` | `c083aeea9aa57632d2c89c0f9b8872aff88edfd773dd7c8ecc8cc5a9961429b6` |
| `libggml.so.0` | `f79467d9ea9ccf26b390cdae4158a5ba803427ab26dd3ff1c6c516deae5f77ec` |
| `libllama.so.0` | `cf5a0aaf2a68243a4a09a0c230ffb6a0e665262dd1f2fb36e32142a3d7e4e4a4` |
| `llama-omni-tts-eval` | `0208071b329bb0c4e0ccd9680bb8768ec5c233bcad88b1b941b1db0681211591` |
| `llama-omni-eval-cli` | `640aa777d0e79755e8a8cc9bad2d9dbcec8032bedeccf2a9b3cb691db307ecd4` |
| `llama-omni-eval-daily-cli` | `1b06868cae6f0e302ee7c38528f00317223f73dc53825150dfd83130619ec9c1` |
| `MiniCPM-o-4_5-F16.gguf` | `d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de` |

## 2. 可复现性

- `REPRODUCIBLE_BINARY = PASS`：从 `fd3dd36` 干净重建，`llama-omni-server` 与 `libomni.so` SHA 逐字节一致。
- 构建命令：`bash submission/scripts/build.sh`（`cmake -B build -DGGML_CANN=ON -DCMAKE_BUILD_TYPE=Release`）。
- 构建路径：`build/bin/`（server + libomni.so + libggml*）。

## 3. 历史身份（**已作废**，仅供考古，不要引用为提交身份）

| 阶段 | source | server | libomni | 状态 |
|---|---|---|---|---|
| 2026-08-05 前序冻结 | `bdd4550` | `db258375…` | `c4b16937…` | 已作废 |
| 2026-08-13 Track A/B 中间态 | `a77d6a8` + patch | `c330dc5a…` | `b600ce52…` | 已作废（LISTEN-wedge 前） |
| **2026-08-14 最终** | **`fd3dd36`** | **`4694cb58…`** | **`3f3e1e63…`** | ✅ **当前权威** |

> ⚠️ `docs/F6_*` 系列历史 debugging 报告可能仍引用旧 SHA（bdd4550 / a77d6a8 / c330dc5a / b600ce52 等）。
> 这些是**历史证据**，不是提交身份；提交身份**只认本表第 1 节 + `VERSION_MANIFEST.md`**。

## 4. 修改规则

- 不得修改冻结候选源码（`fd3dd36`）与冻结二进制。
- 源码/二进制任何变化 → 重建 + 重 SHA + 更新本表 + 重跑对应验证。
