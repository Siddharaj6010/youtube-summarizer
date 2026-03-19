"""Tests for src/transcript.py — get_transcript with mocked HTTP."""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import requests
from transcript import get_transcript
from exceptions import VideoError, APIError


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    """Ensure SUPADATA_API_KEY is set for all tests unless explicitly testing missing key."""
    monkeypatch.setenv("SUPADATA_API_KEY", "test-key-123")


class TestGetTranscript:
    @patch("transcript.requests.get")
    def test_200_with_content_returns_transcript(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"content": "Hello world transcript text"}
        mock_get.return_value = mock_resp

        result = get_transcript("vid123")
        assert result == "Hello world transcript text"

    @patch("transcript.requests.get")
    def test_200_with_segments_returns_joined_text(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": None,
            "segments": [
                {"text": "Part one"},
                {"text": "Part two"},
            ],
        }
        mock_get.return_value = mock_resp

        result = get_transcript("vid123")
        assert result == "Part one Part two"

    @patch("transcript.requests.get")
    def test_200_empty_response_raises_video_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        mock_get.return_value = mock_resp

        with pytest.raises(VideoError) as exc_info:
            get_transcript("vid123")
        assert "empty" in str(exc_info.value).lower()

    @patch("transcript.requests.get")
    def test_404_raises_video_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        with pytest.raises(VideoError) as exc_info:
            get_transcript("vid123")
        assert "vid123" in str(exc_info.value)

    @patch("transcript.requests.get")
    def test_400_raises_video_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = '{"error": "Invalid video"}'
        mock_resp.json.return_value = {"error": "Invalid video"}
        mock_get.return_value = mock_resp

        with pytest.raises(VideoError):
            get_transcript("vid123")

    @patch("transcript.requests.get")
    def test_401_raises_api_error_with_action_required(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        with pytest.raises(APIError) as exc_info:
            get_transcript("vid123")
        assert exc_info.value.service == "Supadata"
        assert exc_info.value.action_required is True

    @patch("transcript.requests.get")
    def test_429_raises_api_error_auto_resolve(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_get.return_value = mock_resp

        with pytest.raises(APIError) as exc_info:
            get_transcript("vid123")
        assert exc_info.value.service == "Supadata"
        assert exc_info.value.action_required is False
        assert "monthly" in exc_info.value.user_message.lower() or "limit" in exc_info.value.user_message.lower()

    @patch("transcript.requests.get")
    def test_500_raises_api_error_auto_resolve(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_get.return_value = mock_resp

        with pytest.raises(APIError) as exc_info:
            get_transcript("vid123")
        assert exc_info.value.action_required is False

    @patch("transcript.requests.get")
    def test_timeout_raises_api_error(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("timed out")

        with pytest.raises(APIError) as exc_info:
            get_transcript("vid123")
        assert exc_info.value.action_required is False

    @patch("transcript.requests.get")
    def test_connection_error_raises_api_error(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("connection failed")

        with pytest.raises(APIError) as exc_info:
            get_transcript("vid123")
        assert exc_info.value.action_required is False

    def test_missing_api_key_raises_api_error(self, monkeypatch):
        monkeypatch.delenv("SUPADATA_API_KEY", raising=False)

        with pytest.raises(APIError) as exc_info:
            get_transcript("vid123")
        assert exc_info.value.action_required is True
        assert "SUPADATA_API_KEY" in exc_info.value.user_message
