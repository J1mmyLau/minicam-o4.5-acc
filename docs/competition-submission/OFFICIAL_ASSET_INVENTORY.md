# Official Asset Inventory — Sub-track A (llama.cpp-omni)

> 官方评测规范已发布 (2026-08-05)。本文档逐项盘点执行 Gate 所需的官方资产获取状态。
> `AVAILABLE_LOCAL` = 已在本地固定版本 | `AVAILABLE_REMOTE` = URL 可访问 | `NOT_LINKED_IN_SPEC` = 官方规范未给出具体获取方式

---

## 1. Spec & Rules

| 资产 | 状态 | 备注 |
|------|------|------|
| 官方评测规范文档 | `AVAILABLE_REMOTE` | https://www.feishu.cn/docx/U41vdXMmQo7tv3xW2p9c9uEanKe |
| 精度基线/阈值 | `AVAILABLE_LOCAL` | 已记录: OFFICIAL_EVALUATION_SPEC.md |
| 性能基线 (1.087) | `AVAILABLE_LOCAL` | 已记录 |
| SPEAK 阶段定义 | `AVAILABLE_LOCAL` | 已记录 |
| 评测流程 | `AVAILABLE_LOCAL` | 已记录 |

---

## 2. Demo

| 资产 | 状态 | 备注 |
|------|------|------|
| MiniCPM-o-Demo 仓库 | `AVAILABLE_LOCAL` | ba7fa9c, 422 files, HTTPS shallow clone |
| Demo 官方固定 commit | `VERSION_UNCONFIRMED` | 官方规范未指定 commit；当前使用最新 main HEAD |
| Demo 交互流程素材 | `NOT_LINKED_IN_SPEC` | 文本/图片/音频/视频交互样例 |
| Demo 完整交互流程定义 | `NOT_LINKED_IN_SPEC` | 官方指定的交互步骤和验证标准 |

---

## 3. Benchmark Assets

| 资产 | 状态 | 备注 |
|------|------|------|
| Daily-Omni 测试数据 | `NOT_LINKED_IN_SPEC` | 官方数据版本/子集待确认 |
| Daily-Omni 官方脚本 | `NOT_LINKED_IN_SPEC` | 执行脚本待获取 |
| Daily-Omni 评分器 | `NOT_LINKED_IN_SPEC` | 评分逻辑待确认 |
| VideoMME 测试数据 | `NOT_LINKED_IN_SPEC` | 同上 |
| VideoMME 官方脚本 | `NOT_LINKED_IN_SPEC` | 同上 |
| VideoMME 评分器 | `NOT_LINKED_IN_SPEC` | 同上 |
| TTS-Seed 测试文本 | `NOT_LINKED_IN_SPEC` | 同上 |
| TTS-Seed 参考音频 | `NOT_LINKED_IN_SPEC` | 同上 |
| TTS-Seed ASV 脚本 | `NOT_LINKED_IN_SPEC` | 同上 |
| TTS-Seed WER 脚本 | `NOT_LINKED_IN_SPEC` | 同上 |

---

## 4. Model

| 资产 | 状态 | 备注 |
|------|------|------|
| MiniCPM-o-4_5-F16.gguf | `NOT_ON_THIS_MACHINE` | ~16GB; 权重不在当前服务器 |
| 模型 SHA256 | `VERSION_UNCONFIRMED` | 待官方确认文件完整性校验值 |

---

## 5. RTF Harness

| 资产 | 状态 | 备注 |
|------|------|------|
| SPEAK 状态识别方法 | `NOT_LINKED_IN_SPEC` | 运行时 LISTEN/SPEAK_GENERATION/SPEAK_TAIL 分类 |
| RTF 计时边界定义 | `AVAILABLE_LOCAL` | SPEAK→WAV 完整链路 (规范已明确) |
| RTF 聚合方式 | `NOT_LINKED_IN_SPEC` | mean/p50/p95待确认 |
| 多轮 warmup 次数 | `NOT_LINKED_IN_SPEC` | 规范说"多轮预热"，具体次数待确认 |
| 正式测试重复次数 | `NOT_LINKED_IN_SPEC` | 待确认 |

---

## 6. Submission Template

| 资产 | 状态 | 备注 |
|------|------|------|
| 提交目录结构 | `NOT_LINKED_IN_SPEC` | 待官方给出模板 |
| 文件命名规范 | `NOT_LINKED_IN_SPEC` | 待确认 |
| 视频格式要求 | `NOT_LINKED_IN_SPEC` | 待确认 |

---

## 7. Summary

```
ASSETS_FULLY_AVAILABLE              = 1 (Demo repo)
ASSETS_SPEC_AVAILABLE               = 8 (规则/基线/阈值/流程)
ASSETS_NOT_ON_THIS_MACHINE          = 1 (模型权重)
ASSETS_NOT_LINKED_IN_SPEC           = 17 (Benchmark数据/脚本/评分器/RTF harness/模板)
ASSETS_VERSION_UNCONFIRMED          = 2 (Demo commit, 模型SHA)

GATE_EXECUTION_READY                = PARTIAL
  - G1 (Framework): 需硬件环境
  - G2-G4 (Accuracy): 需 Benchmark 资产
  - G5 (Demo): Demo 已 clone，需推理环境 + 模型 + 交互素材
  - G6 (RTF): 需 RTF harness + SPEAK 分类方法
  - G7 (Reproduction): 需 G2-G6 先通过
  - G8 (Package): 需提交模板
```

> **结论**: 规范层面已完备。执行 Gate 需要获取 Benchmark 数据、脚本、评分器和 RTF harness。
> 这些资产在官方规范中未给出具体下载链接——可能需要通过官方渠道联系组委会获取。
