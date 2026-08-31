# RTS 性能评测结果（Track A 主指标）

## 状态

**DONE — 4-run 主统计（2026-08-29/30）+ 提交前 3-run 复测（2026-08-31）**

| 指标 | 值 |
|---|---|
| core RTF（4-run mean±stdev） | **0.4829 ± 0.0161** |
| core RTF（提交前复测 3-run） | **0.4840 ± 0.0125**（0.4736/0.4978/0.4806） |
| SPEAK→wav 均值（4-run mean） | 647.9 ms |
| 本地基线（4-run） | 0.6754 ± 0.0152 / 827.1 ms |
| 官方 Track A baseline | 1.087（1087.3 ms） |
| 相对本地基线 | **−28.5%** |
| 相对官方基线 | **−55.6%** |

## 测试命令

```bash
./submission/scripts/run_rts.sh <seed>    # seeds 1001-1004
# 等价于（关键 env 由脚本注入）:
#   set -a; source submission/config/server.env; set +a
#   OMNI_T2W_N_TIMESTEPS=2 OMNI_T2W_PROMPT_CACHE=<nfe2 cache> \
#   EVAL_CONFIG=$PWD/config-local.env ./evaluation/run_eval.sh rts
```

## 参数

- 视频：`evaluation/judge-final/assets/video/omni_duplex1.mp4`（120s 双工）
- harness：`run_judge_direct.py`（同一条计时边界：core RTF = Σ段耗时/Σ音频时长）
- server 启动 env = config/server.env（A+C + TileLang 核 + NFE2 launch-only）
- 每 run 完整视频 26+ SPEAK 段

## 原始输出（本机 /tmp，提交时建议归档进 run 产物）

| seed | 目录 | core RTF | SPEAK→wav mean/median (ms) | 分解 |
|---|---|---|---|---|
| 1001 | /tmp/rts_step10_s1001 | 0.4960 | 625.6 / 607.2 | encode 0.0611 + prefill 0.066 + decode 0.1325 + tts 0.141 + t2w 0.0955 |
| 1002 | /tmp/rts_step10_s1002 | 0.4603 | 639.7 / 638.9 | encode 0.0598 + prefill 0.0658 + decode 0.1169 + tts 0.1358 + t2w 0.0821 |
| 1003 | /tmp/rts_step10_s1003 | 0.4829 | 685.5 / 713.1 | encode 0.0572 + prefill 0.0687 + decode 0.1328 + tts 0.1363 + t2w 0.0879 |
| 1004 | /tmp/rts_step10_s1004 | 0.4925 | 640.8 / 617.4 | encode 0.0604 + prefill 0.0651 + decode 0.1374 + tts 0.1496 + t2w 0.08 |

复核 run：/tmp/rts_configverify（RTF 0.4901，SPEAK→wav 602.0/528.0ms）

judge 会话报告（含每段 WAV + 逐段计时）：
`evaluation/judge-final/sessions/20260829_165919_omni_direct_54021_r1/eval_e2e_report.json` 等。
