"""Tests for src/notion_db.py — _truncate_text, get_processed_video_ids, create pages, retry tracking."""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from notion_db import (
    _truncate_text, get_processed_video_ids, create_summary_page,
    increment_retry_count, mark_video_skipped,
)
from exceptions import APIError


# ---------------------------------------------------------------------------
# _truncate_text — pure logic
# ---------------------------------------------------------------------------

class TestTruncateText:
    def test_short_text_unchanged(self):
        assert _truncate_text("hello", 100) == "hello"

    def test_long_text_truncated_with_ellipsis(self):
        result = _truncate_text("a" * 50, 20)
        assert len(result) == 20
        assert result.endswith("...")

    def test_exactly_at_limit(self):
        text = "a" * 100
        assert _truncate_text(text, 100) == text

    def test_one_over_limit(self):
        text = "a" * 101
        result = _truncate_text(text, 100)
        assert len(result) == 100
        assert result.endswith("...")

    def test_empty_string(self):
        assert _truncate_text("", 10) == ""


# ---------------------------------------------------------------------------
# get_processed_video_ids — mocked Notion client
# ---------------------------------------------------------------------------

class TestGetProcessedVideoIds:
    def test_returns_set_of_video_ids(self):
        mock_client = MagicMock()
        mock_client.databases.query.return_value = {
            "results": [
                {
                    "properties": {
                        "Video ID": {
                            "rich_text": [{"text": {"content": "vid_001"}}]
                        }
                    }
                },
                {
                    "properties": {
                        "Video ID": {
                            "rich_text": [{"text": {"content": "vid_002"}}]
                        }
                    }
                },
            ],
            "has_more": False,
            "next_cursor": None,
        }

        result = get_processed_video_ids(mock_client, "db_123")
        assert result == {"vid_001", "vid_002"}

    def test_filter_includes_summarized_and_skipped(self):
        mock_client = MagicMock()
        mock_client.databases.query.return_value = {
            "results": [],
            "has_more": False,
            "next_cursor": None,
        }

        get_processed_video_ids(mock_client, "db_123")

        call_kwargs = mock_client.databases.query.call_args[1]
        filter_config = call_kwargs["filter"]
        assert "or" in filter_config
        statuses = [f["select"]["equals"] for f in filter_config["or"]]
        assert "Summarized" in statuses
        assert "Skipped" in statuses

    def test_handles_pagination(self):
        mock_client = MagicMock()
        page1 = {
            "results": [
                {"properties": {"Video ID": {"rich_text": [{"text": {"content": "vid_001"}}]}}}
            ],
            "has_more": True,
            "next_cursor": "cursor_abc",
        }
        page2 = {
            "results": [
                {"properties": {"Video ID": {"rich_text": [{"text": {"content": "vid_002"}}]}}}
            ],
            "has_more": False,
            "next_cursor": None,
        }
        mock_client.databases.query.side_effect = [page1, page2]

        result = get_processed_video_ids(mock_client, "db_123")
        assert result == {"vid_001", "vid_002"}
        assert mock_client.databases.query.call_count == 2

    def test_empty_database(self):
        mock_client = MagicMock()
        mock_client.databases.query.return_value = {
            "results": [],
            "has_more": False,
            "next_cursor": None,
        }

        result = get_processed_video_ids(mock_client, "db_123")
        assert result == set()

    def test_missing_rich_text_skipped(self):
        mock_client = MagicMock()
        mock_client.databases.query.return_value = {
            "results": [
                {"properties": {"Video ID": {"rich_text": []}}},
                {"properties": {"Video ID": {"rich_text": [{"text": {"content": "vid_001"}}]}}},
            ],
            "has_more": False,
            "next_cursor": None,
        }

        result = get_processed_video_ids(mock_client, "db_123")
        assert result == {"vid_001"}


# ---------------------------------------------------------------------------
# create_summary_page — mocked Notion client
# ---------------------------------------------------------------------------

class TestCreateSummaryPage:
    def test_returns_page_id(self):
        mock_client = MagicMock()
        mock_client.pages.create.return_value = {"id": "page_xyz"}

        video_data = {
            "video_id": "vid_001",
            "title": "Test Video",
            "url": "https://youtube.com/watch?v=vid_001",
            "channel": "TestChan",
            "summary": "A great summary.",
            "key_points": "\u2022 Point 1\n\u2022 Point 2",
            "duration": "10:30",
        }

        result = create_summary_page(mock_client, "db_123", video_data)
        assert result == "page_xyz"

    def test_correct_properties_passed(self):
        mock_client = MagicMock()
        mock_client.pages.create.return_value = {"id": "page_xyz"}

        video_data = {
            "video_id": "vid_001",
            "title": "My Title",
            "url": "https://youtube.com/watch?v=vid_001",
            "channel": "MyChan",
            "summary": "Summary text",
            "key_points": "Points",
            "duration": "5:00",
        }

        create_summary_page(mock_client, "db_123", video_data)

        call_kwargs = mock_client.pages.create.call_args[1]
        props = call_kwargs["properties"]
        assert props["Title"]["title"][0]["text"]["content"] == "My Title"
        assert props["Video ID"]["rich_text"][0]["text"]["content"] == "vid_001"
        assert props["URL"]["url"] == "https://youtube.com/watch?v=vid_001"
        assert props["Status"]["select"]["name"] == "Summarized"


# ---------------------------------------------------------------------------
# increment_retry_count — mocked Notion client
# ---------------------------------------------------------------------------

class TestIncrementRetryCount:
    def _make_video_data(self):
        return {
            "video_id": "vid_001",
            "title": "Test Video",
            "url": "https://youtube.com/watch?v=vid_001",
            "channel": "TestChan",
            "duration": "5:00",
        }

    def test_creates_new_error_page_on_first_failure(self):
        mock_client = MagicMock()
        # No existing error page
        mock_client.databases.query.return_value = {"results": []}
        mock_client.pages.create.return_value = {"id": "new_page"}

        count = increment_retry_count(mock_client, "db_123", self._make_video_data(), "No transcript")
        assert count == 1
        mock_client.pages.create.assert_called_once()

    def test_increments_existing_error_page(self):
        mock_client = MagicMock()
        existing_page = {
            "id": "existing_page_id",
            "properties": {
                "Video ID": {"rich_text": [{"text": {"content": "vid_001"}}]},
                "Retry Count": {"number": 1},
                "Status": {"select": {"name": "Error"}},
            }
        }
        mock_client.databases.query.return_value = {"results": [existing_page]}

        count = increment_retry_count(mock_client, "db_123", self._make_video_data(), "Still failing")
        assert count == 2
        mock_client.pages.update.assert_called_once()
        update_kwargs = mock_client.pages.update.call_args[1]
        assert update_kwargs["properties"]["Retry Count"]["number"] == 2

    def test_handles_none_retry_count_as_zero(self):
        mock_client = MagicMock()
        existing_page = {
            "id": "existing_page_id",
            "properties": {
                "Video ID": {"rich_text": [{"text": {"content": "vid_001"}}]},
                "Retry Count": {"number": None},
                "Status": {"select": {"name": "Error"}},
            }
        }
        mock_client.databases.query.return_value = {"results": [existing_page]}

        count = increment_retry_count(mock_client, "db_123", self._make_video_data(), "Error")
        assert count == 1


# ---------------------------------------------------------------------------
# mark_video_skipped — mocked Notion client
# ---------------------------------------------------------------------------

class TestMarkVideoSkipped:
    def test_updates_status_to_skipped(self):
        mock_client = MagicMock()
        existing_page = {
            "id": "page_to_skip",
            "properties": {
                "Video ID": {"rich_text": [{"text": {"content": "vid_001"}}]},
                "Status": {"select": {"name": "Error"}},
            }
        }
        mock_client.databases.query.return_value = {"results": [existing_page]}

        mark_video_skipped(mock_client, "db_123", "vid_001")

        mock_client.pages.update.assert_called_once()
        update_kwargs = mock_client.pages.update.call_args[1]
        assert update_kwargs["properties"]["Status"]["select"]["name"] == "Skipped"

    def test_no_error_page_found_logs_warning(self):
        mock_client = MagicMock()
        mock_client.databases.query.return_value = {"results": []}

        # Should not raise
        mark_video_skipped(mock_client, "db_123", "vid_missing")
        mock_client.pages.update.assert_not_called()
