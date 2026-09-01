<div align="center">

<img src="assets/logo.svg" width="150" alt="项目 logo —— 昇腾 NPU 芯片与实时语音波形">

# TileLang 教学

### 以本项目真实生产 kernel 为教材 —— 从心智模型到生产接线

主项目介绍 → [`main` 分支 README](https://github.com/Phoenix3334/minicpmo45-ascend-private/blob/main/README.md)（[English](https://github.com/Phoenix3334/minicpmo45-ascend-private/blob/main/README.md) · [简体中文](https://github.com/Phoenix3334/minicpmo45-ascend-private/blob/main/README.zh-CN.md)）

[![TileLang fusion](https://img.shields.io/badge/TileLang_fusion-+66%25_decode-orange)](https://github.com/tile-ai/tilelang)
[![QKR](https://img.shields.io/badge/QK--norm%2BRoPE-0.47%E2%86%920.78_tok%2Fs-blue)](tl-tutorial/03-production-kernels.md)
[![conv1d](https://img.shields.io/badge/vocoder_conv1d-t2w_%E2%88%9221%25-blueviolet)](tl-tutorial/04-conv1d.md)
[![platform](https://img.shields.io/badge/platform-Ascend_910C-informational)](https://www.hiascend.com/)

</div>

---

## 这个分支是什么

**👉 教程入口：[`tl-tutorial/README.md`](tl-tutorial/README.md)**

给本项目（MiniCPM-o 4.5 / Ascend 910C 实时语音对话，RTF 0.6754→0.4829）写的
TileLang 教程：**7 讲 + 7 份代码，全部摘自生产 kernel 或官方模板，零虚构示例**。
学完你能读懂、修改、并写出下一个融合 kernel。

| 讲 | 内容 |
|---|---|
| 01 | 心智模型：GM→UB 内存层级三拍子 + 七个核心原语 + Hello World 逐行 |
| 02 | two-pass 模板精读（官方 `rms_norm.py`，行融合的模板来源） |
| 03 | **生产 kernel 精读**：QK-norm+RoPE 三版演进（decode +66% 那个） |
| 04 | vocoder conv1d（消 im2col，t2w −21%，WAV corr 0.9993） |
| 05 | 血泪规则 10 条（全部实测撞过） |
| 06 | 生产接线：AOT `.so` → 桥接 → env 开关 → 位级 parity |
| 07 | 练习路线（910C 本机可直接跑） |

## 分支上还有什么

本分支基于冻结的 `docs/engineering-log`@`858ad30` 切出，所以**同分支还带着完整的
工程日志**（教程只引用不重复）：

| 内容 | 位置 |
|---|---|
| 工程日志原 README（全项目总览） | [`README-engineering-log.md`](README-engineering-log.md) |
| 9 份模块化工程文档（01-overview → 09-lessons-learned） | 仓库根目录 |
| kernel/运行时优化的完整数据链（教程引用的「为什么值」侧） | [`06-kernel-runtime-optimization.md`](06-kernel-runtime-optimization.md) · [`05-profiling.md`](05-profiling.md) |
| B300 训练证据归档 | [`b300/`](b300/) |
| DSpark 910C 推理记录 | [`dspark-910c-inference.md`](dspark-910c-inference.md) |

## 相关分支

| 分支 | 内容 |
|---|---|
| `main` | 项目介绍（中英双语 README，结果榜 + 全生命周期叙事） |
| `perf/tilelang-bridge` | **生产接线真源**：TileLang 桥接 side-load 进 ggml-cann 的代码 |
| `competition/final-ascend-track-a` | 最终提交（冻结 runtime `fd3dd36`） |
| `docs/engineering-log` | 冻结的工程日志（本分支的基线） |
