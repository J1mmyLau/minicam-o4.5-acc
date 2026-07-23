IMPORTANT: Ensure you've thoroughly reviewed the [AGENTS.md](AGENTS.md) file before beginning any work.

---

# AUTONOMOUS CONTEXT MANAGEMENT POLICY

本项目属于长时间自主调试任务。

你必须主动管理上下文，不得等到 context 100% 或 API 报 maximum context length 后才处理。

==================================================
一、上下文阈值
==================================================

当满足以下任一条件时，必须主动进入 CONTEXT_CHECKPOINT 流程：

1. context 使用率达到或接近 75%；
2. 已连续执行大量工具调用、读取大日志或代码；
3. 当前会话已经积累多个实验分支、修复和回退；
4. 即将开始长时间构建、稳定性测试或新故障排查；
5. 你判断后续任务仍需较多上下文；
6. Claude Code 提示 context remaining 较低；
7. 距离自动压缩阈值已不足安全余量。

禁止等到：95%、100%、maximum context length、/compact 本身无法执行。
建议在约 70%～80% 时压缩。

==================================================
二、压缩前必须同步 Markdown
==================================================

执行 /compact 前，必须先更新：

  /workspace/cann-migration-9.0-to-9.1/f003/F003_HANDOFF.md
  /workspace/cann-migration-9.0-to-9.1/f003/STATUS.md

F003_HANDOFF.md 必须包含当前真实现场，固定结构见完整策略。
STATUS.md 为简短状态摘要。

==================================================
三、同步真实现场
==================================================

REPO=/workspace/llama.cpp-omni-token2wav-cann

更新 Markdown 前必须执行：git branch/rev-parse/status/diff/log/worktree/stash，
sha256sum 二进制，ps 后台进程。不得只依赖记忆。

==================================================
四、保存未提交现场
==================================================

/compact 前保存 checkpoint 到：
/workspace/cann-migration-9.0-to-9.1/f003/checkpoints/<timestamp>/

不得为了"干净"而 git checkout/reset/stash 丢弃未提交 diff。

==================================================
五、compact 后恢复
==================================================

compact 后第一件事：重新读取 F003_HANDOFF.md、STATUS.md、git status/diff、后台进程。
核对 branch/worktree/HEAD/diff/runner/二进制，不得仅凭摘要继续。

==================================================
六、执行纪律
==================================================

编译失败、链接失败、路径错误、cwd重置、timeout、CANN错误、测试脚本错误等
普通问题不得导致停止。处理：定位→修复→重建→重跑→记录→继续。

只有任务成功完成或外部硬阻塞才允许停止。

==================================================
七、上下文增长控制
==================================================

长日志写文件用 grep/tail/sed；不在聊天输出完整 build log；
不重复粘贴项目背景；diff 用文件保存；及时更新 STATUS 和 HANDOFF。
