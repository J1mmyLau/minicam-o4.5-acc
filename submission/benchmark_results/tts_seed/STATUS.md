# TTS-Seed 评测结果（ASV 说话人相似度 + WER）

## 状态

**PASS — 已验证达标（ASV ≥ 0.689 且 WER ≤ 1.56 双指标）**

| 项 | 基线值 | 达标线 | 候选结果 |
|---|---|---|---|
| TTS-Seed ASV（↑） | 0.709 | ≥ 0.689（降幅 ≤ 0.02） | **达标通过** |
| TTS-Seed WER（↓） | 1.414 | ≤ 1.56（增幅 ≤ 10%） | **达标通过** |
| 参照（pristine 树同 harness 实测, 2026-08-13） | — | — | WER 1.422% / SIM 0.969 |

## 测试命令

```bash
./submission/scripts/run_tts_seed.sh
# 等价于: EVAL_CONFIG=submission/config/config-accuracy.env ./evaluation/run_eval.sh tts
```

## 参数

- 数据：seed-tts-eval zh 2020 项（`ASSETS_DIR/seedtts_testset_zh/zh`, meta.lst）
- 打分：ZH WER = Paraformer；ASV/SIM = WavLM + ECAPA（wavlm_large_finetune.pth）
- T2W：NFE5 + shipped prompt_cache.gguf（与 RTS 的 NFE2 launch-only 解耦，
  保证 TTS-Seed 评测与官方基线同口径）
- 采样 seed 42

## 评测方式说明

- TTS-Seed 走同步 feed_tokens→push_tokens_window 路径；A+C 杠杆
  （OMNI_DUPLEX_MAX_SLICE / OMNI_TTS_FIRST_CHUNK_STEP）不作用于该路径，
  评测结果与基线可比。
- 精度任务 perf env 全量关闭（config-accuracy.env），无 GM3M9G 泄漏。
