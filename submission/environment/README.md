# 依赖与运行环境

## 硬件

- 1× Ascend 910C（dual-die：2× Ascend910 芯片，单卡合规；`ASCEND_RT_VISIBLE_DEVICES=1`）
- 主机内存 ≥ 256GB（F16 模型 ~20GB + T2W 资产）

## 软件

| 组件 | 版本 |
|---|---|
| OS | openEuler 22.03 SP4 (aarch64) |
| CANN Toolkit | 9.1.0-beta.1（`/usr/local/Ascend/cann/set_env.sh`） |
| 编译器 | clang/gcc（C++17）、cmake ≥ 3.19 |
| Python（评测 harness） | `.venv-eval`（evaluation/requirements.txt） |
| TileLang | `/workspace/tilelang-ascend`（AOT 核生成，PYTHONPATH 注入） |

## 模型资产

| 资产 | 路径 | SHA256 |
|---|---|---|
| 主模型 F16 | `/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf` | `d1e69845…57c3de` |
| TTS 子模型 | `<MODEL_DIR>/tts/MiniCPM-o-4_5-tts-F16.gguf` | （未改） |
| token2wav | `<MODEL_DIR>/token2wav-gguf` | （未改） |
| RTS NFE2 cache | `/workspace/models/token2wav-rts-nfe2/prompt_cache.gguf` | launch-only 资产 |
| TTS 打分 | paraformer-zh / wavlm_large.pt / wavlm_large_finetune.pth / ECAPA | 评测侧资产 |

## 数据集

- Video-MME：`evaluation/appendix/videomme/`（parquet + data/）
- Daily-Omni：`evaluation/appendix/daily-omni/daily_omni.jsonl`
- seed-tts-eval：`evaluation/appendix/seedtts_testset_zh/zh`（2020 项）
- RTS 视频：`evaluation/judge-final/assets/video/omni_duplex1.mp4`

## 环境自检

```bash
bash submission/environment/env_check.sh
```

（输出 NPU/CANN/模型/数据集存在性 + 版本；对应官方 (a) 项「依赖与环境文件」）
