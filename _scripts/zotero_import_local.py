#!/usr/bin/env python
"""Import a prepared paper into a Zotero collection via the local Connector API."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


CONNECTOR = "http://127.0.0.1:23119"
EXPECTED_COLLECTION = "每日文献阅读"
CONNECTOR_PING = CONNECTOR + "/connector/ping"
ZOTERO_EXE = Path(r"C:\Program Files\Zotero\zotero.exe")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=str(Path(__file__).resolve().parents[1]), help="Obsidian Vault path")
    parser.add_argument("--date", required=True, help="Daily brief date, YYYY-MM-DD")
    parser.add_argument("--paper-key", default="", help="Prepared paper key; defaults to selected brief paper")
    parser.add_argument("--expected-collection", default=EXPECTED_COLLECTION, help="Required selected Zotero collection")
    parser.add_argument("--target-collection-name", default="", help="Collection name to target even if not selected")
    parser.add_argument("--skip-attachment", action="store_true", help="Do not upload the local PDF attachment")
    args = parser.parse_args()
    ensure_zotero_running()

    vault = Path(args.vault)
    status_path = find_status_path(vault, args.date, args.paper_key)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    brief = load_brief(vault, args.date, status["paper_index"])
    paper = brief["paper"]

    selected = connector_post("/connector/getSelectedCollection", {})
    target = find_target_collection(selected, args.target_collection_name or args.expected_collection)
    if not target:
        raise SystemExit(f"Zotero collection not found: {args.target_collection_name or args.expected_collection!r}")
    target["key"] = find_local_collection_key(target["name"])
    if not args.target_collection_name and selected.get("name") != args.expected_collection:
        raise SystemExit(
            f"Selected Zotero collection is {selected.get('name')!r}, expected {args.expected_collection!r}."
        )

    doi = normalize_doi(paper.get("doi") or status.get("doi") or "")
    existing_item = find_zotero_item_by_doi(doi) if doi else None
    attachment_status = "missing"
    if existing_item:
        imported_key = existing_item["key"]
        imported = False
        if target_collection_key(target) not in existing_item.get("data", {}).get("collections", []):
            ensure_collection_membership(existing_item, target_collection_key(target))
        local_pdf = Path(status["pdf_path"]) if status.get("pdf_path") else None
        if local_pdf and local_pdf.exists() and item_has_pdf_attachment(imported_key, local_pdf):
            attachment_status = "attached_existing"
        elif not args.skip_attachment and local_pdf and local_pdf.exists():
            attach_pdf_to_existing(imported_key, local_pdf, paper)
            attachment_status = "attached" if wait_for_pdf_attachment(imported_key, local_pdf) else "attachment_unverified"
        else:
            attachment_status = "missing_on_existing_item"
    else:
        session_id = f"codex-{args.date}-{status['paper_key']}-{int(time.time())}"
        item_id = status["paper_key"]
        item = zotero_item_from_paper(paper, item_id)
        connector_post("/connector/saveItems", {"sessionID": session_id, "items": [item]})
        if selected.get("name") != target.get("name"):
            connector_post("/connector/updateSession", {"sessionID": session_id, "target": target["id"]})
        imported_key = wait_for_item_key(doi)
        if not imported_key:
            raise SystemExit("Connector saved the item, but Zotero Local API could not verify its item key")
        imported = True

        if not args.skip_attachment and status.get("pdf_path") and Path(status["pdf_path"]).exists():
            save_attachment(session_id, item_id, Path(status["pdf_path"]), paper)
            attachment_status = ("attached" if wait_for_pdf_attachment(imported_key, Path(status["pdf_path"]))
                                 else "attachment_unverified")

    attachment_complete = attachment_status in {"attached", "attached_existing"}
    status.update(
        {
            "zotero_status": "linked" if attachment_complete else "attachment_pending",
            "zotero_collection": target.get("name"),
            "zotero_collection_id": target.get("id"),
            "zotero_collection_key": target_collection_key(target),
            "zotero_item_key": imported_key,
            "zotero_item_uri": f"zotero://select/library/items/{imported_key}" if imported_key else "",
            "zotero_imported_now": imported or bool(status.get("zotero_imported_now")),
            "zotero_attachment_status": attachment_status,
        }
    )
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    update_obsidian_note(Path(status["obsidian_note"]), status)
    print(f"status={status_path}")
    print(f"zotero_item_key={imported_key}")
    print(f"zotero_collection={target.get('name')}")
    print(f"imported_now={imported}")
    return 0 if attachment_complete or args.skip_attachment else 1


def find_target_collection(selected: dict[str, Any], collection_name: str) -> dict[str, Any] | None:
    if selected.get("name") == collection_name:
        return {"id": f"C{selected.get('id')}", "name": selected.get("name")}
    for target in selected.get("targets", []):
        if target.get("name") == collection_name and str(target.get("id", "")).startswith("C"):
            return target
    return None


def find_status_path(vault: Path, date: str, paper_key: str) -> Path:
    imports_dir = vault / "_data" / "zotero-imports"
    if paper_key:
        path = imports_dir / f"{date}-{paper_key}.json"
        if path.exists():
            return path
        raise SystemExit(f"Intake status JSON not found: {path}")
    matches = sorted(imports_dir.glob(f"{date}-*.json"))
    if not matches:
        raise SystemExit(f"No intake status JSON found for {date}")
    if len(matches) > 1:
        raise SystemExit(f"Multiple intake status files found for {date}; pass --paper-key.")
    return matches[0]


def load_brief(vault: Path, date: str, paper_index: int) -> dict[str, Any]:
    path = vault / "_data" / "daily-briefs" / f"{date}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    candidates = data.get("top_candidates") or [data.get("selected")]
    return {"brief": data, "paper": candidates[paper_index - 1]}


def connector_post(endpoint: str, payload: dict[str, Any]) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        CONNECTOR + endpoint,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Zotero-Allowed-Request": "true",
            "X-Zotero-Connector-API-Version": "3",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Zotero Connector {endpoint} failed: HTTP {exc.code}: {body}") from exc


def ensure_zotero_running() -> None:
    if connector_available():
        return
    if not ZOTERO_EXE.exists():
        raise SystemExit(f"Zotero executable not found: {ZOTERO_EXE}")
    subprocess.Popen([str(ZOTERO_EXE)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    deadline = time.time() + 45
    while time.time() < deadline:
        if connector_available():
            return
        time.sleep(1)
    raise SystemExit("Timed out waiting for Zotero Connector at 127.0.0.1:23119.")


def connector_available() -> bool:
    try:
        with urllib.request.urlopen(CONNECTOR_PING, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def save_attachment(session_id: str, parent_item_id: str, pdf_path: Path, paper: dict[str, Any]) -> None:
    metadata = {
        "sessionID": session_id,
        "parentItemID": parent_item_id,
        "title": "Full Text PDF",
        "url": str(pdf_path),
    }
    req = urllib.request.Request(
        CONNECTOR + "/connector/saveAttachment",
        data=pdf_path.read_bytes(),
        headers={
            "Content-Type": "application/pdf",
            "Content-Length": str(pdf_path.stat().st_size),
            "X-Metadata": json.dumps(metadata, ensure_ascii=True),
            "Zotero-Allowed-Request": "true",
            "X-Zotero-Connector-API-Version": "3",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Zotero PDF attachment failed: HTTP {exc.code}: {body}") from exc


def zotero_item_from_paper(paper: dict[str, Any], item_id: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "itemType": "journalArticle",
        "title": paper.get("title") or "",
        "creators": [creator_from_name(name) for name in paper.get("authors") or []],
        "date": str(paper.get("year") or ""),
        "publicationTitle": paper.get("journal_name") or paper.get("source") or "",
        "DOI": paper.get("doi") or "",
        "url": paper.get("url") or "",
        "abstractNote": paper.get("abstract") or "",
        "language": "en",
        "tags": [
            {"tag": "每日文献阅读"},
            {"tag": "Codex导入"},
        ],
        "notes": [
            {
                "note": (
                    "<p>由 Codex 每日文献工作流导入。</p>"
                    f"<p>中文题名：{html_escape(paper.get('title_zh') or '')}</p>"
                    "<p>Obsidian 中已有对应文献笔记；阅读报告将在讨论后形成。</p>"
                )
            }
        ],
    }


def creator_from_name(name: str) -> dict[str, str]:
    parts = name.strip().split()
    if len(parts) <= 1:
        return {"lastName": name.strip(), "creatorType": "author"}
    return {"firstName": " ".join(parts[:-1]), "lastName": parts[-1], "creatorType": "author"}


def find_zotero_item_by_doi(doi: str) -> dict[str, Any] | None:
    if not doi:
        return None
    url = CONNECTOR + "/api/users/0/items?itemType=journalArticle&q=" + urllib.parse.quote(doi) + "&qmode=everything&limit=100"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            items = json.load(response)
    except urllib.error.URLError as exc:
        raise SystemExit(f"Zotero Local API DOI lookup failed: {exc}") from exc
    return next((item for item in items
                 if normalize_doi(item.get("data", {}).get("DOI", "")) == doi), None)


def wait_for_item_key(doi: str) -> str:
    for _ in range(20):
        item = find_zotero_item_by_doi(doi)
        if item:
            return item["key"]
        time.sleep(0.5)
    return ""


def target_collection_key(target: dict[str, Any]) -> str:
    key = str(target.get("key") or "")
    if not key:
        raise SystemExit("Zotero Local API collection key is missing")
    return key


def find_local_collection_key(collection_name: str) -> str:
    matches: list[dict[str, Any]] = []
    start = 0
    while True:
        url = CONNECTOR + f"/api/users/0/collections?limit=100&start={start}"
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                batch = json.load(response)
        except urllib.error.URLError as exc:
            raise SystemExit(f"Zotero Local API collection lookup failed: {exc}") from exc
        matches.extend(entry for entry in batch if entry.get("data", {}).get("name") == collection_name)
        if len(batch) < 100:
            break
        start += len(batch)
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one Zotero collection named {collection_name!r}; found {len(matches)}")
    key = str(matches[0].get("key") or "")
    if not key:
        raise SystemExit(f"Zotero collection {collection_name!r} has no Local API key")
    return key


def ensure_collection_membership(item: dict[str, Any], collection_key: str) -> None:
    daily, headers = local_write_context()
    collections = list(item.get("data", {}).get("collections", []))
    daily.replace_membership(item, [*collections, collection_key], headers)


def local_write_context():
    import zotero_daily_collection as daily
    _, server_headers = daily.request("/")
    server_id = next((value for key, value in server_headers.items()
                      if key.lower() == "zotero-server-id"), "")
    if not server_id:
        raise SystemExit("Zotero Local API server ID is missing")
    return daily, {"Zotero-Server-ID": server_id, "Zotero-API-Key": daily.authorize(server_id)}


def attach_pdf_to_existing(item_key: str, pdf_path: Path, paper: dict[str, Any]) -> None:
    """Create a stored child attachment and upload its file through Zotero 10 Local API."""
    daily, headers = local_write_context()
    template, _ = daily.request("/items/new?itemType=attachment&linkMode=imported_file", headers=headers)
    template.update({
        "parentItem": item_key,
        "linkMode": "imported_file",
        "title": "Full Text PDF",
        "url": "",
        "contentType": "application/pdf",
        "filename": pdf_path.name,
    })
    create_headers = {**headers, "Zotero-Write-Token": str(uuid.uuid4())}
    created, _ = daily.request("/users/0/items", "POST", [template], create_headers)
    successful = created.get("successful", {}) if isinstance(created, dict) else {}
    attachment = successful.get("0") or successful.get(0)
    attachment_key = attachment.get("key") if isinstance(attachment, dict) else ""
    if not attachment_key:
        raise SystemExit(f"Zotero attachment item creation failed: {created}")
    try:
        upload_local_file(attachment_key, pdf_path, headers)
    except (Exception, SystemExit):
        cleanup_created_attachment(attachment_key, daily, headers)
        raise


def cleanup_created_attachment(attachment_key: str, daily, headers: dict[str, str]) -> None:
    """Remove only the empty attachment item created by this failed invocation."""
    try:
        item, _ = daily.request(f"/users/0/items/{attachment_key}", headers=headers)
        data = item.get("data", {}) if isinstance(item, dict) else {}
        if item.get("key") != attachment_key or data.get("itemType") != "attachment":
            return
        delete_headers = {**headers, "If-Unmodified-Since-Version": str(item.get("version") or data.get("version"))}
        daily.request(f"/users/0/items/{attachment_key}", "DELETE", None, delete_headers)
    except Exception as exc:
        print(f"Zotero cleanup warning: {type(exc).__name__}")


def upload_local_file(attachment_key: str, pdf_path: Path, headers: dict[str, str]) -> None:
    content = pdf_path.read_bytes()
    precondition = {**headers, "If-None-Match": "*"}
    params = {
        "md5": hashlib.md5(content).hexdigest(),
        "filename": pdf_path.name,
        "filesize": str(len(content)),
        "mtime": str(int(pdf_path.stat().st_mtime * 1000)),
    }
    authorization = local_form_post(f"/api/users/0/items/{attachment_key}/file", params, precondition)
    if authorization.get("exists"):
        return
    upload_key = authorization.get("uploadKey")
    upload_url = authorization.get("url")
    if not upload_key or not upload_url:
        raise SystemExit(f"Zotero file upload authorization failed: {authorization}")
    if str(upload_url).startswith("/"):
        upload_url = "http://127.0.0.1:23119" + str(upload_url)
    payload = str(authorization.get("prefix") or "").encode() + content + str(authorization.get("suffix") or "").encode()
    upload_request = urllib.request.Request(
        str(upload_url), data=payload, method="POST",
        headers={"Content-Type": authorization.get("contentType") or "application/pdf"},
    )
    with urllib.request.urlopen(upload_request, timeout=60) as response:
        response.read()
    local_form_post(f"/api/users/0/items/{attachment_key}/file", {"upload": upload_key}, precondition)


def local_form_post(path: str, payload: dict[str, str], headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        "http://127.0.0.1:23119" + path,
        data=urllib.parse.urlencode(payload).encode("ascii"), method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Zotero Local API file upload failed: HTTP {exc.code}: {body}") from exc


def item_has_pdf_attachment(item_key: str, expected_pdf: Path | None = None) -> bool:
    url = CONNECTOR + f"/api/users/0/items/{item_key}/children?itemType=attachment&limit=100"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            items = json.load(response)
    except urllib.error.URLError as exc:
        raise SystemExit(f"Zotero Local API attachment lookup failed: {exc}") from exc
    expected_md5 = hashlib.md5(expected_pdf.read_bytes()).hexdigest() if expected_pdf else ""
    return any(
        item.get("data", {}).get("contentType") == "application/pdf"
        and (not expected_md5 or item.get("data", {}).get("md5") == expected_md5)
        for item in items
    )


def wait_for_pdf_attachment(item_key: str, expected_pdf: Path) -> bool:
    for _ in range(20):
        if item_has_pdf_attachment(item_key, expected_pdf):
            return True
        time.sleep(0.5)
    return False


def update_obsidian_note(note_path: Path, status: dict[str, Any]) -> None:
    if not note_path.is_file():
        return
    text = note_path.read_text(encoding="utf-8")
    text = re.sub(r"zotero_status: .+", "zotero_status: linked", text)
    text = re.sub(r"- Zotero: .+", f"- Zotero: {status.get('zotero_item_uri') or 'linked'}", text)
    note_path.write_text(text, encoding="utf-8")


def normalize_doi(value: str) -> str:
    return value.strip().lower().removeprefix("https://doi.org/").removeprefix("http://doi.org/")


def html_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


if __name__ == "__main__":
    raise SystemExit(main())
