#!/usr/bin/env python
"""Refresh a saved brief from verified venue metrics without searching or redelivering."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import daily_literature_brief as brief
import download_brief_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    vault = Path(args.vault)
    old_path = vault / "_data/daily-briefs" / f"{args.date}.json"
    data = json.loads(old_path.read_text(encoding="utf-8"))
    config = brief.load_config(vault / "_references/research-topics.yml")
    metrics = brief.load_journal_metrics(vault / "_references/journal-metrics.yml")
    selected = from_saved(data["selected"])
    top = [from_saved(item) for item in data["top_candidates"]]
    if data["topic"] != config["topic_name"]:
        raise SystemExit("Saved brief and current research topic differ; manual review is required")
    for paper in [selected, *top]:
        old_quality = paper.scores.get("期刊会议质量", 0)
        brief.apply_journal_metrics(paper, metrics)
        if not brief.verified_venue(paper):
            raise SystemExit(f"Venue metrics are not verified: {paper.source}")
        new_quality = max(old_quality, 5 if paper.journal_quartile == "Q1"
                          or paper.journal_cas_quartile.startswith("1区")
                          or paper.venue_type == "conference" else 4)
        paper.scores["期刊会议质量"] = new_quality
        paper.total_score += new_quality - old_quality
        reason = "期刊指标与分区已核验，符合正式筛查标准"
        if reason not in paper.reasons:
            paper.reasons.append(reason)
    md = brief.render_markdown(args.date, config, data["subtopic"], selected, top,
                               data.get("classic_reread"))
    refreshed = brief.render_json(args.date, config, data["subtopic"], selected, top,
                                  data.get("classic_reread"))
    brief.write_outputs(vault, args.date, selected, md, refreshed)
    pdf_report = vault / "_data/pdf-downloads" / f"{args.date}.json"
    if pdf_report.exists():
        report = json.loads(pdf_report.read_text(encoding="utf-8"))
        if report.get("doi") == selected.doi:
            download_brief_pdf.publish(args.date, report)
    print(f"refreshed={old_path}")
    print("reading_outline_removed=true")
    return 0


def from_saved(item: dict) -> brief.Paper:
    names = brief.Paper.__dataclass_fields__
    return brief.Paper(**{name: value for name, value in item.items() if name in names})


if __name__ == "__main__":
    raise SystemExit(main())
