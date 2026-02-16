"""Tests for src/transcript.py — get_transcript with mocked HTTP."""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import requests
from transcript import get_transcript


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
    def test_200_empty_response_returns_none(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        mock_get.return_value = mock_resp

        assert get_transcript("vid123") is None

    @patch("transcript.requests.get")
    def test_404_returns_none(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        assert get_transcript("vid123") is None

    @patch("transcript.requests.get")
    def test_401_returns_none(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        assert get_transcript("vid123") is None

    @patch("transcript.requests.get")
    def test_429_returns_none(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_get.return_value = mock_resp

        assert get_transcript("vid123") is None

    @patch("transcript.requests.get")
    def test_timeout_returns_none(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("timed out")
        assert get_transcript("vid123") is None

    @patch("transcript.requests.get")
    def test_request_exception_returns_none(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("connection failed")
        assert get_transcript("vid123") is None

    def test_missing_api_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("SUPADATA_API_KEY", raising=False)
        assert get_transcript("vid123") is None
