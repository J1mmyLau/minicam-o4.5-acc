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

  /workspace/cann-migration-9.0-to-9.1/e2e-ngl8/STATUS.md
  /workspace/cann-migration-9.0-to-9.1/e2e-ngl8/HANDOFF.md

STATUS.md 必须包含当前真实现场。
HANDOFF.md 必须包含 commit chain、已完成/未完成、文档清单。

==================================================
三、同步真实现场
==================================================

REPO=/workspace/llama.cpp-omni-ngl8-e2e

更新 Markdown 前必须执行：git branch/rev-parse/status/diff/log/worktree/stash，
sha256sum 二进制，ps 后台进程。不得只依赖记忆。

==================================================
四、保存未提交现场
==================================================

/compact 前保存 checkpoint 到：
/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/checkpoints/<timestamp>/

不得为了"干净"而 git checkout/reset/stash 丢弃未提交 diff。

==================================================
五、compact 后恢复
==================================================

compact 后第一件事：重新读取 STATUS.md、HANDOFF.md、git status/diff、后台进程。
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

# PROGRESS UPDATE ENFORCEMENT

这是本文件最重要的部分。进度文档不是"忙完了再写"，而是**每完成一个原子步骤就必须立即同步**。
文档滞后 = 上下文恢复失败 = 会话断裂 = 返工。

==================================================
一、触发条件
==================================================

以下任一事件发生后，**必须在同一个 tool call batch 或紧接着的下一步**更新对应文档：

| 触发事件 | 必须更新的文件 | 必须更新的内容 |
|---------|-------------|-------------|
| 任务/实验状态变化（START→RUNNING→DONE/REJECTED/BLOCKED） | STATUS.md, HANDOFF.md, AUDIT.md | 该任务的状态、结论、证据路径 |
| 新 commit 产生 | HANDOFF.md | commit chain、HEAD 更新 |
| 新实验数据产出（baseline、A/B、sweep 等） | HANDOFF.md, AUDIT.md | n、指标、结论、数据路径 |
| 发现新 bug/问题（F-xxx） | HANDOFF.md, AUDIT.md | 分类、根因、状态 |
| Gate 通过/拒绝 | STATUS.md, AUDIT.md | Gate 名、判定、关键数据 |
| /compact 前 | STATUS.md, HANDOFF.md | 完整现场同步 |
| 会话结束/中断前 | HANDOFF.md | 当前任务、残留进程、下一步 |

==================================================
二、禁止行为
==================================================

- ❌ "先跑完这批实验再一起更新文档"
- ❌ "等结果出来了我再写"
- ❌ "现在太忙，文档不急"
- ❌ 让文档落后代码/数据超过 1 个实验步骤
- ❌ 用"我记得"代替写入文件
- ❌ 恢复上下文时只信摘要，不信磁盘文件

==================================================
三、文档优先级
==================================================

**STATUS.md** — 每次事件后更新。简短。当前 phase、每项 F-xxx 状态、HEAD、剩余任务。
**HANDOFF.md** — 每次事件后更新。完整交接：commit chain、已完成表、未完成表、文档索引。
**AUDIT.md** — 每次事件后追加一行。机读格式：`## YYYY-MM-DD HH:MM | TYPE | RESULT`。
**TASKS.md** — 任务状态变化时更新。旧项改状态，新项追加。

==================================================
四、更新示例
==================================================

错误做法：
```
[跑完 chunking A/B] → "结果出来了，p50 delta -8ms，我先更新文档" → [实际没更新]
```

正确做法：
```
[跑完 chunking A/B] → 立即写入 STATUS.md（Chunking→REJECTED）→
写入 HANDOFF.md（结果、证据路径）→ 追加 AUDIT.md（DECISION | CHUNKING_REJECTED）→
继续下一任务
```

==================================================
五、文档路径映射
==================================================

| 作用域 | 路径 |
|--------|------|
| 项目状态 | `/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/STATUS.md` |
| 交接文档 | `/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/HANDOFF.md` |
| 下一步 | `/workspace/cann-migration-9.0-to-9.1/e2e-ngl8/NEXT_ACTION.md` |
| 审计日志 | `/workspace/llama.cpp-omni-ngl8-e2e/docs/tracking/AUDIT.md` |
| 任务清单 | `/workspace/llama.cpp-omni-ngl8-e2e/docs/tracking/TASKS.md` |
| F005 状态 | `/workspace/cann-migration-9.0-to-9.1/f005/STATUS.md` |
| F004 状态 | `/workspace/cann-migration-9.0-to-9.1/f004/STATUS.md` |
| F003 状态 | `/workspace/cann-migration-9.0-to-9.1/f003/STATUS.md` |

==================================================
六、恢复时文档优先
==================================================

当从 compact 恢复或 session 继续时，第一优先级是**读文档**，第二优先级是**读 git**。
不得先凭记忆输出状态，再"补文档"。

恢复顺序：
1. 读 STATUS.md → 了解当前 phase
2. 读 HANDOFF.md → 了解最新 commit、待完成任务
3. git log --oneline -10 → 核实 HEAD
4. git worktree list → 核实工作目录
5. ps aux → 核实残留进程
6. 用文档内容覆盖记忆 → 继续执行

==================================================
七、状态冲突处理规则 (STATE CONFLICT RESOLUTION)
==================================================

当会话记忆、任务面板、Git、STATUS、HANDOFF、AUDIT 之间出现冲突时，
必须按以下优先级确定真实状态：

1. 当前 worktree 的 Git HEAD、status 和实际文件
2. STATUS.md
3. HANDOFF.md
4. AUDIT.md
5. TASKS.md
6. 当前进程、日志和结果文件
7. 会话记忆和历史聊天内容

禁止让旧会话记忆覆盖更新后的磁盘状态。

若发现以下任一情况，必须先进入 STATE_RECOVERY，不得直接执行任务：

- 当前目录与 HANDOFF 中的 worktree 不一致
- 当前 HEAD 与 HANDOFF 中记录的 commit 不一致
- TASKS 显示 PENDING，但 AUDIT 已记录完成
- 会话声称某 Gate 未完成，但 STATUS 已记录 PASS
- 路径指向旧的 f003/f004 worktree
- 当前任务标题与 NEXT_ACTION.md 不一致

STATE_RECOVERY 必须执行：
```
git worktree list --porcelain
git status --short
git log --oneline -10
读取 STATUS.md
读取 HANDOFF.md
读取 NEXT_ACTION.md
读取 AUDIT.md 最新条目
检查正在运行的进程
```

恢复完成后，先输出一份状态快照，再继续任务。
不得根据旧上下文补写或反向修改最新文档。

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
完成当前步骤 → 更新 STATUS.md + HANDOFF.md + AUDIT.md → 根据待办优先级选择下一项
→ 立即执行 → 遇到普通问题自行排查 → 直到达到最终停止条件。

---

# CURRENT PHASE: Post-E2E-Baseline

F003 FIXED。F004 VALIDATED。F005 PROTECTION_IMPLEMENTED/RECALL_LIMITED。
E2E Baseline DONE。Chunking REJECTED。
Production config: ngl=8 hybrid（Talker ngl=8, Flow CANN, Vocoder CPU, F005 opt-in）。

当前任务优先级：
1. F005 recall 提升 — 扩大异常样本集，tune 熵阈值
2. F005 retry/fallback 生产开关策略 — recall ≥60% 后可默认开启
3. ngl=8 production config 文档化
4. E2E baseline LLM 瓶颈分析 — LLM 占 FA 69%，寻找优化方向

最终停止条件：
A. 成功完成全部 Gate
B. 外部硬阻塞（缺失文件/凭据/硬件故障/权限不足）
