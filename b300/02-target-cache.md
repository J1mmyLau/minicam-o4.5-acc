# B300 · target cache — MiniCPM rollout / hidden-state cache

**问题**：训练不能在线跑 target（太贵），也不能用与推理不一致的分布。
解法：离线一次性生成 **target hidden-state cache**，训练直接读 cache。

**证据**（B300 机）：
- 生成日志：`logs/prepare_cache_minicpmo_dtriad3_media_fp16.log` + `logs/d6_full_cache.log:482-498`
- 32 行端到端 gate：`logs/d4a_cache32.log`（先小样验证管线，再全量）
- manifest：`cache/minicpmo_dtriad3_media_fp16/manifest.json`
- markers：`state/d4a.complete`、`state/d6.complete`

## 生成过程（d6_full_cache.log 直录）

- **单 GPU（GPU 0）生成**，`peak_cuda=17.54 GiB` 稳定不涨
- 逐 10 条打点：success/overlong/failed/tokens/bytes/eta 全程可观测
- 最终一条：`processed=4197/4197 success=4197 overlong=0 failed=0
  tokens=2145260 bytes=98.21GiB elapsed=113.8min`

```text
=== cache generation summary ===
  TOTAL_JSONL      4197      CACHE_SUCCESS    4197
  CACHE_OVERLONG   0         CACHE_FAILED     0
  SUCCESS_RATE     100.00%   TOTAL_TOKENS     2145260
  CACHE_SIZE_GIB   98.21     WALL_TIME        113.8 min
  per-source: daily_omni 1197/1197, seed_tts_en 1088/1088,
              seed_tts_zh 412/412, video_mme 1500/1500  (all 100.00%)
```

## manifest（版本 2，逐字段）

| 字段 | 值 |
|---|---|
| num_samples / num_shards | **4197 / 10** |
| target_layer_ids | **[1, 9, 17, 25, 33]**（manifest:14-15, 64-73） |
| hidden dtype / size | bfloat16 / **4096** |
| token / mask dtype | int32 / uint8 |
| rollout dtype / tokens | **float16 / 64**（greedy 64-token rollout，stop token 关闭） |
| max_length | 2048 |
| chat_template | `minicpmo_multimodal_rollout` |
| modality | **image+audio** |
| transformers | 4.51.0 |
| **total_cache_bytes** | **105,456,927,733 B（100,571.56 MiB ≈ 98.21 GiB）** |
| source JSONL sha256 | `25a50fa6…97192c`（manifest:58-63 绑定数据指纹） |

## 训练 loader 读回验证（Gate D4 readback PASS）

真实 `CacheDataset + CacheCollator` 读回统计：

| 项 | 值 |
|---|---|
| len(dataset) | 4197 |
| seq_len min/med/**max** | 114 / 705 / **908**（mean 511.1，p10/p90 = 128/741） |
| loss tokens | 64/64（每样本恰好 64 个监督 token） |
| per-sample bytes | min/mean/max = 5.6 MB / **25.1 MB** / 44.6 MB |
| hidden dtypes | 全部 `torch.bfloat16`（无混杂） |

collated batch（batch=4 实例）：

```text
input_ids                  (4, 697)          torch.int32
loss_mask                  (4, 697)          torch.uint8
attention_mask             (4, 697)          torch.int64
target_hidden_states       (4, 697, 20480)   torch.bfloat16   ← 5 层 × 4096 拼接
target_last_hidden_states  (4, 697, 4096)    torch.bfloat16   ← 终态 hidden（L1 目标）
```

> `target_hidden_states` 的 20480 维 = target_layer_ids 5 层 × hidden 4096 拼接，
> 与 910C 侧 dflash 条件特征 [20480] **同构**——两线的条件空间一致。

**决策**：cache 是唯一训练数据源（训练时不在线跑 target）；
「数据 sha256 → manifest → 读回统计」三重绑定使数据管线可复核、可复现。
