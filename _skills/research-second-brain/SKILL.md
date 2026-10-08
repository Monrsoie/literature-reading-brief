---
name: research-second-brain
description: 在每日文献 Vault 中恢复研究任务断点，保存调研发现、设计决策、每日进展、周目标及 Codex 会话关联。
---

# Research Second Brain

从 oridanus/claude-second-brain 的 brain、brain-new-task、brain-save、brain-set-task、brain-show-tasks 迁移到 Windows/Codex。上游 MIT 许可证见 LICENSE。数据限定于当前工作区的 `_data/brain/`，不随技能分发已有记录。

## 入口

在 Vault 根目录运行 `python _scripts/research_brain.py dashboard`，按任务 ID 读取对应 Markdown 正文。仅查询时不创建记录。

- 新建任务：`python _scripts/research_brain.py add tasks --title "标题" --body "范围和验收标准" --priority high`
- 保存发现：`python _scripts/research_brain.py add findings --title "发现" --body "证据、来源路径或 URL、未验证部分" --task TASK_ID`
- 保存决策：`python _scripts/research_brain.py add decisions --title "决策" --body "选择、理由、考虑过的替代方案和影响" --task TASK_ID`
- 每日进展：`python _scripts/research_brain.py add progress --title "进展" --body "完成了什么、验证结果" --task TASK_ID --session SESSION_ID`
- 周目标：`python _scripts/research_brain.py add goals --title "本周目标" --body "用户已确认的目标及完成条件"`；默认当前本地日历周，禁止凭空增加目标。
- 会话关联：`python _scripts/research_brain.py link TASK_ID --session SESSION_ID --state active`
- 断点保存：`python _scripts/research_brain.py checkpoint TASK_ID --stopped "最后已验证结果" --next "具体下一步" --status open --session SESSION_ID`

## 恢复和保存

项目实质任务开始时读取 dashboard、当前周目标及相关任务；按用户当前请求匹配，多个合理匹配时先读正文。不可用标题模糊匹配直接改写多个任务。

已知实际 Codex task/thread ID 时用完整 ID；不知道时记 unknown，不能用猜测的 ID。用户明确要求关联其他任务时，用应用任务工具核实。statuses 是最后记录的关联状态，不是实时进程监控；显示更新时间，不能把旧 active 记录宣称为仍在运行。

完成重要阶段、交接或本轮结束前保存 where_stopped 和 next_action，记录实际验证结果；完成才标记 done，阻塞要写原因。更新对应 session 状态为 idle/blocked/done。每次 checkpoint 会新建进展记录以保留历史。

发现区分观察与推断；决策保存理由；论文报告仍放 Literature/reports，记忆中用链接引用。查询 next 时综合优先级、时间、周目标和阻塞提出最多三项下一步，并引用具体记录。

这些是文件级持久记忆和 agent 执行约定，不依赖 Claude/macOS hooks。新任务通过 AGENTS.md 路由恢复。强制结束进程只能恢复最后已保存断点。不要声称已注册每十分钟或崩溃自动保存 hooks。
