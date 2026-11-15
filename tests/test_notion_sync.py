"""Tests for Notion sync helpers: one-pass page index and index-aware
sync_job (no full-database rescan per job, no credential resolution needed)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from notion_sync import NotionSync


def make_sync():
    """Build a NotionSync without touching credentials."""
    s = NotionSync.__new__(NotionSync)
    s.token = 'test-token'
    s.database_id = 'test-db'
    return s


class PageIndexTests(unittest.TestCase):
    def test_builds_index_across_paginated_results(self):
        s = make_sync()
        responses = [
            {"results": [
                {"id": "p1", "properties": {"URL": {"url": "https://www.adzuna.com/details/111?utm=x"}}},
                {"id": "p2", "properties": {"URL": {"url": "https://www.adzuna.com/land/ad/222?v=Y"}}},
                {"id": "p3", "properties": {"URL": {"url": None}}},
             ],
             "next_cursor": "c1"},
            {"results": [
                {"id": "p4", "properties": {"URL": {"url": "https://www.adzuna.com/details/333"}}},
             ],
             "next_cursor": None},
        ]
        s._make_request = MagicMock(side_effect=responses)
        index = s._build_page_index()
        self.assertEqual(index, {"111": "p1", "222": "p2", "333": "p4"})
        self.assertEqual(s._make_request.call_count, 2)

    def test_sync_job_uses_index_without_rescanning(self):
        s = make_sync()
        s._make_request = MagicMock(return_value={"id": "ignored"})
        s._find_existing_page = MagicMock(side_effect=AssertionError("must not full-scan"))
        job = {"title": "T", "company": "C", "location": "L",
               "url": "https://www.adzuna.com/details/111?utm=x",
               "salary_min": 85000, "salary_max": 110000,
               "status": "new", "match_score": 50.0}
        page_id = s.sync_job(job, page_index={"111": "existing-page"})
        self.assertEqual(page_id, "existing-page")
        args, kwargs = s._make_request.call_args
        self.assertEqual(args[0], "/pages/existing-page")
        self.assertEqual(kwargs.get("method"), "PATCH")

    def test_sync_job_creates_page_when_not_in_index(self):
        s = make_sync()
        s._make_request = MagicMock(return_value={"id": "created-page"})
        job = {"title": "T", "company": "C",
               "url": "https://www.adzuna.com/details/999",
               "status": "new", "match_score": 10.0}
        page_id = s.sync_job(job, page_index={})
        self.assertEqual(page_id, "created-page")
        args, kwargs = s._make_request.call_args
        self.assertEqual(args[0], "/pages")
        self.assertEqual(kwargs.get("method"), "POST")


class DatePropertyTests(unittest.TestCase):
    def _job(self):
        return {"title": "T", "company": "C",
                "url": "https://www.adzuna.com/details/111",
                "status": "new", "match_score": 50.0,
                "pulled_at": "2026-11-11 14:03:22",  # SQL alias sync_matches provides
                "posted_date": "2026-11-10T13:19:08Z"}

    def test_sync_job_sends_date_properties(self):
        s = make_sync()
        s._make_request = MagicMock(return_value={"id": "pg"})
        s.sync_job(self._job(), page_index={})
        props = s._make_request.call_args.kwargs["data"]["properties"]
        self.assertEqual(props["Date Pulled"]["date"]["start"], "2026-11-11")
        self.assertEqual(props["Date Posted"]["date"]["start"], "2026-11-10")

    def test_sync_job_skips_dates_when_disabled(self):
        s = make_sync()
        s._make_request = MagicMock(return_value={"id": "pg"})
        s.sync_job(self._job(), page_index={}, include_dates=False)
        props = s._make_request.call_args.kwargs["data"]["properties"]
        self.assertNotIn("Date Pulled", props)
        self.assertNotIn("Date Posted", props)

    def test_ensure_schema_adds_only_missing(self):
        s = make_sync()
        s._make_request = MagicMock(side_effect=[
            {"properties": {"Date Pulled": {"date": {}}}},  # GET db: one exists already
            {},                                            # PATCH response
        ])
        self.assertTrue(s.ensure_schema_properties())
        args, kwargs = s._make_request.call_args
        self.assertEqual(args[0], f"/databases/{s.database_id}")
        self.assertEqual(kwargs["method"], "PATCH")
        self.assertEqual(list(kwargs["data"]["properties"]), ["Date Posted"])

    def test_ensure_schema_noop_when_present(self):
        s = make_sync()
        s._make_request = MagicMock(return_value={
            "properties": {"Date Pulled": {}, "Date Posted": {}}})
        self.assertTrue(s.ensure_schema_properties())
        self.assertEqual(s._make_request.call_count, 1)  # GET only, no PATCH

    def test_ensure_schema_returns_false_on_error(self):
        s = make_sync()
        s._make_request = MagicMock(side_effect=RuntimeError("api down"))
        self.assertFalse(s.ensure_schema_properties())

    def test_ensure_schema_adds_not_interested_option_preserving_existing(self):
        s = make_sync()
        s._make_request = MagicMock(side_effect=[
            {"properties": {
                "Date Pulled": {}, "Date Posted": {},
                "Status": {"type": "select", "select": {"options": [
                    {"id": "opt1", "name": "New", "color": "blue"},
                    {"id": "opt2", "name": "Applied", "color": "green"},
                ]}},
            }},
            {},  # PATCH response
        ])
        self.assertTrue(s.ensure_schema_properties())
        args, kwargs = s._make_request.call_args
        self.assertEqual(kwargs["method"], "PATCH")
        opts = kwargs["data"]["properties"]["Status"]["select"]["options"]
        self.assertEqual([o["name"] for o in opts], ["New", "Applied", "Not Interested"])
        self.assertEqual(opts[0]["id"], "opt1")  # existing ids preserved, not recreated

    def test_ensure_schema_skips_status_when_option_present(self):
        s = make_sync()
        s._make_request = MagicMock(return_value={"properties": {
            "Date Pulled": {}, "Date Posted": {},
            "Status": {"type": "select", "select": {"options": [
                {"id": "opt9", "name": "Not Interested", "color": "gray"},
            ]}},
        }})
        self.assertTrue(s.ensure_schema_properties())
        self.assertEqual(s._make_request.call_count, 1)  # GET only, no PATCH

    def test_status_mapping_not_interested(self):
        s = make_sync()
        self.assertEqual(s._map_status('not_interested'), 'Not Interested')
        self.assertEqual(s._map_status('auto_rejected'), 'Auto-Rejected')


if __name__ == '__main__':
    unittest.main()
