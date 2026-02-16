"""Tests for src/notion_db.py — _truncate_text, get_processed_video_ids, create pages."""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from notion_db import _truncate_text, get_processed_video_ids, create_summary_page, create_error_page


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

    def test_handles_pagination(self):
        mock_client = MagicMock()
        # First page
        page1 = {
            "results": [
                {"properties": {"Video ID": {"rich_text": [{"text": {"content": "vid_001"}}]}}}
            ],
            "has_more": True,
            "next_cursor": "cursor_abc",
        }
        # Second page
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
            "key_points": "• Point 1\n• Point 2",
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
# create_error_page — mocked Notion client
# ---------------------------------------------------------------------------

class TestCreateErrorPage:
    def test_returns_page_id(self):
        mock_client = MagicMock()
        mock_client.pages.create.return_value = {"id": "err_page_1"}

        video_data = {
            "video_id": "vid_002",
            "title": "Broken Video",
            "url": "https://youtube.com/watch?v=vid_002",
            "channel": "Chan",
        }

        result = create_error_page(mock_client, "db_123", video_data, "No transcript")
        assert result == "err_page_1"

    def test_error_status_and_message(self):
        mock_client = MagicMock()
        mock_client.pages.create.return_value = {"id": "err_page_2"}

        video_data = {
            "video_id": "vid_003",
            "title": "Another Video",
            "url": "https://youtube.com/watch?v=vid_003",
            "channel": "Chan",
        }

        create_error_page(mock_client, "db_123", video_data, "API timeout")

        call_kwargs = mock_client.pages.create.call_args[1]
        props = call_kwargs["properties"]
        assert props["Status"]["select"]["name"] == "Error"
        assert "API timeout" in props["Summary"]["rich_text"][0]["text"]["content"]
