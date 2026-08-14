# 优化报告（提交物）

> 结构见 `docs/competition-submission/PERFORMANCE_REPORT_TEMPLATE.md`。最终落本文件。
> 当前：章节骨架就绪，内部证据可回填（1-10、14-16），官方口径待定（11-13）。

## 主线

```
MiniCPM-o 4.5 → Main LLM → Talker → Token2Wav → Flow → Vocoder → streaming audio
原始瓶颈：T2W CPU 设备放置 93%（decode→speak 仅 2.9%）
优化：静态前缀 KV Cache（prefill 2.4×）/ 生命周期 / CANN Flow/Vocoder（W0 −81.4%）
      / TTS KV bounds guard / 文本+SSE 接口修复
```

## 待回填章节

- [ ] 2. 官方基线（官方数字到达后）
- [ ] 11. chunk RTF 正式结果（官方口径）
- [ ] 12. 精度结果（三项官方 Benchmark）
- [ ] 13. Demo 稳定性（官方 Demo 接入后）
