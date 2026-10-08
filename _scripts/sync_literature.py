#!/usr/bin/env python
"""Generate missing Obsidian literature notes from a Better BibTeX .bib file."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

FIELD_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*(.+?),?\s*$")
ENTRY_RE = re.compile(r"@\w+\s*\{\s*([^,]+),", re.IGNORECASE)


def parse_bib(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig")
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    brace_depth = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        start = ENTRY_RE.match(line)
        if start:
            if current:
                entries.append(current)
            current = {"citekey": start.group(1).strip()}
            brace_depth = line.count("{") - line.count("}")
            continue

        if current is None:
            continue

        brace_depth += line.count("{") - line.count("}")
        match = FIELD_RE.match(line)
        if match:
            key = match.group(1).lower()
            value = clean_value(match.group(2))
            current[key] = value

        if brace_depth <= 0:
            entries.append(current)
            current = None

    if current:
        entries.append(current)
    return entries


def clean_value(value: str) -> str:
    value = value.strip().rstrip(",").strip()
    if len(value) >= 2 and value[0] == "{" and value[-1] == "}":
        value = value[1:-1]
    elif len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]
    value = value.replace("{{", "{").replace("}}", "}")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def safe_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]+', "-", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] or "untitled"


def render_note(entry: dict[str, str], template: str) -> str:
    authors = entry.get("author", "")
    source = entry.get("journaltitle") or entry.get("journal") or entry.get("booktitle") or entry.get("publisher", "")
    values = {
        "citekey": entry.get("citekey", ""),
        "title": entry.get("title", ""),
        "year": entry.get("year", ""),
        "authors": authors,
        "source": source,
        "doi": entry.get("doi", ""),
        "zotero_uri": entry.get("uri", ""),
        "pdf_path": "",
    }
    output = template
    for key, value in values.items():
        output = output.replace("{{" + key + "}}", value)
    return output.rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=str(Path(__file__).resolve().parents[1]), help="Obsidian Vault path")
    parser.add_argument("--bib", default=None, help="Path to references.bib")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without writing notes")
    args = parser.parse_args()

    vault = Path(args.vault)
    bib = Path(args.bib) if args.bib else vault / "references.bib"
    notes_dir = vault / "Literature" / "notes"
    template_path = vault / "_references" / "literature-note-template.md"

    if not bib.exists():
        raise SystemExit(f"BibTeX file not found: {bib}")
    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")

    notes_dir.mkdir(parents=True, exist_ok=True)
    template = template_path.read_text(encoding="utf-8")
    entries = parse_bib(bib)

    created = 0
    skipped = 0
    for entry in entries:
        citekey = entry.get("citekey", "").strip()
        if not citekey:
            skipped += 1
            continue
        title = entry.get("title", "untitled")
        filename = safe_filename(f"{citekey} - {title}.md")
        note_path = notes_dir / filename
        if note_path.exists():
            skipped += 1
            continue
        if args.dry_run:
            print(f"CREATE {note_path}")
        else:
            note_path.write_text(render_note(entry, template), encoding="utf-8")
        created += 1

    print(f"entries={len(entries)} created={created} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
