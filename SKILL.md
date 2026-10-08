---
name: literature-reading-brief
description: 在本机生成证据化中文文献简报，获取并核验正式出版全文，导入 Zotero，并开展互动领读、笔记沉淀与研究断点记忆。适用于用户要求文献推荐、每日简报或论文领读。
---

# 文献阅读简报

本目录是技能源码，工作区是用户选定的本地 Vault。若当前目录没有 `_scripts/daily_brief_gate.py`，先参照 README 使用 `install.ps1 -VaultPath <用户选定路径>` 初始化，不向任意现有文库覆盖文件。不把技能源码目录默认为用户个人文库。新机器缺少 Zotero、ScanSci 或身份授权时如实报告，不创建虚假的已投递状态。

## 路由

- 简报、全文入库、阅读与笔记：完整读取 `_skills/literature-workflow/SKILL.md`。
- 实质研究或开发开始：读取 `_skills/research-second-brain/SKILL.md`，在工作区运行 `_scripts/research_brain.py dashboard`。保存已验证进度、断点、下一步与会话关联；查询闲聊不创建任务。
- 互动领读：读取 `_skills/literature-workflow/references/guided-reading.md`。默认中文纯文字，按概念依赖讲解和检查理解。主课后分别引导“我形成的理解与判断”“可引用观点”“与我当前研究的关系”，不能替用户编造个人判断。

## 每日交付

1. 使用安装后的 Python 环境运行 `_scripts/daily_brief_gate.py status`，按本地日期去重。未投递时运行 `generate`。`--direct` 仅在用户确实需要绕过代理时使用，不默认关闭用户代理。
2. 修改并使用工作区 `_references/research-topics.yml`；内置交通安全配置只是示例。开放元数据来自 OpenAlex/Crossref；不抓取 Google Scholar/CNKI。
3. 对正式 Top 5 逐篇核验期刊 JIF 年份、数值与来源，以及 JCR Q1/Q2 或中科院 1/2 区来源；会议需有可追溯的顶级分级来源。未核验或不达标则排除，候选不足就说明，不凑数。
4. 首篇全文由 Codex 获取并核验题名、DOI、出版版本和本地文件。只允许合法正式出版版，不以预印本、接受稿或版本不明文件代替。ScanSci 只保留正式出版来源，禁止 Sci-Hub、Tor 或绕过访问限制。来源失败后尝试其他合法出版方渠道；无法取得就明确失败，不标记已下载或已投递。其他候选有正式开放 PDF 时附逐篇直接链接。
5. Codex 完成中文译名、摘要翻译和有证据的推荐理由，保存至当日 JSON，并用 `_scripts/refresh_daily_brief.py --date YYYY-MM-DD` 重建 Markdown。检查 Markdown 与 selected/top_candidates 均一致，没有“待 Codex 补译/补写/补充”等中间稿。不要在简报中预写精读报告。
6. 核对 Zotero 父条目、PDF 附件和“每日文献阅读”分类关系，保留此前推荐的分类成员。交付本地 PDF 与 Markdown 链接；实际交付成功后才运行 `mark-delivered`。只有 `generate` 成功不等于正式简报已经交付。

## 数据和授权边界

- 论文知识和已核实理解写入 `Literature/notes`；流程状态与任务断点写入 `_data/brain` 或运行状态，不写入论文正文。
- Zotero 是原始文献源，不直接写 SQLite，不移动/删除原始库。Local API 身份凭据只存系统 keyring，不写入聊天、代码或 Git。
- 本地定时任务仅在电脑、Codex 与必要应用运行期间工作；只有用户要求时才设置，不能承诺精确开机触发或关机后台运行。模板见 README。
- 本包不包含任何个人文献、推荐历史、研究记忆、账号配置或虚拟环境。安装者的数据从空状态开始。
