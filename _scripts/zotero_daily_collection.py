#!/usr/bin/env python
"""Keep one daily paper in Zotero's dedicated reading collection.

Uses Zotero 10's official Local API. A local authorization key is kept only in memory.
Other entries are removed from the collection, never deleted from My Library.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

import keyring
from keyring.errors import KeyringError, PasswordDeleteError


BASE = "http://127.0.0.1:23119/api"
COLLECTION_NAME = "每日文献阅读"
CREDENTIAL_SERVICE = "Codex 每日文献阅读 Zotero Local API"


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def request(path: str, method: str = "GET", payload: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None, timeout: int = 30) -> tuple[Any, dict[str, str]]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(BASE + path, data=body, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            try:
                result = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                result = raw
            return result, dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        reason = exc.read().decode("utf-8", errors="replace")
        raise ApiError(exc.code, f"Zotero Local API {method} {path}: HTTP {exc.code}: {reason[:500]}") from exc


def load_remembered_key(server_id: str) -> str:
    try:
        return keyring.get_password(CREDENTIAL_SERVICE, server_id) or ""
    except KeyringError as exc:
        print(f"Zotero credential warning: {type(exc).__name__}", file=sys.stderr)
        return ""


def store_remembered_key(server_id: str, key: str) -> None:
    try:
        keyring.set_password(CREDENTIAL_SERVICE, server_id, key)
    except KeyringError as exc:
        print(f"Zotero credential warning: {type(exc).__name__}", file=sys.stderr)


def clear_remembered_key(server_id: str) -> None:
    try:
        keyring.delete_password(CREDENTIAL_SERVICE, server_id)
    except PasswordDeleteError:
        pass
    except KeyringError as exc:
        print(f"Zotero credential warning: {type(exc).__name__}", file=sys.stderr)


def authorize(server_id: str, force: bool = False) -> str:
    if force:
        clear_remembered_key(server_id)
    else:
        remembered = load_remembered_key(server_id)
        if remembered:
            return remembered
    try:
        result, _ = request("/local/authorize", "POST", {"appName": "Codex 每日文献阅读"},
                            {"Zotero-Server-ID": server_id}, timeout=90)
    except TimeoutError as exc:
        raise RuntimeError("Zotero local authorization dialog was not accepted within 90 seconds") from exc
    key = result.get("apiKey") or result.get("key")
    if not key:
        raise RuntimeError("Zotero did not return a local authorization key")
    if result.get("remember"):
        store_remembered_key(server_id, key)
    return key


def get_collection(name: str, headers: dict[str, str]) -> dict[str, Any]:
    collections, _ = request("/users/0/collections", headers=headers)
    matches = [entry for entry in collections if entry.get("data", {}).get("name") == name]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one Zotero collection named {name!r}; found {len(matches)}")
    return matches[0]


def top_items(collection_key: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    items, _ = request(f"/users/0/collections/{collection_key}/items/top?limit=100", headers=headers)
    if len(items) == 100:
        raise RuntimeError("Collection may exceed 100 top items; refuse incomplete cleanup")
    return items


def replace_membership(item: dict[str, Any], collections: list[str], headers: dict[str, str]) -> None:
    key = item["key"]
    version = item["version"]
    write_headers = {**headers, "If-Unmodified-Since-Version": str(version)}
    try:
        request(f"/users/0/items/{key}", "PATCH", {"collections": collections}, write_headers)
    except ApiError as exc:
        if exc.status != 401:
            raise
        headers["Zotero-API-Key"] = authorize(headers["Zotero-Server-ID"], force=True)
        write_headers["Zotero-API-Key"] = headers["Zotero-API-Key"]
        request(f"/users/0/items/{key}", "PATCH", {"collections": collections}, write_headers)


def keep_one(keep_key: str, collection_name: str = COLLECTION_NAME,
             expected_old_keys: set[str] | None = None) -> list[str]:
    _, server_headers = request("/")
    server_id = next((value for key, value in server_headers.items()
                      if key.lower() == "zotero-server-id"), "")
    if not server_id:
        raise RuntimeError("Zotero Local API server ID is missing")
    auth_key = authorize(server_id)
    headers = {"Zotero-Server-ID": server_id, "Zotero-API-Key": auth_key}
    collection = get_collection(collection_name, headers)
    collection_key = collection["key"]
    keep_item, _ = request(f"/users/0/items/{keep_key}", headers=headers)
    if keep_item.get("data", {}).get("itemType") in {"attachment", "note"}:
        raise RuntimeError("The retained key must identify a parent paper")
    items = top_items(collection_key, headers)
    old_keys = {item["key"] for item in items if item["key"] != keep_key}
    if expected_old_keys is not None and old_keys != expected_old_keys:
        raise RuntimeError(f"Collection changed since preflight; expected {sorted(expected_old_keys)}, found {sorted(old_keys)}")
    existing = list(keep_item["data"].get("collections", []))
    if collection_key not in existing:
        replace_membership(keep_item, [*existing, collection_key], headers)
    removed: list[str] = []
    for item in items:
        if item["key"] == keep_key:
            continue
        remaining = [key for key in item["data"].get("collections", []) if key != collection_key]
        replace_membership(item, remaining, headers)
        removed.append(item["key"])

    final_keys = {item["key"] for item in top_items(collection_key, headers)}
    if final_keys != {keep_key}:
        raise RuntimeError(f"Collection verification failed: {sorted(final_keys)}")
    for old_key in removed:
        old_item, _ = request(f"/users/0/items/{old_key}", headers=headers)
        if old_item.get("key") != old_key:
            raise RuntimeError(f"Original library item {old_key} is no longer accessible")
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-item", required=True, help="Zotero parent item key for the daily paper")
    parser.add_argument("--collection-name", default=COLLECTION_NAME)
    parser.add_argument("--expected-old-keys", default="", help="Comma-separated preflight keys, for first migration")
    args = parser.parse_args()
    expected = set(args.expected_old_keys.split(",")) if args.expected_old_keys else None
    removed = keep_one(args.keep_item, args.collection_name, expected)
    print(f"collection={args.collection_name}")
    print(f"kept={args.keep_item}")
    print(f"memberships_removed={','.join(removed) or 'none'}")
    print("original_library_items_preserved=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
