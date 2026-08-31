# CV Bullets — English

> 项目名：**End-to-End Speculative Model Training and Cross-Platform Inference
> Optimization on NVIDIA and Ascend**
> 规则：Action + Technical depth + Result；每条数字见 EVIDENCE_MAP.md。

## 3-bullet version（空间紧张时用）

- Trained a DSpark speculative-decoding draft model for MiniCPM-o 4.5 on
  8×NVIDIA B300 (data-parallel DP8, 150 steps) from a 4,197-sample multimodal
  hidden-state cache (98 GiB, 2.15M tokens, 100% generation success) built to
  match the inference-time feature distribution; block acceptance length
  improved 3.49→3.86 and overall acceptance 43.9%→48.5% under an A/B
  evaluation with prompt-identity assertions.

- Ported the trained draft cross-platform to Huawei Ascend 910C via a custom
  safetensors→GGUF converter and a mixed-precision quantization scheme
  (2.26→1.85 GB) verified bit-identical on acceptance; integrated speculative
  decoding into llama.cpp-omni, measured 1.87× text-domain speedup (k=2,
  draft cost ≈1/28 of target), and empirically ruled it out for the
  real-time duplex path (net-negative), deciding where speculation pays off.

- Cut end-to-end real-time speech RTF from 1.087 to 0.4829 (−55.6%) on a
  single Ascend 910C through a profiling-driven campaign — custom TileLang
  fused kernels (+66% decode throughput), host launch-tax elimination
  (18,214→1,301 launches/step), flow-step and vision-token reduction — while
  holding all four accuracy metrics (VideoMME / Daily-Omni / TTS WER / SIM)
  within tolerance.

## 5-bullet version（详细版）

1. **Training pipeline & data**: Designed a distribution-consistent training
   pipeline for a 5-layer DSpark draft (block size 7, ~2.4B params): offline
   target rollout / hidden-state cache over four real multimodal sources
   (Daily-Omni, Video-MME, Seed-TTS EN/ZH; 4,197 samples, 98.21 GiB,
   2,145,260 tokens, 0 failures), with data SHA-256 bound into the cache
   manifest for reproducibility.

2. **Distributed training & evaluation**: Trained with DP8 data parallelism
   (global batch 32, bf16, torch.compile) for 150 steps; evaluated under a
   prompt-identity-controlled A/B (per-sample prompt-hash multiset equality,
   644 samples, 4 tasks) — avg accept length 3.4923→3.8620, overall
   acceptance 0.4388→0.4854, with gains concentrated at block tail
   (accept@6 0.095→0.190).

3. **Cross-platform deployment**: Built the conversion + quantization chain
   from B300 checkpoint to Ascend 910C inference artifact (custom in-place
   GGUF swap; mixed Q8/BF16/F32 plan targeting 1.85 GB; verified by
   bit-identical acceptance, zero round-trip error, and header-equality
   checks), then integrated and debugged speculative decoding in
   llama.cpp-omni (three independent KV/decode defects fixed).

4. **Speculative-decoding benchmarking & decision**: Measured the real
   economics of speculation — c_draft = 1.11 ms/token (≈1/28 of target) and
   near-free batched verification → 1.87× speedup at k=2 (text domain);
   designed a cross-tree RTS duplex A/B that showed net-negative E2E impact
   (RTF +12%), and made the explicit engineering decision to keep the
   submission draft-free, isolating speculation to where it actually pays.

5. **Performance engineering**: Reduced real-time duplex RTF 1.087→0.4829
   (−55.6%; local same-harness baseline 0.6754→−28.5%) via five-stage
   profiling, custom TileLang-Ascend fused kernels (QK-norm+RoPE +66% decode
   throughput; +55–65% stacked with RMSNorm row fusion), host launch-tax
   elimination (18,214→1,301), flow NFE 5→2 with a prebuilt prompt cache,
   and structural levers (vision tokens 128→64/frame; first-chunk steps
   5→10) — all validated by paired 4-run A/B statistics, with accuracy
   isolated via a dedicated env after diagnosing a perf-config contamination
   that collapsed VideoMME 69.8%→8%.

## 一行技术栈（CV Skills 侧可复用）

NVIDIA B300 (DP8, bf16, torch.compile) · Ascend 910C NPU / CANN ·
llama.cpp / GGUF · quantization (Q8_0 mixed-precision) · TileLang kernel
authoring · ACL graph capture · speculative decoding (DSpark/EAGLE-style) ·
profiling (msprof, per-stage decomposition) · Python / C++ / Bash
