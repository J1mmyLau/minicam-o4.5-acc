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

---

# CONTINUATION AND CONFIRMATION POLICY

本项目采用自主执行模式。

除非操作涉及以下高风险事项，否则禁止向用户请求确认：
- 删除或覆盖用户数据；
- git reset --hard、git clean -fd、强制覆盖未保存代码；
- 修改冻结 Release；
- 重装或升级 Driver、Firmware、CANN；
- 需要管理员权限且会改变系统级环境；
- 推送、合并或发布到远端正式分支；
- 无法逆转的外部操作。

以下情况一律不得询问"是否继续"：
- 一个中间 Gate 通过；
- 10轮或20轮稳定性完成；
- 找到下一步任务；
- 出现新的算子错误；
- 文档写入失败；
- 构建失败；
- 测试失败；
- 需要补做正确性验证；
- 需要跑音质、性能或生命周期测试；
- 已经明确存在待完成项。

当当前结果仍包含 PENDING、BLOCKED、EXPERIMENTAL、PARTIAL、UNVALIDATED、
NEEDS_MORE_EVIDENCE 等状态时，必须自动执行下一项，不得停止汇报。

禁止使用以下句式：
- 是否继续？/ 需要我继续吗？/ 要不要继续跑？
- 是否需要进一步验证？/ 接下来要做吗？/ 请确认后我继续。

正确行为：
完成当前步骤 → 更新 STATUS.md 和 F003_HANDOFF.md → 根据待办优先级选择下一项
→ 立即执行 → 遇到普通问题自行排查 → 直到达到最终停止条件。

F-003 自动执行顺序：
1. non-neox CPU/CANN 数值对齐
2. neox/non-neox 模式交替和 cache 复用测试
3. 20轮稳定性
4. CPU Talker 与 CANN Talker 配对音频生成
5. 自动音频合法性检查
6. ASR 回转或等价内容一致性检查
7. 人工盲听材料整理
8. CPU/CANN 严格交错 A/B
9. First Audio、Talker ms/token、RTF、E2E、HBM、RSS 统计
10. 生命周期和重启验证
11. 决定 7df34a1 接受、修改或拒绝
12. 更新最终文档和提交状态

不得因为某一步通过而停止。

最终停止条件：
A. 成功完成全部 Gate
B. 外部硬阻塞（缺失文件/凭据/硬件故障/权限不足）
