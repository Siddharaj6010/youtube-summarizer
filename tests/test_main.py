"""Tests for src/main.py — format_duration and process_video."""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

# Add src to path so imports work like they do in production
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from main import format_duration, process_video


# ---------------------------------------------------------------------------
# format_duration — pure logic tests
# ---------------------------------------------------------------------------

class TestFormatDuration:
    def test_hours_minutes_seconds(self):
        assert format_duration("PT1H30M45S") == "1:30:45"

    def test_minutes_seconds(self):
        assert format_duration("PT5M30S") == "5:30"

    def test_seconds_only(self):
        assert format_duration("PT45S") == "0:45"

    def test_hours_only(self):
        assert format_duration("PT2H") == "2:00:00"

    def test_zero_padded_minutes_and_seconds(self):
        assert format_duration("PT1H5M3S") == "1:05:03"

    def test_hours_and_minutes_no_seconds(self):
        assert format_duration("PT1H30M") == "1:30:00"

    def test_empty_string(self):
        assert format_duration("") == "Unknown"

    def test_none(self):
        assert format_duration(None) == "Unknown"


# ---------------------------------------------------------------------------
# process_video — integration with mocked dependencies
# ---------------------------------------------------------------------------

class TestProcessVideo:
    """Tests for the process_video orchestrator function."""

    def _make_video(self, video_id="vid123", title="Test Video", channel="TestChan"):
        return {
            "video_id": video_id,
            "title": title,
            "channel_name": channel,
            "playlist_item_id": "pli_123",
        }

    @patch("main.send_summary_notification", return_value=True)
    @patch("main.create_summary_page", return_value="page_abc")
    @patch("main.summarize_transcript", return_value={
        "summary": "A great video.",
        "key_points": ["point1", "point2"],
        "target_audience": "developers",
    })
    @patch("main.get_transcript", return_value="Hello this is a transcript.")
    @patch("main.get_video_details", return_value={"duration": "PT10M30S"})
    def test_successful_flow(
        self, mock_details, mock_transcript, mock_summarize,
        mock_notion, mock_slack,
    ):
        result = process_video(MagicMock(), MagicMock(), self._make_video(), "db_id")
        assert result is True
        mock_notion.assert_called_once()
        mock_slack.assert_called_once()

    @patch("main.send_processing_error_notification", return_value=True)
    @patch("main.create_error_page", return_value="err_page_1")
    @patch("main.get_transcript", return_value=None)
    @patch("main.get_video_details", return_value={"duration": "PT5M"})
    def test_no_transcript_creates_error_page_and_returns_false(
        self, mock_details, mock_transcript, mock_error_page, mock_slack,
    ):
        result = process_video(MagicMock(), MagicMock(), self._make_video(), "db_id")
        assert result is False  # Video should NOT be moved
        mock_error_page.assert_called_once()
        mock_slack.assert_called_once()
        # Verify error message mentions transcript
        call_args = mock_error_page.call_args
        assert "transcript" in call_args[0][3].lower() or "transcript" in str(call_args).lower()

    @patch("main.send_processing_error_notification", return_value=True)
    @patch("main.create_error_page", return_value="err_page_2")
    @patch("main.summarize_transcript", return_value={
        "summary": "",
        "key_points": [],
        "target_audience": "",
        "error": "Anthropic API error: something broke",
    })
    @patch("main.get_transcript", return_value="some transcript text")
    @patch("main.get_video_details", return_value={"duration": "PT3M"})
    def test_summarizer_failure_creates_error_page_and_returns_false(
        self, mock_details, mock_transcript, mock_summarize, mock_error_page, mock_slack,
    ):
        result = process_video(MagicMock(), MagicMock(), self._make_video(), "db_id")
        assert result is False  # Video should NOT be moved
        mock_error_page.assert_called_once()
        mock_slack.assert_called_once()

    @patch("main.send_processing_error_notification", return_value=True)
    @patch("main.create_error_page", side_effect=Exception("Notion down"))
    @patch("main.get_transcript", return_value=None)
    @patch("main.get_video_details", return_value={"duration": "PT5M"})
    def test_notion_error_page_failure_returns_false(
        self, mock_details, mock_transcript, mock_error_page, mock_slack,
    ):
        result = process_video(MagicMock(), MagicMock(), self._make_video(), "db_id")
        assert result is False

    @patch("main.send_processing_error_notification", return_value=True)
    @patch("main.get_video_details", side_effect=Exception("API error"))
    @patch("main.get_transcript", return_value=None)
    @patch("main.create_error_page", return_value="err_page")
    def test_video_details_failure_uses_unknown_duration(
        self, mock_error_page, mock_transcript, mock_details, mock_slack,
    ):
        result = process_video(MagicMock(), MagicMock(), self._make_video(), "db_id")
        assert result is False
        # Check that duration was set to "Unknown" in video_data
        call_args = mock_error_page.call_args
        video_data = call_args[0][2]
        assert video_data["duration"] == "Unknown"
