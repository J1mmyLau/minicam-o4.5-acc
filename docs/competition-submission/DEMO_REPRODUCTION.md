# DEMO_REPRODUCTION — Demo 复现（权威）

> 候选 `fd3dd36` 的 Demo 能力复现。**诚实状态**：服务侧能力已验证（PASS），官方前端接入 = NOT_RUN。

## 1. 状态

| 层 | 状态 | 说明 |
|---|---|---|
| 服务侧能力（文本/音频/UTF-8） | ✅ PASS | 30/30 UTF-8（L1 Backend 10/10 + L2 Worker 10/10 + L3 Gateway 10/10） |
| 官方前端（OpenBMB/MiniCPM-o-Demo） | 🔴 NOT_RUN | 尚未实际接入；`bash submission/scripts/start_demo.sh` 待做 |

## 2. 服务侧复现（已验证）

```bash
MODEL_PATH=/path/to/MiniCPM-o-4_5-F16.gguf bash submission/scripts/start_server.sh
bash submission/scripts/health_check.sh
bash submission/scripts/demo_smoke.sh --smoke        # 冒烟 D1-D12
```

已通过的 Demo 能力：
- D1-D3 文本 E2E（Gateway→Worker→Backend）。
- 文本 UTF-8 30/30（中文完整，无 `?` 损坏）。
- 双工音频（LISTEN/SPEAK）在官方 RTS 下 n_speak 0→33，0 拒绝。

## 3. 官方前端接入（待做，NOT_RUN）

官方 Demo = OpenBMB/MiniCPM-o-Demo（GitHub 可拉取）。接入步骤：

```bash
bash submission/scripts/start_demo.sh   # 若已提供前端适配脚本
```

> 服务端 WS 协议已按正确 schema 实现（content 数组 typed parts：video/image/audio），
> 官方前端接入的剩余工作是前端侧配置指向本 server 端点，非服务端改动。

## 4. 已知 Demo 边界

- whisper 音频编码上限 ~24-26s，超长音频可能 `?`×256（见 `KNOWN_LIMITATIONS.md`）。
- 全双工路径（audio→NaN）历史问题已由 `OMNI_CANN_FA_MAX_UBATCH=16` 修复。
