#!/usr/bin/env python
"""Prepare a selected daily-brief paper for Zotero import and Obsidian study."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=str(Path(__file__).resolve().parents[1]), help="Obsidian Vault path")
    parser.add_argument("--date", required=True, help="Daily brief date, YYYY-MM-DD")
    parser.add_argument("--paper-index", type=int, default=1, help="1-based Top candidate index")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite generated import/note files")
    parser.add_argument("--skip-pdf", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--pdf-path", default="", help="Use a verified formal-version PDF")
    args = parser.parse_args()

    vault = Path(args.vault)
    brief_path = vault / "_data" / "daily-briefs" / f"{args.date}.json"
    if not brief_path.exists():
        raise SystemExit(f"Daily brief JSON not found: {brief_path}")

    data = json.loads(brief_path.read_text(encoding="utf-8"))
    candidates = data.get("top_candidates") or [data.get("selected")]
    paper = candidates[args.paper_index - 1]

    key = paper_key(paper)
    imports_dir = vault / "_data" / "zotero-imports"
    notes_dir = vault / "Literature" / "notes"
    imports_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)

    bib_path = imports_dir / f"{args.date}-{key}.bib"
    ris_path = imports_dir / f"{args.date}-{key}.ris"
    status_path = imports_dir / f"{args.date}-{key}.json"
    note_path = notes_dir / safe_filename(f"{key} - {paper.get('title_zh') or paper.get('title')}")

    write_text_once(bib_path, render_bibtex(paper, key), args.overwrite)
    write_text_once(ris_path, render_ris(paper), args.overwrite)

    selected_pdf = Path(args.pdf_path).resolve() if args.pdf_path else None
    if selected_pdf:
        if not selected_pdf.is_file():
            raise SystemExit(f"PDF not found: {selected_pdf}")
        import download_brief_pdf
        verification = download_brief_pdf.validate_pdf(selected_pdf, paper)
        if not verification["identity_match"] or verification["pages"] < 1:
            raise SystemExit("Supplied PDF does not match the selected paper title")
        pdf_status = "local_pdf_verified"
    else:
        pdf_status = "missing"
    if not selected_pdf:
        pdf_status = "formal_fulltext_missing"

    final_pdf = selected_pdf

    report_link = find_report_link(vault, key)
    note_text = render_note(paper, key, final_pdf, args.date, report_link, pdf_status)
    write_text_once(note_path, note_text, args.overwrite)

    status = {
        "date": args.date,
        "paper_index": args.paper_index,
        "paper_key": key,
        "title": paper.get("title"),
        "title_zh": paper.get("title_zh"),
        "doi": paper.get("doi"),
        "zotero_import_bib": str(bib_path),
        "zotero_import_ris": str(ris_path),
        "pdf_path": str(final_pdf) if final_pdf else "",
        "pdf_status": pdf_status,
        "obsidian_note": str(note_path),
        "reading_report": report_link,
        "zotero_status": "manual_import_ready",
    }
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"bib={bib_path}")
    print(f"ris={ris_path}")
    print(f"pdf={final_pdf or 'not_downloaded'}")
    print(f"note={note_path}")
    print(f"status={status_path}")
    return 0


def write_text_once(path: Path, text: str, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        return
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def render_bibtex(paper: dict[str, Any], key: str) -> str:
    fields = {
        "title": paper.get("title", ""),
        "author": " and ".join(paper.get("authors") or []),
        "year": str(paper.get("year") or ""),
        "journal": paper.get("journal_name") or paper.get("source") or "",
        "doi": paper.get("doi") or "",
        "url": paper.get("url") or "",
        "abstract": paper.get("abstract") or "",
        "note": "Generated from Obsidian daily literature brief for manual Zotero import.",
    }
    lines = [f"@article{{{key},"]
    for name, value in fields.items():
        if value:
            lines.append(f"  {name} = {{{bib_escape(value)}}},")
    lines.append("}")
    return "\n".join(lines)


def render_ris(paper: dict[str, Any]) -> str:
    lines = ["TY  - JOUR"]
    for author in paper.get("authors") or []:
        lines.append(f"AU  - {author}")
    append_ris(lines, "TI", paper.get("title"))
    append_ris(lines, "T2", paper.get("journal_name") or paper.get("source"))
    append_ris(lines, "PY", paper.get("year"))
    append_ris(lines, "DO", paper.get("doi"))
    append_ris(lines, "UR", paper.get("url"))
    append_ris(lines, "AB", paper.get("abstract"))
    lines.append("ER  -")
    return "\n".join(lines)


def append_ris(lines: list[str], tag: str, value: Any) -> None:
    if value:
        lines.append(f"{tag}  - {value}")


def render_note(
    paper: dict[str, Any],
    key: str,
    pdf_path: Path | None,
    date: str,
    report_link: str,
    pdf_status: str,
) -> str:
    authors = "; ".join(paper.get("authors") or [])
    title = paper.get("title") or ""
    title_zh = paper.get("title_zh") or title
    source = paper.get("journal_name") or paper.get("source") or ""
    pdf_value = str(pdf_path) if pdf_path else "未取得正式发表版全文"
    abstract_zh = paper.get("abstract_zh") or ""
    subtopic = paper.get("subtopic") or ""
    topics_yaml = f"topics:\n  - {subtopic}" if subtopic else "topics: []"
    topic_link = f"[[{subtopic}]]" if subtopic else ""
    report_value = report_link or ""
    return f"""---
type: literature-note
citekey: "{key}"
title: "{yaml_escape(title)}"
title_zh: "{yaml_escape(title_zh)}"
year: "{paper.get('year') or ''}"
authors: "{yaml_escape(authors)}"
source: "{yaml_escape(source)}"
doi: "{paper.get('doi') or ''}"
zotero_status: manual_import_ready
pdf_status: {pdf_status}
brief_status: selected
reading_status: to_read
report_status: not_started
{topics_yaml}
tags:
  - literature
  - daily-brief
status: to_read
---

# {title_zh}

> Original title: {title}

## 元数据
- Citekey: `{key}`
- Authors: {authors}
- Year: {paper.get('year') or '未知'}
- Source: {source or '未知'}
- IF: {paper.get('journal_if') or '未核验'}（{paper.get('journal_metric_year') or '年份未核验'}）
- JCR Quartile: {paper.get('journal_quartile') or '未核验'}
- CAS Quartile: {paper.get('journal_cas_quartile') or '未采用'}
- DOI: {paper.get('doi') or '无'}
- PDF: {pdf_value}
- 每日简报：[[{date}]]
- 阅读报告：{report_value}

## 一句话总结

## 摘要中文翻译
{abstract_zh}

## 研究问题

## 方法

## 数据与实验

## 主要结论

## 与我当前研究的关系

## 可引用观点

## 疑问

## 关联
- 主题：{topic_link}
- 方法：
- 数据集：
- 安全风险任务：
- 每日简报：[[{date}]]
- 阅读报告：{report_value}
- 相关文献：
"""


def find_report_link(vault: Path, key: str) -> str:
    reports_dir = vault / "Literature" / "reports"
    if not reports_dir.exists():
        return ""
    for path in reports_dir.glob(f"{key}*.md"):
        return f"[[{path.stem}]]"
    return ""


def paper_key(paper: dict[str, Any]) -> str:
    value = paper.get("citekey") or paper.get("doi") or paper.get("title") or "untitled"
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()[:80] or "untitled"


def safe_filename(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]+', "-", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:180] + ".md"


def bib_escape(value: str) -> str:
    return str(value).replace("{", "\\{").replace("}", "\\}")


def yaml_escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


if __name__ == "__main__":
    raise SystemExit(main())
