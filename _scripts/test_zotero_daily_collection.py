"""Verify that daily collection cleanup preserves original Zotero items."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import zotero_daily_collection as daily


class DailyCollectionTests(unittest.TestCase):
    def test_keep_one_only_changes_collection_memberships(self):
        parent = {"key": "NEW", "version": 4,
                  "data": {"itemType": "journalArticle", "collections": ["TARGET"]}}
        old = {"key": "OLD", "version": 7,
               "data": {"itemType": "journalArticle", "collections": ["TARGET", "OTHER"]}}
        patches = []
        def fake_request(path, method="GET", payload=None, headers=None, timeout=30):
            if path == "/":
                return {}, {"Zotero-Server-ID": "server"}
            if path == "/users/0/collections":
                return [{"key": "TARGET", "data": {"name": daily.COLLECTION_NAME}}], {}
            if path == "/users/0/items/NEW":
                return parent, {}
            if path == "/users/0/items/OLD" and method == "GET":
                return old, {}
            if path == "/users/0/items/OLD" and method == "PATCH":
                patches.append((payload, headers))
                return {}, {}
            raise AssertionError((path, method))

        with patch.object(daily, "request", side_effect=fake_request), \
                patch.object(daily, "authorize", return_value="in-memory"), \
                patch.object(daily, "top_items", side_effect=[[parent, old], [parent]]):
            self.assertEqual(daily.keep_one("NEW", expected_old_keys={"OLD"}), ["OLD"])
        self.assertEqual(patches[0][0], {"collections": ["OTHER"]})
        self.assertEqual(patches[0][1]["If-Unmodified-Since-Version"], "7")

    def test_preflight_mismatch_refuses_mutation(self):
        parent = {"key": "NEW", "version": 4,
                  "data": {"itemType": "journalArticle", "collections": []}}
        def fake_request(path, method="GET", payload=None, headers=None, timeout=30):
            if method != "GET":
                raise AssertionError("mutation before preflight")
            return ({}, {"Zotero-Server-ID": "server"}) if path == "/" else (parent, {})
        with patch.object(daily, "request", side_effect=fake_request), \
                patch.object(daily, "authorize", return_value="in-memory"), \
                patch.object(daily, "get_collection", return_value={"key": "TARGET"}), \
                patch.object(daily, "top_items", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "Collection changed"):
                daily.keep_one("NEW", expected_old_keys={"OLD"})

    def test_single_use_authorization_is_renewed_on_401(self):
        calls = []
        def fake_request(path, method="GET", payload=None, headers=None, timeout=30):
            calls.append(headers["Zotero-API-Key"])
            if len(calls) == 1:
                raise daily.ApiError(401, "single-use key consumed")
            return {}, {}
        with patch.object(daily, "request", side_effect=fake_request), \
                patch.object(daily, "authorize", return_value="fresh") as authorize:
            headers = {"Zotero-Server-ID": "server", "Zotero-API-Key": "old"}
            daily.replace_membership({"key": "OLD", "version": 7}, [], headers)
        self.assertEqual(calls, ["old", "fresh"])
        authorize.assert_called_once_with("server", force=True)

    def test_remembered_authorization_is_reused_without_dialog(self):
        with patch.object(daily, "load_remembered_key", return_value="remembered"), \
                patch.object(daily, "request") as request:
            self.assertEqual(daily.authorize("server"), "remembered")
        request.assert_not_called()

    def test_always_allow_key_is_saved_in_secure_store(self):
        with patch.object(daily, "load_remembered_key", return_value=""), \
                patch.object(daily, "request", return_value=({"key": "new", "remember": True}, {})), \
                patch.object(daily, "store_remembered_key") as store:
            self.assertEqual(daily.authorize("server"), "new")
        store.assert_called_once_with("server", "new")


if __name__ == "__main__":
    unittest.main()
