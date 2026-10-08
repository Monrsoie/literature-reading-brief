#!/usr/bin/env python
"""Create an Obsidian reading-report draft from a daily brief JSON file."""
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
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing draft")
    args = parser.parse_args()

    vault = Path(args.vault)
    brief_path = vault / "_data" / "daily-briefs" / f"{args.date}.json"
    template_path = vault / "_references" / "literature-reading-report-template.md"
    reports_dir = vault / "Literature" / "reports"

    if not brief_path.exists():
        raise SystemExit(f"Daily brief JSON not found: {brief_path}")
    if not template_path.exists():
        raise SystemExit(f"Reading report template not found: {template_path}")

    data = json.loads(brief_path.read_text(encoding="utf-8"))
    candidates = data.get("top_candidates") or [data.get("selected")]
    paper = candidates[args.paper_index - 1]
    reports_dir.mkdir(parents=True, exist_ok=True)

    key = paper_id(paper)
    existing = find_existing_report(reports_dir, key)
    if existing and not args.overwrite:
        print(f"exists={existing}")
        return 0

    filename = safe_filename(f"{key} - 阅读报告 - {paper.get('title_zh') or paper.get('title')}", ".md")
    output_path = reports_dir / filename
    if output_path.exists() and not args.overwrite:
        print(f"exists={output_path}")
        return 0

    template = template_path.read_text(encoding="utf-8")
    output = render_report(template, paper, data, args.date)
    output_path.write_text(output, encoding="utf-8")
    print(f"created={output_path}")
    return 0


def find_existing_report(reports_dir: Path, key: str) -> Path | None:
    matches = sorted(reports_dir.glob(f"{key}*.md"))
    return matches[0] if matches else None


def render_report(template: str, paper: dict[str, Any], brief: dict[str, Any], date: str) -> str:
    title = paper.get("title", "")
    values = {
        "citekey": paper.get("citekey") or paper_id(paper),
        "title": title,
        "title_zh": paper.get("title_zh") or title,
        "year": str(paper.get("year") or ""),
        "authors": "; ".join(paper.get("authors") or []),
        "journal": paper.get("journal_name") or paper.get("source") or "",
        "journal_if": paper.get("journal_if") or "未核验",
        "journal_quartile": paper.get("journal_quartile") or "未核验",
        "doi": paper.get("doi") or "",
        "zotero_status": "pending",
        "pdf_status": "open_pdf" if paper.get("pdf_url") else "missing",
        "zotero_uri": "",
        "pdf_path": paper.get("pdf_url") or "",
        "daily_brief": f"[[{date}]]",
        "literature_note": "",
    }
    output = template
    for key, value in values.items():
        output = output.replace("{{" + key + "}}", value)

    output = output.replace("### 原文摘要\n\n", f"### 原文摘要\n\n{paper.get('abstract') or ''}\n\n")
    output = output.replace("### 中文翻译\n\n", f"### 中文翻译\n\n{paper.get('abstract_zh') or ''}\n\n")
    return output.rstrip() + "\n"


def paper_id(paper: dict[str, Any]) -> str:
    value = paper.get("doi") or paper.get("title") or "untitled"
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()[:80] or "untitled"


def safe_filename(name: str, suffix: str = ".md") -> str:
    name = re.sub(r'[<>:"/\\|?*]+', "-", name)
    name = re.sub(r"\s+", " ", name).strip()
    if name.lower().endswith(suffix.lower()):
        name = name[: -len(suffix)]
    stem = name[: max(1, 180 - len(suffix))] or "untitled"
    return stem.rstrip(" .") + suffix


if __name__ == "__main__":
    raise SystemExit(main())
