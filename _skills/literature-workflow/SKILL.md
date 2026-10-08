---
name: literature-workflow
description: Manage a local Zotero and Markdown literature workflow, including formal-paper intake, evidence-grounded interactive reading, learning notes, and feedback-based workflow improvement.
---

# Literature Workflow

Use this skill for the user's Zotero + Obsidian + Codex research workflow.

## Paths

- Vault: `<workflow-root>`
- Bibliography: `<workflow-root>\references.bib`
- Literature notes: `<workflow-root>\Literature\notes`
- Literature PDFs: `<workflow-root>\Literature\pdfs`
- Literature reports: `<workflow-root>\Literature\reports`
- Literature map: `<workflow-root>\maps\literature-map.md`
- Note template: `<workflow-root>\_references\literature-note-template.md`
- Reading report template: `<workflow-root>\_references\literature-reading-report-template.md`
- Sync script: `<workflow-root>\_scripts\sync_literature.py`
- Daily brief script: `<workflow-root>\_scripts\daily_literature_brief.py`
- Selected paper intake script: `<workflow-root>\_scripts\intake_selected_paper.py`
- Local Zotero import script: `<workflow-root>\_scripts\zotero_import_local.py`
- Reading report script: `<workflow-root>\_scripts\create_reading_report.py`
- Research topics config: `<workflow-root>\_references\research-topics.yml`
- Journal metrics config: `<workflow-root>\_references\journal-metrics.yml`
- Daily brief Markdown: `<workflow-root>\maps\daily-briefs`
- Daily brief JSON: `<workflow-root>\_data\daily-briefs`
- Zotero import drafts: `<workflow-root>\_data\zotero-imports`
- Zotero executable: `C:\Program Files\Zotero\zotero.exe`

## Role Split

- Zotero is the source of record for bibliographic metadata, PDFs, annotations, tags, collections, and citekeys.
- Obsidian is the long-term knowledge base for literature notes, reading reports, topic maps, backlinks, and review outlines.
- Codex is the workflow operator: discover candidates, generate briefs, read PDFs when available, discuss the paper with the user, and write the final Markdown artifacts.

Do not treat Obsidian as a Zotero replacement. Do not treat Zotero notes as the main place for long learning reports; store full reports in Obsidian and keep Zotero notes concise.

## Reading and Improvement Modes

- For guided reading, user answers/annotations, or consolidation of learned material, read [references/guided-reading.md](references/guided-reading.md). Use the user's current understanding and verified formal text, not a prewritten paper summary as a substitute for teaching.
- After a completed reading or note delivery, apply the same reference's **反向调优标准流程**. Also apply it when the user explicitly requests a workflow retrospective or prompt improvement. Distinguish reusable process changes from paper-specific facts and casual questions.
- Default to Chinese, pure-text interaction in this Vault. Do not generate HTML lessons merely because a general teaching skill uses them. A course outline is adjustable; understanding, not a fixed lesson count, determines completion.
- After the content lessons, guide three distinct synthesis modules: the user's understanding/judgment, citable claims, and relevance to their research. Reuse sufficient prior discussion; do not populate personal sections solely from assistant-generated conclusions. Follow the reference's module-specific guidance before consolidation.
- Follow the requested deliverable: update the existing note for a learning-note request; create a separate report or update the map only when in scope. Reading completion alone does not authorize Zotero writes, scheduled-task changes, or unrelated global skill edits.

## Formal Full-Text Policy

- For a formal daily recommendation, paper intake, Zotero attachment, or full-paper reading, accept only the final formally published full text: the publisher/journal Version of Record or the final paper in an official conference proceedings repository. Verify that the PDF title and DOI or other publication identity match the formal publication record.
- Never download or substitute a preprint as the formal full text. This includes arXiv, bioRxiv, medRxiv, SSRN, Research Square, TechRxiv, OSF Preprints, and equivalent preprint services, even when the preprint page links to the article's formal DOI.
- Preprint records may be used only as bibliographic discovery clues. If mentioned, label them as preprints; do not save their PDFs under `Literature/pdfs/`, attach them to Zotero as the article full text, mark them verified, or use them as the basis for a formal full-paper reading report.
- Treat repository manuscripts, author manuscripts, accepted manuscripts, and other non-publisher copies as non-formal unless the file itself is explicitly the publisher's Version of Record or final official proceedings paper.
- If a lawful formal full text cannot be obtained, stop automatic full-text acquisition. Keep the bibliographic record and abstract-level brief, set the PDF state to `formal_fulltext_missing`, and explicitly tell the user to obtain the authorized official PDF and provide its local path. Do not fall back to a preprint, claim that the PDF was downloaded, or imply that full-text verification succeeded.
- When the user supplies a local official PDF, validate its title and DOI or publication identity before continuing intake, Zotero attachment, or full-paper reading.
- Journal IF/JIF and quartile belong to the verified formal publication venue, not to a preprint or to the individual paper. A verified journal record does not by itself prove that a formal full-text PDF is available.

## Default Workflow

1. Read `AGENTS.md` in the Vault before making workflow changes.
2. Check whether `references.bib` exists and is non-empty.
3. Use `_scripts/sync_literature.py` to generate missing literature notes from BibTeX entries.
4. Keep note filenames stable and citekey-based.
5. Update `maps/literature-map.md` only when the user requests mapping, indexing, or relationship updates.
6. Do not move or delete Zotero-owned files unless the user explicitly asks.

## Three-Party Reading Workflow

Use this staged workflow when the user wants a paper found, stored, studied, and turned into a report:

0. **Daily intake path**: use `_scripts/daily_brief_gate.py generate` to prepare the formal-PDF and Zotero assets. Codex must still finish evidence verification, translations and recommendation reasons before delivery; do not create a reading report before actual discussion. Start a dedicated reading session only after the user has received and chosen the verified formal paper.
1. **Discover**: run `_scripts/daily_literature_brief.py --vault "<workflow-root>"` in WSL, or the Windows-equivalent path outside WSL. Generate Markdown and JSON brief outputs.
2. **Select**: confirm which paper the user wants to study. Use the selected paper's DOI/title/citekey as the stable identity.
3. **Intake**: obtain and verify the lawful formal published PDF first, then pass it explicitly with `_scripts/intake_selected_paper.py --vault "<workflow-root>" --date YYYY-MM-DD --pdf-path <verified-formal-pdf>` to generate BibTeX/RIS import drafts and the Obsidian literature note. The intake script must not download `pdf_url` on its own. Never download a preprint as the selected paper's full text. If the formal PDF is unavailable, keep the metadata artifacts and ask the user to supply the authorized official PDF.
4. **Zotero asset step**: for the automated daily workflow, run `_scripts/zotero_import_local.py --vault "<workflow-root>" --date YYYY-MM-DD --target-collection-name 每日文献阅读` and verify the parent item, cumulative collection membership, and PDF attachment. A prepared local PDF alone is not a completed daily intake.
5. **Obsidian note step**: ensure there is a citekey- or DOI-based note in `Literature/notes/`. Add Properties for Zotero/PDF/brief/report status.
6. **Original text step**: use only a verified formal published PDF from the publisher, official proceedings repository, user-supplied local file, or Zotero-exported attachment. Clearly distinguish extracted original content from Codex inference. Do not perform the formal full-paper reading from a preprint.
7. **Discussion step**: use the guided-reading reference to teach and check understanding before finalizing learned material. Incorporate resolved questions into substantive sections; retain only genuine unanswered content questions, respecting the user's exclusions.
8. **Consolidation step**: for learning notes, update the existing `Literature/notes/` file. For a requested full report, write to `Literature/reports/` using `_references/literature-reading-report-template.md`. Preserve existing substantive material and separate facts, examples, and user judgments.
9. **Map step, when requested**: update `maps/literature-map.md` with links under topic, method, dataset, safety task, and paper-idea sections.
10. **Zotero backlink step, when in scope**: if Zotero write automation is not available, provide a concise pasteable note linking the requested Obsidian deliverable and citekey.
11. **Feedback loop**: after consolidation, perform the reference's retrospective, validate any authorized instruction changes, and save the outcome outside the literature-note body. Do not force changes when the existing workflow already handles the feedback.

When importing through the local Zotero Connector, never write Zotero's SQLite database directly. Require the selected Zotero collection to match the intended destination, such as `每日文献阅读`, before saving.

## Daily Literature Brief

For the first local one-click version:

1. Use `_scripts/daily_literature_brief.py`.
2. Discover candidates from open scholarly metadata APIs only.
3. Do not scrape Google Scholar or CNKI.
4. For each automated daily run, use `_scripts/daily_brief_gate.py generate` to download and validate the formal Top 1 PDF, prepare intake, and write the item plus PDF attachment into Zotero collection `每日文献阅读`. Preserve prior days in that cumulative collection.
5. Prefer one high-quality paper per day, with Top 5 candidates retained.
6. Score each candidate from 0 to 5 on: 主题相关性, 近三年优先级, 期刊会议质量, 方法启发性, 综述可用性, 小论文灵感潜力.
7. For the main recommendation, attempt only a lawful formal published PDF and mark its version/source explicitly. Reject and do not retain or import arXiv, bioRxiv, medRxiv, SSRN, Research Square, or other preprint files. If the formal PDF cannot be obtained, keep the abstract-level recommendation, set `formal_fulltext_missing`, and tell the user to obtain and provide the authorized official PDF; never substitute a preprint. For other candidates, link only directly verified formal open-access PDFs.
8. Do not mark the daily delivery complete until the formal PDF exists locally and the Zotero item, `每日文献阅读` collection membership, and PDF attachment have all been verified. Download or Zotero failures remain undelivered.
9. Store both Markdown for Obsidian reading and JSON for future desktop/mobile app use.
10. Put Chinese translations below English titles and abstracts when Codex has generated them in-session.
11. Verify JIF year/value/source and JCR Q1/Q2 or CAS 1/2 with traceable sources before recommending; exclude unverified or ineligible venues from the formal Top 5. Conference rankings need traceable top-tier evidence; JIF is not applicable.
12. Do not generate a 20-minute reading guide or reading-report draft in the daily brief. Create it only after the user has read the verified formal paper and discussed it with Codex.

## Note Quality

For each paper note, prefer these sections:

- 元数据
- 一句话总结
- 研究问题
- 方法
- 数据与实验
- 主要结论
- 与我当前研究的关系
- 可引用观点
- 疑问
- 关联

When summarizing PDFs, distinguish extracted facts from inference. Do not fabricate metadata that is absent from BibTeX or the PDF.

### 笔记正文不是阅读流程记录

文献笔记和阅读报告的正文只保存研究知识、证据、判断及其边界。不得写入阅读进度、操作记录、勾选清单、待办事项、下载或 Zotero 确认过程、“待讨论/待补写/待生成”等流程占位语。工作流当前状态如确有程序需要，只能保留为 frontmatter 的单值属性；过程历史、下一步和执行待办写入 research-second-brain、运行状态文件或任务系统，不进入文献正文。

“疑问”有严格语义：只记录针对论文内容的实质性问题，并且论文正文、补充材料、公开代码或数据均没有提供足以支持答案的证据。讨论中已经回答的问题应把结论写回方法、实验、局限性等相应章节，不再保留在“疑问”；阅读进度、后续检索计划、复现计划和文献管理事项也不得放入该节。没有符合条件的未解问题时，“疑问”留空。

## Reading Report Quality

A completed report should be more detailed than the daily brief and should reflect the user's discussion with Codex. It must include:

- Basic metadata and Zotero/Obsidian links.
- English title, Chinese title, original abstract, Chinese abstract.
- One-sentence takeaway and 3-5 key claims.
- Research question, method, data/experiment, metrics, findings, limitations.
- Safety-risk task classification and relevance to the user's review.
- Reusable quotes or paraphrased citation points, clearly separated from inference.
- User discussion形成的实质性理解，以及仍无法由论文材料回答的问题。
- Links to related notes and literature map entries.

Use full reports for papers the user actually studies. Do not create long reports for every daily Top 5 candidate unless asked.
