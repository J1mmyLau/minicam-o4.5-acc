# SOP Paragraph — English

> **状态：草稿 DRAFT**——待你确认叙事框架与 CV bullets 后定稿。
> 目标：150–200 words，偏 CS / Systems / AI Infrastructure。

## Draft v1（187 words）

My most formative project traced the full life cycle of a language model —
from training to cross-platform inference. I trained a speculative-decoding
draft network for a multimodal LLM on 8×NVIDIA B300 GPUs, building the data
pipeline myself: an offline hidden-state cache of 4,197 multimodal samples
(98 GiB) so the draft would learn exactly the feature distribution it sees
at inference. Under an A/B evaluation with prompt-identity assertions, block
acceptance length rose from 3.49 to 3.86. I then carried the artifact to a
Huawei Ascend 910C NPU: writing the GGUF conversion and a mixed-precision
quantization verified bit-identical on acceptance, and integrating
speculative decoding into llama.cpp, where I measured where it helps (1.87×
at k=2) and where it does not (net-negative in real-time duplex), deciding
accordingly. Finally, on the same NPU, I cut real-time speech RTF from 1.087
to 0.4829 through profiling-driven kernel work — custom TileLang fused
kernels, launch-tax elimination, and structural levers — while keeping every
accuracy metric within tolerance. Moving between model training, quantization,
and hardware-level optimization taught me to treat systems as one continuous
problem, which is exactly what I hope to pursue in graduate study.

## 备选结尾句（按学校口味替换最后一句）

- 研究向：…which is the perspective on AI systems I hope to deepen through
  graduate research in {program}.
- 工程向：…and I want to build the next generation of inference systems
  where such cross-layer co-design is the norm, not the exception.

## 写作说明

- 全段只用了 EVIDENCE_MAP 里的数字（3.49→3.86 / 1.87× / 1.087→0.4829），
  没有混用 acceptance 与 speedup 口径。
- 「deciding accordingly」对应 RTS 净负判定——这是面试官容易深挖的点，
  与 INTERVIEW_NOTES 的 Q4 答法一致。
- 如需更 "research" 的味道，可在 hidden-state cache 处加半句动机：
  "to eliminate train–inference distribution drift by construction"。
