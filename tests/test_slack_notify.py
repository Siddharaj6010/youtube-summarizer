"""Tests for src/slack_notify.py — Slack notifications with mocked HTTP."""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import requests
from slack_notify import (
    send_summary_notification, send_video_skipped_notification,
    send_api_error_notification,
)


def _sample_video_data():
    return {
        "title": "Test Video",
        "channel": "TestChan",
        "duration": "10:30",
        "url": "https://youtube.com/watch?v=vid123",
        "summary": "A great video about testing.",
        "key_points": "\u2022 Point 1\n\u2022 Point 2",
    }


class TestSendSummaryNotification:
    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_successful_send(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        assert send_summary_notification(_sample_video_data()) is True
        mock_post.assert_called_once()

    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_http_error_returns_false(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        assert send_summary_notification(_sample_video_data()) is False

    @patch("slack_notify.get_webhook_url", return_value=None)
    def test_no_webhook_url_returns_false(self, mock_url):
        assert send_summary_notification(_sample_video_data()) is False

    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_timeout_returns_false(self, mock_url, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("timed out")
        assert send_summary_notification(_sample_video_data()) is False

    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_connection_error_returns_false(self, mock_url, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")
        assert send_summary_notification(_sample_video_data()) is False

    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_payload_contains_blocks(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        send_summary_notification(_sample_video_data())

        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert "blocks" in payload
        assert "text" in payload  # fallback text


class TestSendVideoSkippedNotification:
    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_successful_send(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        result = send_video_skipped_notification(
            "Test Video", "TestChan", "https://youtube.com/watch?v=abc", "No transcript"
        )
        assert result is True

    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_includes_video_title_and_error(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        send_video_skipped_notification(
            "My Video", "MyChan", "https://youtube.com/watch?v=xyz", "No captions"
        )

        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert "My Video" in payload["text"]
        assert "No captions" in payload["text"]

    @patch("slack_notify.get_webhook_url", return_value=None)
    def test_no_webhook_returns_false(self, mock_url):
        assert send_video_skipped_notification("t", "c", "u", "e") is False


class TestSendApiErrorNotification:
    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_successful_send(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        result = send_api_error_notification(
            "OpenRouter", "Out of credits", action_required=True
        )
        assert result is True
        mock_post.assert_called_once()

    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_action_required_uses_red_circle(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        send_api_error_notification("OpenRouter", "Bad key", action_required=True)

        call_kwargs = mock_post.call_args[1]
        blocks = call_kwargs["json"]["blocks"]
        block_texts = str(blocks)
        assert "red_circle" in block_texts

    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_auto_resolve_uses_yellow_circle(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        send_api_error_notification("Supadata", "Monthly limit", action_required=False)

        call_kwargs = mock_post.call_args[1]
        blocks = call_kwargs["json"]["blocks"]
        block_texts = str(blocks)
        assert "yellow_circle" in block_texts

    @patch("slack_notify.get_webhook_url", return_value=None)
    def test_no_webhook_returns_false(self, mock_url):
        assert send_api_error_notification("S", "M", action_required=True) is False
