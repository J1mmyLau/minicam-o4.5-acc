# REPRODUCTION — 从零复现指南（权威）

> 面向主办方的从零复现步骤。目标：`git checkout fd3dd36` → 构建 → 逐字节复现冻结二进制 → 跑通评测。

## 0. 前置

- 硬件：1× Ascend 910C（dual-die，单卡合规）。
- 软件：CANN 9.1.0-beta.1（`/usr/local/Ascend/cann/set_env.sh` 存在）。
- 模型：`MiniCPM-o-4_5-F16.gguf`（SHA256 `d1e6984531bab1962d8bc73da4b6dffc5c2d9b0da336603943df04100e57c3de`）。
- T2W 模型：token2wav-gguf。

## 1. 取源码（单 commit，无补丁）

```bash
git clone <repo> && cd llama.cpp-omni-bench-huawei
git checkout fd3dd36870f60829e47cafffacc7027cf8eb21d4   # tag competition-final-20260814
```

> `fd3dd36` 已内含 a77d6a8 + trackA_fixes.patch + LISTEN-wedge 修复 + stage_timing 发射，**无需**再 `git apply`。

## 2. 环境检查

```bash
bash submission/environment/env_check.sh
```

预期输出：`ENV_CHECK=PASS`（CANN 环境 / NPU / 模型 / 端口 / 冻结二进制）。

## 3. 构建（复现 REPRODUCIBLE_BINARY=PASS）

```bash
bash submission/scripts/build.sh
```

预期 SHA（重建逐字节一致）：

```text
llama-omni-server = 4694cb589b61fbc3d9c26508dbfb044ae06f07395ca409659dbb0f066a28815f
libomni.so        = 3f3e1e636f66e81501eeda9285e1228e14da542211292a67f8bae70fbdf822ec
```

> 完整 8 项 + model SHA 见 `BINARY_PROVENANCE.md`。

## 4. 启动（冻结 env = Config D）

```bash
MODEL_PATH=/path/to/MiniCPM-o-4_5-F16.gguf bash submission/scripts/start_server.sh
bash submission/scripts/health_check.sh
```

启动 env 已固化为 Config D（`submission/config/server.env`），6 变量：
`OMNI_T2W_DEVICE=cann-flow-only` / `OMNI_VOC_DEVICE=gpu:0` / `OMNI_T2W_PIPELINE_OVERLAP=1` /
`OMNI_CANN_FA_MAX_UBATCH=16` / `GGML_CANN_WEIGHT_NZ=off` / `GGML_CANN_ACL_GRAPH=off`。

## 5. 评测（准确率 + RTF）

```bash
bash submission/scripts/run_daily_omni.sh     # Daily-Omni → 79.43%
bash submission/scripts/run_video_mme.sh      # Video-MME  → 69.8%
bash submission/scripts/run_tts_seed.sh       # Seed-TTS   → WER 1.422% / SIM 0.969
bash submission/scripts/run_performance.sh    # SPEAK→WAV RTF
```

## 6. 复现校验点

- [ ] server 重建 SHA == `4694cb589b61fbc3d…`，libomni.so == `3f3e1e636f66e815…`。
- [ ] 结果 `run_id` / `binary_sha` / `model_sha` 齐全。
- [ ] 无 `/tmp` 持久化依赖、无私有绝对路径唯一默认值。
- [ ] `evaluation/` + 4 保护工具 byte-identical to `c9785cc`（0 行改动）。
