# vLLM-Omni 队友交接包（可执行主页）

> 本文件是迁移指南集的**首页**：队友接手 vLLM-Omni 路线后的**第一个小时做什么**、**第一周计划**、**最先跑的实验**、**要避免的 llama 弯路**、**每份文档在哪查**、**每个实验用什么模板**、以及**最终交付清单**。
> **不读完整个文档集也能开始**：按本文 §1 → §2 → §3 顺序走即可。

---

## 1. 第一个小时（必做，5 件事）

```text
□ 1. 读 README.md（30 秒）——知道这套文档是什么、7 个文件分别干什么
□ 2. 读本文件 §4（最优先审计位置）——拿到第一周要核对的 5 个源码位置
□ 3. 确认 run manifest 模板（§6）——从第一个实验开始就要记录
□ 4. 确认状态标签（§7）——只允许 5 种，禁止混用
□ 5. 打开执行计划 V0——今天把环境冻结 + 冒烟做了
```

> 一个小时目标：**你已经知道下一步该去哪查、该用什么模板、该记录什么**。不需要读完所有附录。

---

## 2. 已提取的核心经验（llama 侧，已证据化）

| 经验 | 一句话 | 对应文档 |
|---|---|---|
| 设备放置 > 模型 decode | Flow/Vocoder CPU→NPU 带来 −81.4% W0；decode→speak 仅 2.9% | 主指南 §3.3/§3.2 |
| 静态前缀可复用 | prefill 206→85ms（2.4×） | 主指南 §3.1 |
| 出队 ≠ 完成 | 异步 Stage 完成语义必须精确 | 主指南 §3.4 |
| 状态绑定请求身份 | per-generation 隔离解决跨请求污染 | 主指南 §3.5 |
| 接口/协议先于模型 | 输入协议错误与文本字段缺陷曾误判"模型不支持" | 主指南 §3.6 |
| Talker 有独立 context 上限 | `tts_n_past_accumulated=4096` memory slot | 主指南 §3.7 |
| 诚实口径纪律 | 内部结果 ≠ 官方结果，不伪造 | 风险矩阵 R25 |

---

## 3. 队友第一周执行计划

| 天 | 任务 | 产出 | 模板 |
|---|---|---|---|
| D1 | V0 环境冻结 + V1 三类接口冒烟 | `freeze.txt` + 冒烟脚本 | Run Manifest |
| D2 | V2 单卡 baseline（三类指标） | `baseline.json` | Per-request 记录 |
| D3–D4 | V3 Stage 打点 + V4 设备放置审计（**并行**） | `stage_timeline.json` + `device_placement.md` | Per-request 记录 |
| D5 | V5 Prefix Cache A/B | `prefix_cache_ab.json` | 配对 A/B 清单 |
| D6–D7 | V6 生命周期（连续/取消/断连）+ 复盘 | `lifecycle.json` + 周报 | 决策记录 |

> 本周不写任何算子。只建立：基线 + 占比 + 设备 + 前缀复用四张地图。

---

## 4. vLLM 优先审计位置（第一周核对，全部 TO_AUDIT）

```text
1. vllm_omni/ 多阶段 pipeline：request state 是否 per-request 贯穿 thinker→talker→token2wav
2. KV Cache manager / Prefix Caching：是否覆盖多模态/TTS 固定前缀，Cache Key 组成
3. deploy/*.yaml：Stage 设备布局基线（单卡为比赛口径）
4. /v1/chat/completions：streaming vs non-streaming 是否同路径；TTS 模板开关透传
5. abort/cancel 路径 + Stage 后台任务：response 后是否仍有 active work
```

（路径名来自 vLLM 文档约定，是否与实际仓库一致需核对 → 转 CONFIRMED。）

---

## 5. 最先跑的三个实验（优先级铁律）

1. **端到端 Stage 打点（V3）** — 确认 Thinker/Talker/Token2Wav 各占比，验证"瓶颈不在 decode"假设。
2. **设备放置审计（V4）** — 确认 Flow/Vocoder 到底跑在 CPU 还是 NPU、host-device copy 在哪。
3. **Prefix Cache A/B（V5）** — 确认固定参考音频与模板是否真正复用。

> 三者的共同点：**先测量，后优化**。与 llama 路线完全一致。

---

## 6. 实验模板（Run Manifest / Per-request 记录 / 决策记录 / A/B 清单）

> 完整可复制模板见 `EXPERIMENT_TEMPLATES.md`。这里放最小版。

```text
Run Manifest（每次 run 一栏）
  run_id | date | host | NPU 拓扑 | CANN | driver | image tag
  branch | HEAD | deploy YAML SHA | model revision
  env vars | server command | benchmark command | binary/SHA
```

```text
Per-request 记录（每个实验请求一行）
  run_id | request_id | 请求类型(text/audio/av) | mode(stream/non)
  时间戳 T0..T15 | 输入长度 | 输出长度 | HTTP 状态 | 字段完整性 | WAV 有效
```

```text
决策记录（每个 A/B 或 Gate 一条）
  run_id | 假设 | 实验 | 样本数 | 配对方式 | p50/p95 | CI95
  结论(OPTIMIZE/VERIFY_FIRST/PROFILE_FIRST/DEFER/REJECT_BY_AMDAHL/NOT_APPLICABLE/QUALITY_RISK)
  依据 | 回滚方法 | 日期/by
```

---

## 7. 不应该重复的 llama 弯路

| 弯路 | llama 教训 | vLLM 避免 |
|---|---|---|
| 直接优化 LLM decode | 只占 2.9%，T2W 占 93% | 先 Stage 打点 |
| 机械提前触发 Talker | B6b 负结果（无稳定收益） | 仅当 profiling 证明占比大 |
| 只看 `npu-smi` 利用率 | 无法识别 CPU 回退 | 逐 Stage device 打点 |
| 把预填协议搞错 | 首次 prefill 吞内容 → 误判"不支持" | 先验 processor 输出 + packing |
| 把接口字段当模型能力 | 无 text / SSE 崩溃 → 误判 BLOCKED | V1 冒烟先验接口 |
| 把 TTS 错误归因主模型 KV | memory slot 是 Talker 独立上限 | V7 分 Stage 监控 |
| 多卡结果当单卡成绩 | — | 比赛只用单卡口径 |
| 先优化再冻结 | 无基线无法归因 | V0 冻结先行 |

---

## 8. 尚缺的证据（当前迁移指南无法回答，需 vLLM 实测或官方资产）

```text
1. vLLM 侧 Stage 打点真实占比（V3 前无数据）
2. vLLM Prefix Cache 对多模态/TTS 前缀的实际覆盖（V5 前无数据）
3. vLLM Token2Wav/Flow/Vocoder 实际设备放置（V4 前无数据）
4. vLLM 长 TTS 的 Talker/Token2Wav context 上限（V7 前无数据）
5. 官方 Daily-Omni 准确率 / Seed-TTS 指标（官方 Harness/资产未定 → 不宣称 PASS）
6. vLLM 源码级组件核实（全部 TO_AUDIT 项）
7. llama 侧最终 T6 重跑结果（当前二进制 c075c535/db258375 回归进行中）
```

---

## 9. 最终交接要求（队友冻结比赛候选前必须产出 12 项）

```text
1. Canonical 单卡启动 YAML
2. 一键启动脚本
3. 一键冒烟脚本
4. Seed-TTS benchmark
5. Daily-Omni benchmark
6. Stage 性能时间线
7. Prefix Cache A/B
8. 长稳回归
9. 已知问题
10. 已拒绝优化
11. 回滚方法
12. 最终比赛口径
```

状态必须分开（不允许混用）：

```text
DEPLOYMENT_PASS
INTERNAL_PERFORMANCE_PASS
INTERNAL_QUALITY_PASS
PENDING_EXTERNAL_ASSETS
OFFICIAL_BENCHMARK_PASS
```

> 官方 Gate（OFFICIAL_BENCHMARK_PASS / COMPETITION_COMPLETE）仅在官方 Harness 与结果未定时一律不宣称。

---

## 10. 文档索引（7 个文件）

| 文件 | 内容 | 什么时候打开 |
|---|---|---|
| `README.md` | **入口**：这套文档是什么、先读哪个 | 第一次 |
| `LLAMA_TO_VLLM_EXPERIENCE_MIGRATION.md` | 主指南：12 经验 + 4 决策树 + 打点 schema | 理解方法论 |
| `LLAMA_VLLM_COMPONENT_MAPPING.md` | 13 组件 × 13 字段 + rg 导航命令 | 定位源码 |
| `LLAMA_RAW_EVIDENCE_APPENDIX.md` | llama 全部实测数字 + CI95 + 来源 | 查数字 |
| `VLLM_OPTIMIZATION_EXECUTION_PLAN.md` | V0–V12 × 16 字段 | 动手执行 |
| `VLLM_RISK_AND_VALIDATION_MATRIX.md` | 16 证据 + 25 风险 + 候选决策 | 出故障时 |
| `EXPERIMENT_TEMPLATES.md` | 4 种实验模板（Run Manifest 等） | 每次实验前 |

> **快速阅读顺序**：README → 主指南 §0–§5 → 附录 A/B/C（参考数字）→ 按执行计划 V3→V4→V5 动手。
