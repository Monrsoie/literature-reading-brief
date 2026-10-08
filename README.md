# 文献阅读简报 Skill

在本机把“发现论文 → 正式全文核验 → Zotero 入库 → 中文简报 → 互动领读 → 知识沉淀”连成一个工作流。由 Codex 完成翻译、证据核验和讨论，Python 处理可重复的检索、去重、文件生成与本地应用桥接。

## 当前能力

- OpenAlex / Crossref 开放元数据检索，按子主题轮换；每天推荐一篇，最多保留五篇候选，六个维度各 0–5 分。
- 正式推荐前核验 JIF 年份、数值、来源及 JCR Q1/Q2 或中科院 1/2 区；会议需有顶级级别依据。候选不足会如实说明。
- ScanSci 合法来源下载包装器，仅接受正式出版版，核验标题、DOI、页数和 SHA-256；不以预印本或接受稿替代。首篇附本地 PDF，其他开放正式 PDF 附直接链接。
- Zotero 10 Connector + 官方 Local API 入库，核对 PDF 附件；“每日文献阅读”累积保留历史推荐，不自动清空分类。
- 中文纯文字互动领读，按理解调整课程；主课后分别形成个人判断、可引用观点与研究联系，讨论后再整理笔记。
- 本地 research-second-brain：任务/断点、调研发现、设计决策、每日进展、周目标、会话与任务关联。
- 本地日期去重与投递回执；只在电脑和必要应用运行期间工作，不依赖关机云端托管。

这不是桌面安装插件，也不是单独运行就能生成完整中文简报的 Python 服务。脚本输出是中间稿，Codex 必须完成译名、摘要翻译、推荐理由及证据核查后再交付。下载失败或 Zotero 不可用时不得宣称已投递。无 DOI 或正文无法提取身份信息的 PDF，当前自动核验可能无法通过，需要人工核验，不能绕过校验伪造成功。

## 安装（Windows）

当前发行版以 Windows 10/11 工作流为基准；未验证 macOS/Linux 安装、进程清理与系统 keyring。需要 Python 3.11+、Codex、本机 Zotero 10。Obsidian 可选，直接使用 Markdown 也可以；Git 仅在使用 clone 时需要。

```powershell
git clone https://github.com/Monrsoie/-skill.git literature-reading-brief
cd literature-reading-brief
.\install.ps1 -VaultPath 'D:\MyResearchVault'
```

也可以在 GitHub 下载源码 ZIP，解压后执行安装。安装脚本把源码和示例配置复制到指定 Vault，创建隔离环境 `tools/scansci-pdf-env`，安装 `requirements.txt`，并在实际 CODEX_HOME（未设置时为用户 `.codex`）注册技能。已有不同内容的文件或同名技能会导致停止，绝不强行覆盖。依赖安装失败时不会注册技能；已复制的工作区保留，修复后可重试。脚本不更改系统执行策略；若系统禁止本地脚本，请按组织允许的方式运行，不必全局关闭安全策略。

安装后在 Codex 打开该 Vault，调用 `$literature-reading-brief`；新技能未显示时重新打开 Codex。不想注册技能可使用 `-SkipSkillRegistration`，在项目中让 Codex 读取根目录 `SKILL.md`。`-SkipDependencies` 只适用于已有可用环境或源码安装验证，不表示下载依赖已准备好。

### 首次配置

1. 修改 `_references/research-topics.yml` 中主题、核心词、方法词、启发词、子主题与查询。内置交通安全词表只是演示；不含作者个人文库与研究记录。
2. 核验或替换 `_references/journal-metrics.yml`。它是带来源的历史快照，不是实时 JCR 数据库。更换领域需要添加对应期刊/会议；旧指标或无可靠来源的行不能用于正式推荐。
3. 打开 Zotero 10，在其设置中允许本机 Local API，首次运行在 Zotero 内批准授权。凭据由系统 keyring 保存，不向 Codex 聊天或仓库提供。端口为本机 `127.0.0.1:23119`。不要运行 `zotero_daily_collection.py` 的清理命令作为日常任务：它是仅供明确授权的分类整理工具。
4. 可选：用 Better BibTeX 自动导出 `references.bib` 到 Vault。已有 Zotero 数据默认只读检查用户目录 `Zotero/zotero.sqlite`；自定义数据目录通过本地环境变量 `ZOTERO_DATA_DIR` 指定。程序不直接写入此数据库。

安装后可先检查，不触发网络检索或导入：

```powershell
cd 'D:\MyResearchVault'
.\tools\scansci-pdf-env\Scripts\python.exe -X utf8 _scripts/daily_brief_gate.py status
.\tools\scansci-pdf-env\Scripts\python.exe -X utf8 _scripts/research_brain.py dashboard
```

给 Codex 的首次请求示例：

> 使用文献阅读简报技能，检查我的主题配置并生成今天的正式简报。帮我获取并核验首篇正式出版 PDF，导入 Zotero 的“每日文献阅读”；完成中文译名、摘要翻译和推荐理由，其他候选附正式开放 PDF 链接。失败如实说明，不标记投递。

### 本地定时任务

确认手动流程成功后，再请 Codex 创建本机定时任务，选择自己的检查时段或周期。任务提示词可复用：

> 在本地 Vault 使用文献阅读简报技能。按本地日期先检查投递状态，已投递不重复通知；未投递则完成检索、证据核验、中文简报、正式全文下载与 Zotero 入库。首篇给本地 PDF，其他候选给正式开放 PDF 直接链接。只在实际交付成功后写投递回执；失败保持未投递并报告需要处理的问题。不要恢复旧任务、清空历史分类或提前生成阅读报告。

需要电脑、Codex 和 Zotero 可用；不是 Windows 开机事件钩子，不承诺开机瞬间执行。仓库不会替安装者创建定时任务，未在陌生机器验证休眠恢复或补跑行为。

## 数据位置与隐私

| 位置 | 用途 |
|---|---|
| `_references/` | 用户主题、指标来源和笔记模板 |
| `maps/daily-briefs/` / `_data/daily-briefs/` | Markdown / JSON 简报 |
| `Literature/pdfs/` / `Literature/notes/` | 本地全文与知识笔记 |
| `_data/pdf-downloads/` / `_data/zotero-imports/` | 下载核验和导入状态 |
| `_data/daily-delivery/` | 本地日期投递状态 |
| `_data/brain/` | 研究/阅读断点和过程记录，不是选题依据或推荐历史 |

上述个人运行数据均被 `.gitignore` 排除，发行包不携带任何既有记录。检索会向开放元数据服务发送查询和 DOI；下载会访问论文来源；Zotero 桥接只访问本机 API。没有新增遥测。不得上传他人或付费论文 PDF、凭据和个人笔记。

## 开发验证

```powershell
.\tools\scansci-pdf-env\Scripts\python.exe -X utf8 -m unittest discover -s _scripts -p 'test_*.py'
```

单元测试隔离网络与 Zotero 写入，用合成样例核验去重、正式全文版本门禁、题名/DOI 校验、导入回滚和分类保留。单元测试通过不代表在每台电脑真实下载、机构认证、Zotero 或定时运行均已通过。

## 许可证与来源

仓库主许可证沿用作者创建仓库时选定的 Apache-2.0，见 LICENSE。研究记忆技能源于 `oridanus/claude-second-brain`，保留其 MIT 声明；ScanSci 是单独安装的依赖，未复制其源码或环境。详见 THIRD_PARTY_NOTICES.md。
