"""Tests for src/slack_notify.py — Slack notifications with mocked HTTP."""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import requests
from slack_notify import send_summary_notification, send_error_notification, send_recovery_notification


def _sample_video_data():
    return {
        "title": "Test Video",
        "channel": "TestChan",
        "duration": "10:30",
        "url": "https://youtube.com/watch?v=vid123",
        "summary": "A great video about testing.",
        "key_points": "• Point 1\n• Point 2",
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


class TestSendErrorNotification:
    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_successful_send(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        result = send_error_notification("Token expired", attempt=1, next_retry_minutes=15)
        assert result is True
        mock_post.assert_called_once()

    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_includes_error_and_attempt(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        send_error_notification("API key invalid", attempt=3, next_retry_minutes=120)

        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert "blocks" in payload
        assert "#3" in payload["text"]

    @patch("slack_notify.get_webhook_url", return_value=None)
    def test_no_webhook_returns_false(self, mock_url):
        assert send_error_notification("err", attempt=1, next_retry_minutes=15) is False

    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_first_attempt_includes_explanation(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        send_error_notification("some error", attempt=1, next_retry_minutes=15)

        call_kwargs = mock_post.call_args[1]
        blocks = call_kwargs["json"]["blocks"]
        block_texts = str(blocks)
        assert "increasing delays" in block_texts

    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_retry_text_for_hours(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        send_error_notification("err", attempt=3, next_retry_minutes=120)

        call_kwargs = mock_post.call_args[1]
        blocks = call_kwargs["json"]["blocks"]
        context_block = blocks[1]  # context block with retry info
        assert "2h" in context_block["elements"][0]["text"]

    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_retry_text_for_24_hours(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        send_error_notification("err", attempt=5, next_retry_minutes=1440)

        call_kwargs = mock_post.call_args[1]
        blocks = call_kwargs["json"]["blocks"]
        context_block = blocks[1]
        assert "24 hours" in context_block["elements"][0]["text"]


class TestSendRecoveryNotification:
    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_successful_send(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        result = send_recovery_notification(previous_failures=5)
        assert result is True

    @patch("slack_notify.requests.post")
    @patch("slack_notify.get_webhook_url", return_value="https://hooks.slack.com/test")
    def test_includes_failure_count(self, mock_url, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        send_recovery_notification(previous_failures=7)

        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert "7" in payload["text"]

    @patch("slack_notify.get_webhook_url", return_value=None)
    def test_no_webhook_returns_false(self, mock_url):
        assert send_recovery_notification(previous_failures=3) is False
