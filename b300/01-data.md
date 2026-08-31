# B300 · data — 三套真实数据集 → 4197 行 JSONL

**问题**：draft 训练数据必须来自真实比赛域（非合成），且四个来源每源非零。

**证据**（B300 机）：
- `/ssd2/minicpmo-dspark/logs/d4_jsonl.log`、`logs/build_dtriad_jsonl.log`
- marker：`state/jsonl.complete`
- 正式 JSONL：`datasets/jsonl/dtriad_train.jsonl`
  （sha256 `25a50fa6ec87649d39c74cb3ac3c0a4337b6c32d4e0ef1fbfd374ce8e0b7192c`，
  由 cache manifest `:58-63` 绑定）

**构建记录**（d6_full_cache.log:44-54 原文）：

```text
[daily_omni] built 1197 rows, skipped/missing 0
[video_mme]  built 1500 rows, skipped/missing 0
[seed_tts]   built 1500 rows
[combined]   4197 rows -> /pool/hdd/minicpmo-dspark/datasets/jsonl/dtriad_train.jsonl
             {'seed_tts_en': 1088, 'video_mme': 1500, 'daily_omni': 1197, 'seed_tts_zh': 412}
```

## 组成（准入条件：每源非零）

| 源 | 样本 | 说明 |
|---|---|---|
| Daily-Omni | **1197** | rev `bf5a6ee4c829`，视频+音频 QA，0 skip |
| Video-MME | **1500** | rev `ead1408f75b6`，94.07 GiB 全量下载后抽取（MAX_PER_DATASET=1500 截断），0 skip |
| Seed-TTS EN | **1088** | rev `8f5e1aa2a35d` |
| Seed-TTS ZH | **412** | 同上 |
| **合计** | **4197** | 真实媒体、无合成；解压确定性、保留原件、幂等（1584 个 mp4） |

**决策**：以这份数据为唯一训练源；JSONL sha256 由下游 cache manifest 绑定，
形成「数据 → cache」的可复核链条（防数据被悄悄换掉）。
