# FAILURES

## F-009：FINAL-AB Wall Timer Bug (run_ab.sh)

- 日期：2026-07-18
- 任务：FINAL-AB 实验
- 脚本：harness/experiments/FINAL-AB/run_ab.sh
- 环境：Ascend910 (×2), CANN 9.0.0
- 结果：ab.log 中所有 20 对 wall=0
- 失败类型：Harness 脚本（计时）
- 根因：run_ab.sh line 52 Python f-string 语法错误：
  `python3 -c "print(f'{$t1} - {$t0}':.1f)"`
  花括号 `{$t1}` 在单引号字符串内不会被 shell 展开，Python 收到的是字面量 `f'{$t1} - {$t0}'`，
  变量替换失败，fallback echo "0" 被写入 result.txt
- 修复：使用 `python3 -c "print(f'{t1 - t0:.1f}')"` 或直接 `echo "$t1 - $t0" | bc`
- Wall time 恢复：从 stdout.log 文件 birth time→mtime（stat %W→%Y）恢复，
  可靠性有限（包含文件系统延迟，不含模型加载前时间）
- 是否重试：否（不重跑已有 A/B）
- 证据：harness/experiments/FINAL-AB/run_ab.sh:52

## F-008：EXP-005-V3-B Persistent Worker Deadlock Bug

- 日期：2026-07-17
- 任务：EXP-005-V3-B persistent worker thread
- Baseline commit：3f7a7f0
- 实验代码：uncommitted, branch perf/exp005-v3b-persistent-worker
- 环境：Ascend910, CANN 9.0.0 (but T2W on CPU)
- 假设：Persistent worker 线程复用消除 std::async thread creation overhead
- 修改：push_tokens_window 中 vocoder 改为 submit→worker→wait 模式
- 结果：call 0 完成后，call 1 在 retrieve-previous-result 处死锁
- 失败类型：正确性（死锁）
- 根因：call 0 在 is_first 路径同步消费 worker 结果（设置 result_ready=false），
  call 1 进入 !is_first 路径尝试获取 "previous result"，但结果已被 call 0 消费。
  Worker 没有收到新请求，result_ready 永远为 false → 死锁。
- 修复：移除 broken "retrieve previous" pipeline pattern，改为统一 synchronous-via-worker
  （submit→wait→get，所有非 final 窗口一致）
- 修复后 correctness：PASS（WAV SHA256 完全一致）
- 修复后 performance：NEUTRAL (+0.3%)
- 证据：harness/experiments/EXP-005-V3-B-persistent-worker/

## F-007：EXP-005-V3 Async Vocoder Correctness Bug

- 日期：2026-07-17
- 任务：EXP-005-V3 Dedicated T2W A/B Benchmark
- Baseline commit：3f7a7f0
- Experiment commit：ce2dbe1 (perf/exp005-instrumentation)
- 环境：Ascend910 (device 0), CANN 9.0.0, F16 GGUF
- 假设：std::async per-window vocoder 可与 next encoder+flow 重叠
- 修改：push_tokens_window 中 vocoder 改为 std::async(std::launch::async)
- 命令：token2wav-example with OMNI_T2W_REPEAT=5
- 结果：Async 产生与 sync 不同的音频输出（451200 vs 427200 samples, -5.3%）
- 失败类型：正确性
- 根因：async_wave_out_ retrieval offset bug
  - call 0 (is_first): launch async, wait, retrieve → async_wave_out_ consumed
  - call 1 (non-first): retrieve → async_wave_out_ already empty（consumed by call 0, not yet set by new async）
  - call 17: async output lost（final call runs sync, never retrieves）
  - Audio shifted by 1 chunk, net loss of 1 chunk
- 已排除：random seed, flow matching randomness, WAV I/O
- 后续建议：V3-B persistent worker thread with correct double-buffer or queue pattern
- 是否重试：否（V3 failed, move to V3-B）
- 证据：harness/experiments/EXP-005-token2wav-pipeline/benchmarks/
  - comparison.json, correctness_summary.md, window_timeline.csv

## F-001：Full Omni (Audio+Vision) Vision CANN NaN

- 日期：2026-07-15
- 任务：llama.cpp-omni Reference Baseline / Full Omni test
- Commit：`6eeeb4d`
- 环境：Ascend910, CANN 9.0.0, F16 GGUF
- 假设：CANN Vision 后端产出 NaN 嵌入
- 修改：vision.cpp cb 增强 + nan_check_embed + OMNI_VISION_CPU
- 结果：**NOT REPRODUCED** — 单图和多切片路径均 NaN=0
- 失败类型：正确性
- 根因：未确定；当前证据无法确认。可能来自环境差异、图片内容或 batch 配置
- 已排除：异步同步、CANN vs CPU 后端差异、多切片路径
- 后续建议：若再次出现，保存原始图片 + 命令 + env + 模型 hash + 边界统计
- 是否重试：条件满足后（获得原 NaN 条件）

## F-002：CANN BatchMatMulV3 内核缺失

- 日期：2026-07-15
- 任务：vision_image_batch_encode (batch_size > 1)
- Commit：`6eeeb4d`
- 环境：Ascend910, CANN 9.0.0
- 假设：CANN 图编译应支持 batch matmul
- 修改：无
- 命令：`vision_image_batch_encode` with batch_size > 1
- 结果：`EZ9999: Inner Error! Cannot find bin of op BatchMatMulV3`
- 失败类型：运行时
- 根因：CANN 内核注册/编译缺失 (`ggml/src/ggml-cann/aclnn_ops.cpp`)
- 已排除：—
- 后续建议：检查 CANN 内核包配置，或使用 serial fallback
- 是否重试：是（CANN 内核配置后）

## F-003：TTS CANN 设备 1 崩溃

- 日期：2026-07-15
- 任务：Full Omni with TTS on CANN (both devices)
- Commit：`6eeeb4d`
- 环境：Ascend910 (×2), CANN 9.0.0
- 假设：TTS 模型可完全运行在 CANN 双卡上
- 修改：`tts_gpu_layers: -1 → 0`（TTS 退 CPU）
- 结果：设备 1 `aclnnRepeatInterleave` 崩溃，设备 0 正常
- 失败类型：运行时
- 根因：CANN 多设备算子注册不完整
- 已排除：—
- 后续建议：修复 CANN 多设备算子，恢复 TTS GPU 加速（当前 RTF ~3.9）
- 是否重试：条件满足后（多设备 CANN 算子补全）

## F-006：Stability Harness 脚本 Bug（WAV 路径 + timeout）

- 日期：2026-07-16
- 任务：TASK-004 Stability Test
- 提交：3f7a7f0
- 环境：Ascend910, CANN 9.0.0, F16
- 结果：3 轮全部判定 FAIL，但 iter-1 模型实际正常（exit=0, TTS=0, 4 WAVs）
- 失败类型：Harness 脚本
- 根因：
  1. WAV 搜索路径 `/workspace/llama.cpp-omni-clean/tools/omni/output/` 与实际输出 `./tools/omni/output/` 不匹配
  2. timeout=180s 过短（Full Omni median=68s, max=121s）
- 已排除：模型不稳定
- 后续建议：修正脚本（绝对路径 + timeout≥300s）后重跑
- 是否重试：是（修正后）

## F-005：Audio-only baseline run-02 超时中断

- 日期：2026-07-16
- 任务：TASK-003B Audio-only Reference Baseline
- 提交：3f7a7f0
- 环境：Ascend910, CANN 9.0.0, F16 GGUF
- 结果：run-02 在 10 分钟超时内未完成（该轮 WAV 数量异常大）
- 失败类型：资源（超时）
- 根因：Audio-only 测试每轮生成大量 WAV（14–81），单轮耗时可达 5 分钟以上
- 后续建议：增加超时限制或减少测试样本数
- 是否重试：否（已有 4/4 有效 measured）

## F-004：Vision Debug Print 在 Full Omni 路径下为空

- 日期：2026-07-15
- 任务：调试 Vision 编码张量
- Commit：`6eeeb4d`
- 环境：Ascend910, CANN 9.0.0
- 假设：`Omni_DEBUG_GRAPH=1` 在 Full Omni 路径下应打印所有张量
- 修改：增强 debug_print_tensors 输出 NaN/Inf 统计
- 结果：header 打印正常，但无 tensor 数据输出
- 失败类型：可观测性
- 根因：待查（可能与 graph 构建时机或 tensor 生命周期有关）
- 后续建议：调查 debug_print_tensors 在 `vision_image_encode` 而非 `vision_image_batch_encode` 的注册路径
