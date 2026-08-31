# B300 · checkpoint — step_150 内容、校验与导出

**证据**（B300 机）：`step_150/` 原目录 +
`/root/b300_minicpmo_dp8/assets/push_stage11_to_hf.py`（导出清单）+
`logs/d8_verify.log` / `verify_final.log`。

## 原目录（B300，只引用不复制）

```
/ssd2/minicpmo-dspark/home/checkpoints/deepspec/
  dspark_block7_minicpmo_4_5_multimodal_dtriad_stage11_b300_dp8/step_150/
```

目录总计 `du -sb` = 112,866,940,032 B = **105.12 GiB**，其中权重只占 **4.2%**。

## 推理需要的 5 个文件（合计 4.414 GiB）

| sha256 | bytes | file |
|---|---|---|
| `5fba915bc8d938e6cc879bed31b80d369d2c0f699298013e96bba5ec140fa362` | 4,738,897,626 | **model.safetensors**（64 tensors，~2369.45M 参数，bf16） |
| `b8eb408bb54ef8c4b68a9384849f3c46ea986d00f2cc652695734fd0845c7c47` | 6,868 | config.json |
| `b0c56c192d4aa57d3dc358338a4a93413b8b68e7c7a7c5b82a5af35afab1d86a` | 10,135 | configuration_minicpmo.py |
| `1a40a58cb7dfa93f723685f860d1cf3caf3a0ecf52b7904db0c4007aacd1536f` | 42,559 | modeling_navit_siglip.py |
| `aecf30c0108f34b3583ccf39eecacd492565f217409a2f898881a58279efea5` | 2,660 | train_config.py |

架构字段见 `step_150/config.json:168-225`：5 层 draft、block_size=7、
num_target_layers=36（绑定 [1,9,17,25,33]）、markov_rank 256、anchors 512。

## ⚠ 8 份 training_state 的含义（勿误读）

`training_state.rank0.pt … rank7.pt` 每份 13,515,997,523 B，共 **100.70 GiB**：

- **不是 8 个模型**——每份 99.9994% 是该 rank 的 **optimizer state**
- 其余是 `next_micro_step=600`（=150 步 × grad_accum 4）与 4 个 RNG state
- DeepSpec **不存 scheduler**：LR schedule 从 next_micro_step 重算
- **拷推理权重时必须 exclude**：

```bash
rsync -avP --exclude 'training_state.rank*.pt' \
  root@10.79.131.152:/ssd2/minicpmo-dspark/home/checkpoints/deepspec/\
dspark_block7_minicpmo_4_5_multimodal_dtriad_stage11_b300_dp8/step_150/ \
  ./dspark-minicpmo-4_5-stage11-step150/
```

## 导出物（B300 侧）

| 项 | 值 |
|---|---|
| 推理文件本地副本 | `/root/submission/`（不含 optimizer state） |
| tarball | `/root/dspark-minicpmo-4_5-stage11-step150.tar.gz`，**3,782,289,212 B** |
| tarball sha256 | `1db577531f1e5c3b2e2e457cfbdf06dc9cab0748f5cd8f8e78eae062e4972cae` |
| 上传清单 | `assets/push_stage11_to_hf.py`（白名单制，只允许推理文件） |
| 外部推送记录 | `logs/push_stage11.log`、`push_all.log`（结项口径：**外部上传不视为本地模型证据**） |

## 910C 侧的下游

`model.safetensors` → swap 原位换字节 → 方案 C 量化 → 提交资产
`dspark_stage11-draft-q8mixed-C.gguf`（1.85GB）：
见上级 [../dspark-910c-inference.md](../dspark-910c-inference.md)。
