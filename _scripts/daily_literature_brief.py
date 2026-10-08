#!/usr/bin/env python
"""Create a one-paper local daily literature brief for the Obsidian Vault."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


USER_AGENT = "LiteratureBriefSkill/1.0"
ZOTERO_SQLITE = Path(os.environ.get("ZOTERO_DATA_DIR", str(Path.home() / "Zotero"))) / "zotero.sqlite"


@dataclass
class Paper:
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    source: str = ""
    journal_name: str = ""
    journal_if: str = ""
    journal_quartile: str = ""
    journal_cas_quartile: str = ""
    journal_metric_year: str = ""
    journal_if_source: str = ""
    journal_rank_source: str = ""
    venue_type: str = "journal"
    journal_metric_note: str = ""
    doi: str = ""
    url: str = ""
    pdf_url: str = ""
    abstract: str = ""
    title_zh: str = ""
    abstract_zh: str = ""
    cited_by_count: int = 0
    provider: str = ""
    subtopic: str = ""
    is_local: bool = False
    scores: dict[str, int] = field(default_factory=dict)
    total_score: int = 0
    reasons: list[str] = field(default_factory=list)
    local_status: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=str(Path(__file__).resolve().parents[1]), help="Obsidian Vault path")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Brief date, YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="Print the selected brief without writing files")
    parser.add_argument("--download-pdf", action="store_true", help="Download selected formal PDF through local ScanSci")
    args = parser.parse_args()

    vault = Path(args.vault)
    config = load_config(vault / "_references" / "research-topics.yml")
    ensure_dirs(vault)

    journal_metrics = load_journal_metrics(vault / "_references" / "journal-metrics.yml")
    local_index = load_local_bib_index(vault)
    subtopic = choose_subtopic(config, vault)
    candidates = discover_candidates(config, subtopic)
    candidates = dedupe_papers(candidates)

    for paper in candidates:
        paper.is_local = paper_matches_local(paper, local_index)
        apply_journal_metrics(paper, journal_metrics)
        score_paper(paper, config, subtopic)

    ranked = rank_candidates(candidates)
    daily_top_k = int(config.get("daily_top_k", "5"))
    top_k = ranked[:daily_top_k]
    if not top_k:
        raise SystemExit("No relevant paper with verified JIF and Q1/Q2 (or CAS 1/2) venue found. Verify venue metrics before delivery.")

    selected = choose_daily_selection(ranked, top_k)
    if not any(same_paper(selected, paper) for paper in top_k):
        top_k = [selected, *top_k[: max(0, daily_top_k - 1)]]
    classic = find_classic_reread(config, local_index, selected, subtopic)
    apply_existing_enrichment(vault, args.date, selected, top_k, config.get("topic_name", ""))
    today = args.date
    brief_md = render_markdown(today, config, subtopic, selected, top_k, classic)
    brief_json = render_json(today, config, subtopic, selected, top_k, classic)

    if args.dry_run:
        print(brief_md)
        return 0

    write_outputs(vault, today, selected, brief_md, brief_json)
    append_jsonl(vault / "_data" / "discovery-log.jsonl", brief_json)
    print(f"created={vault / 'maps' / 'daily-briefs' / (today + '.md')}")
    print(f"data={vault / '_data' / 'daily-briefs' / (today + '.json')}")
    if args.download_pdf:
        runtime = vault / 'tools/scansci-pdf-env/Scripts/python.exe'
        try:
            result = subprocess.run([str(runtime), '-X', 'utf8',
                                     str(vault / '_scripts/download_brief_pdf.py'), '--date', today],
                                    check=False)
            if result.returncode:
                print('PDF download not verified; brief remains available.')
        except OSError:
            print('ScanSci runtime unavailable; brief remains available.')
    return 0


def load_config(path: Path) -> dict[str, Any]:
    config: dict[str, Any] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not raw.startswith(" ") and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value:
                config[key] = value
                current = None
            else:
                config[key] = []
                current = key
            continue
        if current and line.startswith("- "):
            config[current].append(line[2:].strip())
    return config


def load_journal_metrics(path: Path) -> dict[str, dict[str, str]]:
    """Load source-verified venue metrics without adding a YAML dependency."""
    metrics: dict[str, dict[str, str]] = {}
    if not path.exists():
        return metrics
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line.startswith("- "):
            continue
        parts = [part.strip() for part in line[2:].split("|")]
        if len(parts) < 7 or not parts[0]:
            continue
        name = parts[0]
        metrics[normalize_journal_name(name)] = {
            "name": name,
            "if": parts[1],
            "quartile": parts[2],
            "cas_quartile": parts[3],
            "year": parts[4],
            "if_source": parts[5],
            "rank_source": parts[6],
            "note": parts[7] if len(parts) > 7 else "",
            "venue_type": parts[8] if len(parts) > 8 else "journal",
        }
    return metrics


def apply_journal_metrics(paper: Paper, journal_metrics: dict[str, dict[str, str]]) -> None:
    paper.journal_name = paper.source or "未知"
    metric = journal_metrics.get(normalize_journal_name(paper.journal_name))
    if not metric:
        paper.journal_if = ""
        paper.journal_quartile = ""
        paper.journal_metric_note = "指标未核验，不进入正式推荐。"
        return
    paper.journal_name = metric.get("name") or paper.journal_name
    paper.journal_if = metric.get("if", "")
    paper.journal_quartile = metric.get("quartile", "")
    paper.journal_cas_quartile = metric.get("cas_quartile", "")
    paper.journal_metric_year = metric.get("year", "")
    paper.journal_if_source = metric.get("if_source", "")
    paper.journal_rank_source = metric.get("rank_source", "")
    paper.venue_type = metric.get("venue_type", "journal")
    paper.journal_metric_note = metric.get("note", "")


def verified_venue(paper: Paper) -> bool:
    try:
        metric_year = int(paper.journal_metric_year)
    except ValueError:
        return False
    if metric_year < dt.date.today().year - 2:
        return False
    if not (paper.journal_if_source.startswith("https://") and paper.journal_rank_source.startswith("https://")):
        return False
    if paper.venue_type == "conference":
        return paper.journal_quartile in {"Top", "A*"} and paper.journal_if in {"", "N/A"}
    try:
        float(paper.journal_if)
    except ValueError:
        return False
    return (paper.journal_quartile in {"Q1", "Q2"}
            or paper.journal_cas_quartile.startswith(("1区", "2区")))


def normalize_journal_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", html.unescape(value).lower())


def apply_existing_enrichment(vault: Path, today: str, selected: Paper, top_k: list[Paper], topic_name: str) -> None:
    path = vault / "_data" / "daily-briefs" / f"{today}.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    if data.get("topic") != topic_name:
        return
    saved_papers = [data.get("selected", {})] + list(data.get("top_candidates", []))
    by_key = {
        (item.get("doi") or title_key(item.get("title", ""))): item
        for item in saved_papers
        if item.get("title")
    }
    for paper in [selected, *top_k]:
        item = by_key.get(paper.doi or title_key(paper.title))
        if not item:
            continue
        paper.title_zh = item.get("title_zh") or paper.title_zh
        paper.abstract_zh = item.get("abstract_zh") or paper.abstract_zh


def ensure_dirs(vault: Path) -> None:
    for rel in [
        "maps/daily-briefs",
        "_data/daily-briefs",
        "_data/papers",
        "_data",
    ]:
        (vault / rel).mkdir(parents=True, exist_ok=True)


def choose_subtopic(config: dict[str, Any], vault: Path) -> dict[str, Any]:
    subtopics = [parse_subtopic(item) for item in config.get("subtopics", [])]
    if not subtopics:
        return {"id": "general", "label": "综合主题", "keywords": config.get("core_terms", [])}

    counts = {topic["id"]: 0 for topic in subtopics}
    log_path = vault / "_data" / "discovery-log.jsonl"
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            topic_id = item.get("subtopic", {}).get("id")
            if item.get("topic") == config.get("topic_name") and topic_id in counts:
                counts[topic_id] += 1
    ordered = [(index, item) for index, item in enumerate(subtopics)]
    return sorted(ordered, key=lambda row: (counts.get(row[1]["id"], 0), row[0]))[0][1]


def parse_subtopic(value: str) -> dict[str, Any]:
    parts = value.split("|", 2)
    if len(parts) != 3:
        return {"id": value, "label": value, "keywords": []}
    return {
        "id": parts[0].strip(),
        "label": parts[1].strip(),
        "keywords": [item.strip() for item in parts[2].split(";") if item.strip()],
    }


def discover_candidates(config: dict[str, Any], subtopic: dict[str, Any]) -> list[Paper]:
    queries = build_queries(config, subtopic)
    papers: list[Paper] = []
    since = int(config.get("primary_since_year", "2023"))
    for query in queries:
        papers.extend(fetch_openalex(query, since))
        time.sleep(0.5)
        papers.extend(fetch_crossref(query, since))
        time.sleep(0.5)
    return papers


def build_queries(config: dict[str, Any], subtopic: dict[str, Any]) -> list[str]:
    queries: list[str] = []
    for template in config.get("query_templates", []):
        if "|" in template:
            topic_id, query = template.split("|", 1)
            if topic_id.strip() not in ("all", subtopic["id"]):
                continue
        else:
            query = template
        query = query.strip()
        if query and query not in queries:
            queries.append(query)
    return queries[:4]


def fetch_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_openalex(query: str, since_year: int) -> list[Paper]:
    params = {
        "search": query,
        "filter": f"from_publication_date:{since_year}-01-01,type:article",
        "per-page": "20",
    }
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    try:
        data = fetch_json(url)
    except Exception as exc:
        print(f"OpenAlex warning: {exc}", file=sys.stderr)
        return []

    papers: list[Paper] = []
    for item in data.get("results", []):
        title = normalize_space(strip_html(item.get("title") or ""))
        if not title:
            continue
        authors = [
            normalize_space(auth.get("author", {}).get("display_name", ""))
            for auth in item.get("authorships", [])[:8]
        ]
        authors = [author for author in authors if author]
        source = ""
        locations = item.get("locations") or []
        if locations:
            source = normalize_space((locations[0].get("source") or {}).get("display_name") or "")
        doi = normalize_doi(item.get("doi") or "")
        pdf_url = ""
        for loc in locations:
            pdf_url = loc.get("pdf_url") or pdf_url
        papers.append(
            Paper(
                title=title,
                authors=authors,
                year=item.get("publication_year"),
                source=source,
                doi=doi,
                url=item.get("id") or item.get("doi") or "",
                pdf_url=pdf_url,
                abstract=reconstruct_openalex_abstract(item.get("abstract_inverted_index")),
                cited_by_count=int(item.get("cited_by_count") or 0),
                provider="OpenAlex",
            )
        )
    return papers


def fetch_crossref(query: str, since_year: int) -> list[Paper]:
    params = {
        "query.bibliographic": query,
        "filter": f"from-pub-date:{since_year}-01-01,type:journal-article",
        "rows": "20",
    }
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    try:
        data = fetch_json(url)
    except Exception as exc:
        print(f"Crossref warning: {exc}", file=sys.stderr)
        return []

    papers: list[Paper] = []
    for item in data.get("message", {}).get("items", []):
        title = normalize_space(" ".join(item.get("title") or []))
        if not title:
            continue
        authors = []
        for author in item.get("author", [])[:8]:
            name = normalize_space(f"{author.get('given', '')} {author.get('family', '')}")
            if name:
                authors.append(name)
        year = crossref_year(item)
        source = normalize_space(" ".join(item.get("container-title") or []))
        papers.append(
            Paper(
                title=title,
                authors=authors,
                year=year,
                source=source,
                doi=normalize_doi(item.get("DOI") or ""),
                url=item.get("URL") or "",
                abstract=normalize_space(strip_html(item.get("abstract") or "")),
                cited_by_count=int(item.get("is-referenced-by-count") or 0),
                provider="Crossref",
            )
        )
    return papers


def reconstruct_openalex_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words: list[str] = [""] * (max(pos for positions in index.values() for pos in positions) + 1)
    for word, positions in index.items():
        for pos in positions:
            words[pos] = word
    return normalize_space(" ".join(words))


def crossref_year(item: dict[str, Any]) -> int | None:
    for key in ["published-print", "published-online", "published", "issued"]:
        parts = item.get(key, {}).get("date-parts")
        if parts and parts[0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                continue
    return None


def dedupe_papers(papers: list[Paper]) -> list[Paper]:
    seen: set[str] = set()
    output: list[Paper] = []
    for paper in papers:
        key = paper.doi or title_key(paper.title)
        if key in seen:
            continue
        seen.add(key)
        output.append(paper)
    return output


def rank_candidates(papers: list[Paper]) -> list[Paper]:
    relevant = [paper for paper in papers if paper.scores.get("主题相关性", 0) > 0 and verified_venue(paper)]
    return sorted(relevant, key=lambda p: (p.total_score, p.cited_by_count, p.year or 0), reverse=True)


def load_local_bib_index(vault: Path) -> dict[str, Any]:
    bib_files = list(vault.glob("references.bib")) + list((vault / "_references").glob("*.bib"))
    dois: set[str] = set()
    titles: dict[str, dict[str, str]] = {}
    status_by_doi: dict[str, str] = {}
    status_by_title: dict[str, str] = {}
    for bib in bib_files:
        if not bib.exists():
            continue
        text = bib.read_text(encoding="utf-8-sig", errors="ignore")
        for entry in split_bib_entries(text):
            title = bib_field(entry, "title")
            doi = normalize_doi(bib_field(entry, "doi"))
            year = bib_field(entry, "year")
            journal = bib_field(entry, "journal") or bib_field(entry, "journaltitle") or bib_field(entry, "booktitle")
            citekey = bib_citekey(entry)
            if doi:
                dois.add(doi)
                status_by_doi[doi] = "references.bib"
            if title:
                titles[title_key(title)] = {"title": clean_bib_value(title), "year": year, "source": journal, "citekey": citekey}
                status_by_title[title_key(title)] = "references.bib"
    add_zotero_index(dois, titles, status_by_doi, status_by_title)
    add_import_status_index(vault, dois, titles, status_by_doi, status_by_title)
    return {"dois": dois, "titles": titles, "status_by_doi": status_by_doi, "status_by_title": status_by_title}


def add_zotero_index(
    dois: set[str],
    titles: dict[str, dict[str, str]],
    status_by_doi: dict[str, str],
    status_by_title: dict[str, str],
) -> None:
    if not ZOTERO_SQLITE.exists():
        return
    try:
        con = sqlite3.connect(f"file:{ZOTERO_SQLITE}?mode=ro", uri=True)
    except sqlite3.Error:
        return
    try:
        rows = con.execute(
            """
            select items.key, coalesce(titleValues.value, ''), coalesce(doiValues.value, '')
            from items
            left join itemData titleData
              on titleData.itemID = items.itemID
             and titleData.fieldID = (select fieldID from fields where fieldName = 'title')
            left join itemDataValues titleValues on titleValues.valueID = titleData.valueID
            left join itemData doiData
              on doiData.itemID = items.itemID
             and doiData.fieldID = (select fieldID from fields where fieldName = 'DOI')
            left join itemDataValues doiValues on doiValues.valueID = doiData.valueID
            where items.itemID not in (select itemID from deletedItems)
            """
        ).fetchall()
    except sqlite3.Error:
        return
    finally:
        con.close()
    for key, title, doi in rows:
        doi = normalize_doi(doi or "")
        title = normalize_space(title or "")
        if doi:
            dois.add(doi)
            status_by_doi[doi] = f"Zotero:{key}"
        if title:
            titles.setdefault(title_key(title), {"title": title, "year": "", "source": "", "citekey": key})
            status_by_title[title_key(title)] = f"Zotero:{key}"


def add_import_status_index(
    vault: Path,
    dois: set[str],
    titles: dict[str, dict[str, str]],
    status_by_doi: dict[str, str],
    status_by_title: dict[str, str],
) -> None:
    imports_dir = vault / "_data" / "zotero-imports"
    if not imports_dir.exists():
        return
    for path in imports_dir.glob("*.json"):
        try:
            status = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if status.get("zotero_status") != "linked":
            continue
        doi = normalize_doi(status.get("doi") or "")
        title = normalize_space(status.get("title") or "")
        source = f"Zotero linked:{status.get('zotero_item_key') or path.stem}"
        if doi:
            dois.add(doi)
            status_by_doi.setdefault(doi, source)
        if title:
            key = title_key(title)
            titles.setdefault(key, {"title": title, "year": "", "source": "", "citekey": status.get("paper_key", "")})
            status_by_title.setdefault(key, source)


def split_bib_entries(text: str) -> list[str]:
    chunks = re.split(r"\n(?=@\w+\s*\{)", text)
    return [chunk.strip() for chunk in chunks if chunk.strip().startswith("@")]


def bib_citekey(entry: str) -> str:
    match = re.match(r"@\w+\s*\{\s*([^,]+),", entry)
    return match.group(1).strip() if match else ""


def bib_field(entry: str, field_name: str) -> str:
    match = re.search(rf"^\s*{re.escape(field_name)}\s*=\s*(.+?),?\s*$", entry, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return ""
    return clean_bib_value(match.group(1))


def clean_bib_value(value: str) -> str:
    value = value.strip().rstrip(",").strip()
    if len(value) >= 2 and value[0] in "{\"" and value[-1] in "}\"":
        value = value[1:-1]
    value = value.replace("{{", "{").replace("}}", "}")
    return normalize_space(value)


def paper_matches_local(paper: Paper, local_index: dict[str, Any]) -> bool:
    if paper.doi and paper.doi in local_index["dois"]:
        paper.local_status = local_index.get("status_by_doi", {}).get(paper.doi, "local")
        return True
    title = title_key(paper.title)
    if title in local_index["titles"]:
        paper.local_status = local_index.get("status_by_title", {}).get(title, "local")
        return True
    paper.local_status = ""
    return False


def choose_daily_selection(ranked: list[Paper], top_k: list[Paper]) -> Paper:
    for paper in top_k:
        if not paper.is_local:
            return paper
    for paper in ranked:
        if not paper.is_local:
            return paper
    return top_k[0]


def same_paper(left: Paper, right: Paper) -> bool:
    if left.doi and right.doi:
        return left.doi == right.doi
    return title_key(left.title) == title_key(right.title)


def score_paper(paper: Paper, config: dict[str, Any], subtopic: dict[str, Any]) -> None:
    text = f"{paper.title} {paper.abstract} {paper.source}".lower()
    exclude_hits = keyword_hits(text, config.get("exclude_terms", []))
    if exclude_hits:
        paper.reasons.append("命中排除词：" + ", ".join(exclude_hits[:3]))

    sub_hits = keyword_hits(text, subtopic.get("keywords", []))
    core_hits = keyword_hits(text, config.get("core_terms", []))
    topic_hits = list(dict.fromkeys([*sub_hits, *core_hits]))
    source_quality = source_quality_score(paper.source, config.get("quality_sources", []))
    if verified_venue(paper):
        source_quality = max(source_quality, 5 if paper.journal_quartile == "Q1"
                             or paper.journal_cas_quartile.startswith("1区")
                             or paper.venue_type == "conference" else 4)
    recency = recency_score(paper.year)

    related = clamp_score(len(sub_hits) + len(core_hits) // 2)
    method = clamp_score(len(keyword_hits(text, config.get("method_terms", []))))
    review = clamp_score(related + (1 if paper.abstract else 0) + (1 if paper.cited_by_count >= 20 else 0))
    idea = clamp_score(len(keyword_hits(text, config.get("idea_terms", []))))

    if exclude_hits:
        related = max(0, related - 2)
        method = max(0, method - 1)
    if not topic_hits:
        related = 0
        review = max(0, review - 3)
        idea = 0

    paper.scores = {
        "主题相关性": related,
        "近三年优先级": recency,
        "期刊会议质量": source_quality,
        "方法启发性": method,
        "综述可用性": review,
        "小论文灵感潜力": idea,
    }
    paper.total_score = sum(paper.scores.values())
    if not topic_hits:
        paper.total_score = min(paper.total_score, 8)
    if exclude_hits:
        paper.total_score = min(paper.total_score, 6)
    paper.subtopic = subtopic["id"]
    if sub_hits:
        paper.reasons.append("匹配子主题关键词：" + ", ".join(sub_hits[:5]))
    if topic_hits:
        paper.reasons.append("匹配当前研究主题关键词：" + ", ".join(topic_hits[:5]))
    else:
        paper.reasons.append("当前研究主题相关性不足，已降权")
    if source_quality >= 5:
        paper.reasons.append("来源位于当前配置的高质量期刊/会议候选名单")
    if paper.year and paper.year >= 2023:
        paper.reasons.append("符合近三年优先策略")
    if paper.is_local:
        paper.reasons.append(f"本地已存在（{paper.local_status or 'local'}），默认每日流程会跳过新增导入")
    if paper.pdf_url:
        paper.reasons.append("发现开放 PDF 链接")
    else:
        paper.reasons.append("未发现开放 PDF，后续可能需要手动补全文")


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    hits: list[str] = []
    for keyword in keywords:
        if not keyword:
            continue
        term = keyword.lower()
        pattern = re.escape(term).replace(r"\ ", r"\s+")
        if re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text):
            hits.append(keyword)
    return hits


def source_quality_score(source: str, quality_sources: list[str]) -> int:
    lower = source.lower()
    if not lower:
        return 2
    for item in quality_sources:
        item_lower = item.lower()
        if item_lower in lower:
            return 5
    return 2


def recency_score(year: int | None) -> int:
    current = dt.date.today().year
    if not year:
        return 2
    if year >= current - 1:
        return 5
    if year >= current - 3:
        return 4
    if year >= 2023:
        return 3
    return 1


def clamp_score(value: int) -> int:
    return max(0, min(5, value))


def find_classic_reread(config: dict[str, Any], local_index: dict[str, Any], selected: Paper, subtopic: dict[str, Any]) -> dict[str, str] | None:
    classic_before = int(config.get("classic_before_year", "2023"))
    keywords = subtopic.get("keywords", [])
    candidates = []
    for item in local_index["titles"].values():
        try:
            year = int(item.get("year") or 0)
        except ValueError:
            year = 0
        if not year or year >= classic_before:
            continue
        text = f"{item.get('title', '')} {item.get('source', '')}".lower()
        hits = keyword_hits(text, keywords)
        if hits:
            candidates.append((len(hits), year, item, hits))
    if not candidates:
        return None
    _, _, item, hits = sorted(candidates, key=lambda row: (row[0], row[1]), reverse=True)[0]
    return {
        "title": item.get("title", ""),
        "year": item.get("year", ""),
        "source": item.get("source", ""),
        "citekey": item.get("citekey", ""),
        "reason": "与今日主题强相关：" + ", ".join(hits[:5]),
    }


def render_markdown(today: str, config: dict[str, Any], subtopic: dict[str, Any], selected: Paper, top_k: list[Paper], classic: dict[str, str] | None) -> str:
    lines = [
        f"# 每日文献简报 {today}",
        "",
        f"- 今日子主题：{subtopic['label']} (`{subtopic['id']}`)",
        f"- 检索主题：{config.get('topic_name', '')}",
        "",
        "## 今日推荐",
        "",
        f"### {selected.title}",
        f"**中文译名：** {selected.title_zh or '待 Codex 实时补译'}",
        "",
        f"- 作者：{format_authors(selected.authors)}",
        f"- 年份：{selected.year or '未知'}",
        f"- 来源：{selected.source or '未知'}",
        f"- IF 值：{selected.journal_if}（{selected.journal_metric_year} JIF）" if selected.venue_type == "journal" else "- IF 值：不适用（顶级会议）",
        f"- 期刊：{selected.journal_name or selected.source or '未知'}",
        f"- JCR 分区：{selected.journal_quartile or '不适用'}",
        f"- 中科院分区：{selected.journal_cas_quartile or '未采用此项作筛查依据'}",
        f"- 指标来源：[IF/JIF](<{selected.journal_if_source}>)；[分区/级别](<{selected.journal_rank_source}>)",
        f"- DOI：{selected.doi or '无'}",
        f"- URL：{selected.url or '无'}",
        f"- PDF 状态：{'发现开放 PDF：' + selected.pdf_url if selected.pdf_url else '未获取 PDF'}",
        f"- 本地状态：{selected.local_status if selected.is_local else '未发现'}",
        f"- 数据源：{selected.provider}",
        f"- 期刊指标备注：{selected.journal_metric_note or '无'}",
        f"- 引用数参考：{selected.cited_by_count}",
        "",
        "## 评分",
        "",
    ]
    for name, score in selected.scores.items():
        lines.append(f"- {name}：{score}/5")
    lines.extend([
        f"- 总分：{selected.total_score}/30",
        "",
        "## 为什么选它",
        "",
    ])
    lines.extend([f"- {reason}" for reason in selected.reasons] or ["- 暂无自动理由"])
    lines.extend([
        "",
        "## 摘要",
        "",
        selected.abstract or "当前数据源未提供摘要。建议后续通过 DOI、出版社页面或 Zotero 补全文。",
        "",
        "## 摘要中文翻译",
        "",
        selected.abstract_zh or "待 Codex 实时补译。",
        "",
        "## Top 5 候选",
        "",
    ])
    for index, paper in enumerate(top_k, start=1):
        lines.extend([
            f"### {index}. {paper.title}",
            f"- 中文译名：{paper.title_zh or '待 Codex 实时补译'}",
            f"- 分数：{paper.total_score}/30",
            f"- 年份/来源：{paper.year or '未知'} / {paper.source or '未知'}",
            f"- IF/期刊/JCR/中科院：{paper.journal_if or '不适用'}（{paper.journal_metric_year}） / {paper.journal_name or paper.source or '未知'} / {paper.journal_quartile or '不适用'} / {paper.journal_cas_quartile or '未采用'}",
            f"- 核验来源：[IF/JIF](<{paper.journal_if_source}>)；[分区/级别](<{paper.journal_rank_source}>)",
            f"- 本地状态：{paper.local_status if paper.is_local else '未发现'}",
            f"- PDF：{'[开放 PDF](<' + paper.pdf_url + '>)' if paper.pdf_url else '未发现开放 PDF 链接'}",
            f"- 未选中原因：{'今日推荐' if same_paper(paper, selected) else explain_not_selected(paper, selected)}",
            "",
        ])
    lines.extend(["## 经典重读提醒", ""])
    if classic:
        lines.extend([
            f"- {classic.get('title')} ({classic.get('year')})",
            f"- 来源：{classic.get('source') or '未知'}",
            f"- Citekey：`{classic.get('citekey') or '未知'}`",
            f"- 提醒原因：{classic.get('reason')}",
        ])
    else:
        lines.append("- 今日主题下没有匹配到强相关经典重读提醒。")
    lines.append("")
    return "\n".join(lines)


def explain_not_selected(paper: Paper, selected: Paper) -> str:
    if paper.total_score < selected.total_score:
        return "综合评分低于今日推荐"
    if not paper.pdf_url and selected.pdf_url:
        return "PDF 可获得性弱于今日推荐"
    if paper.is_local and not selected.is_local:
        return "本地已有，今日优先补充新候选"
    return "排序略低，保留为候选"


def render_json(today: str, config: dict[str, Any], subtopic: dict[str, Any], selected: Paper, top_k: list[Paper], classic: dict[str, str] | None) -> dict[str, Any]:
    return {
        "date": today,
        "topic": config.get("topic_name", ""),
        "subtopic": subtopic,
        "selected": paper_to_dict(selected),
        "top_candidates": [paper_to_dict(paper) for paper in top_k],
        "classic_reread": classic,
    }


def paper_to_dict(paper: Paper) -> dict[str, Any]:
    return {
        "title": paper.title,
        "title_zh": paper.title_zh,
        "authors": paper.authors,
        "year": paper.year,
        "source": paper.source,
        "journal_name": paper.journal_name,
        "journal_if": paper.journal_if,
        "journal_quartile": paper.journal_quartile,
        "journal_cas_quartile": paper.journal_cas_quartile,
        "journal_metric_year": paper.journal_metric_year,
        "journal_if_source": paper.journal_if_source,
        "journal_rank_source": paper.journal_rank_source,
        "venue_type": paper.venue_type,
        "journal_metric_note": paper.journal_metric_note,
        "doi": paper.doi,
        "url": paper.url,
        "pdf_url": paper.pdf_url,
        "abstract": paper.abstract,
        "abstract_zh": paper.abstract_zh,
        "cited_by_count": paper.cited_by_count,
        "provider": paper.provider,
        "subtopic": paper.subtopic,
        "is_local": paper.is_local,
        "local_status": paper.local_status,
        "scores": paper.scores,
        "total_score": paper.total_score,
        "reasons": paper.reasons,
    }


def write_outputs(vault: Path, today: str, selected: Paper, markdown: str, data: dict[str, Any]) -> None:
    md_path = vault / "maps" / "daily-briefs" / f"{today}.md"
    json_path = vault / "_data" / "daily-briefs" / f"{today}.json"
    paper_path = vault / "_data" / "papers" / f"{paper_id(selected)}.json"
    md_path.write_text(markdown, encoding="utf-8")
    json_text = json.dumps(data, ensure_ascii=False, indent=2)
    json_path.write_text(json_text + "\n", encoding="utf-8")
    paper_path.write_text(json.dumps(data["selected"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def paper_id(paper: Paper) -> str:
    base = paper.doi or paper.title
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def format_authors(authors: list[str]) -> str:
    if not authors:
        return "未知"
    if len(authors) <= 4:
        return "; ".join(authors)
    return "; ".join(authors[:4]) + " 等"


def normalize_doi(value: str) -> str:
    value = value.strip().lower()
    value = value.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    return value


def title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", strip_html(title).lower())


def strip_html(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", value))


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


if __name__ == "__main__":
    raise SystemExit(main())
