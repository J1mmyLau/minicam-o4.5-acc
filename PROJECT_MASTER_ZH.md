# 项目总述（申请材料版）— 中文

> 项目名（申请口径）：**End-to-End Speculative Model Training and Cross-Platform
> Inference Optimization on NVIDIA and Ascend**
> 事实来源：`docs/engineering-log` 分支（frozen @ 858ad30）。只用已归档证据。

## 总述（约 1000 字）

这个项目是一条完整的"训练—跨平台部署—性能工程"链路，对象是 MiniCPM-o 4.5
多模态大模型的实时语音对话推理。它由三段构成：在 NVIDIA B300 上训练一个
投机解码（speculative decoding）draft 模型；把它跨平台部署到华为 Ascend 910C
国产 NPU；再用 profiling 驱动的内核与运行时优化，把端到端实时率（RTF）从
官方基线 1.087 压到 0.4829（−55.6%），同时四项精度指标全部保持在容差内。

**模型侧（NVIDIA B300，8 卡）**：我先解决训练数据与推理分布一致的问题——
不是简单收集语料，而是用 target 模型对四个真实多模态数据源
（Daily-Omni 1197 / Video-MME 1500 / Seed-TTS EN 1088 / ZH 412，共 4197 样本）
离线生成 hidden-state cache：98.21 GiB、215 万 token、生成成功率 100%，
并manifest 绑定数据 sha256 形成可复核链条。在此之上以 DP8 数据并行训练
DSpark draft（5 层、block size 7、约 23.7 亿参数）150 步。评估用
prompt-identity 受控的 A/B（逐样本 prompt 哈希多重集断言相等）：块平均接受
长度 3.4923→3.8620，整体接受率 43.9%→48.5%，提升集中在 block 尾部
（@6 位 9.5%→19.0%）。我刻意不把 acceptance 提升说成端到端加速——那是
另一个单独实测的数字。

**部署侧（Ascend 910C）**：把 B300 产出的 checkpoint 跨平台搬到 910C：
自写 safetensors→GGUF 原位转换器（上游转换器会丢 draft 专有字段），设计
混合量化方案（前两层+一处 FFN 下投影走 Q8_0，条件主干与 markov 张量保持
高精度）把 2.26GB 压到 1.85GB，并以三重自证验证位级无损（量化前后
acceptance 逐位一致、safetensors round-trip 误差为零、header 字节全等）。
随后把投机解码接进 llama.cpp-omni：修掉三个独立的 KV/解码缺陷后，文本域
k=2 实测 1.87× 加速（draft 单 token 成本 1.11ms，约为 target 的 1/28）；
但在真实时双工路径上实测净负（RTF +12%、decode 2.56× 慢），据此做出
工程决策——RTS 主线不挂 draft。这个"测出来是负的就不用"的判断，
和加速本身一样是本项目的贡献。

**性能侧（同一张 910C）**：先做归因再动手：把 RTF 分解成五段
（视觉编码/prefill/decode/音频 token 生成/token2wav），逐段 profile，
并用实验否决了一批流行假设（malloc 开销、lm_head 重复计算、单算子换装
均为零或负收益）。真正的收益来自三处：自建 TileLang-Ascend 后端并写出
整段融合核（QK-norm+RoPE 单核使 decode 吞吐 +66%，叠加 norm 行融合
+55~65%；conv1d im2col 消除使 t2w −21% 且 WAV 相关 0.9993）；host 侧
launch 税削减（每步 launch 从 18214 降到 1301）；以及两个结构性杠杆
（vision token 每帧 128→64、首 chunk 步长 5→10）。叠加流匹配步数
5→2，最终 4-run 稳定在 0.4829±0.0161。精度与性能用双环境变量严格隔离
——期间定位并修复过一次 perf 配置泄漏导致 VideoMME 从 69.8% 塌到 8% 的
事故，根因是长上下文 prefill 的 logits 污染。

这个项目体现的能力：**分布式训练与数据管线设计、跨平台模型部署与量化、
profiling 驱动的系统优化、写进硬件后端的 kernel 工程、以及把每个结论都
钉在受控实验上的 evidence-driven 工程习惯**（包括完整记录被否决的路线）。

## 使用说明

- 改 PS：取"三段主线 + 最后一段能力句"。
- CV：见 CV_BULLETS_EN.md。
- 面试：见 INTERVIEW_NOTES_ZH.md。
- 所有数字的出处：见 EVIDENCE_MAP.md，改口径前先查表。
