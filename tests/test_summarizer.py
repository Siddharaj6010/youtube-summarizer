"""Tests for src/summarizer.py — _truncate_transcript, _parse_response, summarize_transcript."""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from summarizer import _truncate_transcript, _parse_response, summarize_transcript, MAX_TRANSCRIPT_LENGTH


# ---------------------------------------------------------------------------
# _truncate_transcript — pure logic
# ---------------------------------------------------------------------------

class TestTruncateTranscript:
    def test_short_text_unchanged(self):
        text = "This is a short transcript."
        assert _truncate_transcript(text) == text

    def test_long_text_truncated_at_sentence_boundary(self):
        # Build text that exceeds the limit, with a sentence boundary near the end
        sentence = "This is a complete sentence. "
        # Fill up to ~90% of limit with sentences, then add more
        repeats = (MAX_TRANSCRIPT_LENGTH // len(sentence)) + 10
        text = sentence * repeats
        result = _truncate_transcript(text)
        assert len(result) <= MAX_TRANSCRIPT_LENGTH + 100  # some slack for the suffix
        assert result.endswith("[Transcript truncated due to length...]")
        # Should end at a sentence boundary (period before the suffix)
        before_suffix = result.replace("\n\n[Transcript truncated due to length...]", "")
        assert before_suffix.endswith(".")

    def test_long_text_no_sentence_boundary_truncated_at_limit(self):
        # A single long word with no periods
        text = "x" * (MAX_TRANSCRIPT_LENGTH + 1000)
        result = _truncate_transcript(text)
        assert result.endswith("[Transcript truncated due to length...]")

    def test_exactly_at_limit(self):
        text = "a" * MAX_TRANSCRIPT_LENGTH
        assert _truncate_transcript(text) == text


# ---------------------------------------------------------------------------
# _parse_response — pure logic
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_well_formatted_response(self):
        response = """SUMMARY:
This video covers Python tips and tricks for beginners.

KEY POINTS:
- Use list comprehensions for cleaner code
- F-strings are faster than format()
- Type hints improve readability

TARGET AUDIENCE:
Python beginners and intermediate developers"""

        result = _parse_response(response)
        assert "Python tips" in result["summary"]
        assert len(result["key_points"]) == 3
        assert "list comprehensions" in result["key_points"][0]
        assert "beginners" in result["target_audience"].lower()

    def test_missing_sections_return_defaults(self):
        result = _parse_response("Just some random text with no sections.")
        assert result["summary"] == ""
        assert result["key_points"] == []
        assert result["target_audience"] == ""

    def test_multiple_key_points_with_different_bullets(self):
        response = """SUMMARY:
A video about testing.

KEY POINTS:
- First point
* Second point
• Third point

TARGET AUDIENCE:
Developers"""

        result = _parse_response(response)
        assert len(result["key_points"]) == 3

    def test_empty_response(self):
        result = _parse_response("")
        assert result["summary"] == ""
        assert result["key_points"] == []
        assert result["target_audience"] == ""


# ---------------------------------------------------------------------------
# summarize_transcript — mocked OpenRouter client
# ---------------------------------------------------------------------------

class TestSummarizeTranscript:
    @patch("summarizer.get_openrouter_client")
    def test_successful_summarization(self, mock_get_client):
        mock_choice = MagicMock()
        mock_choice.message.content = """SUMMARY:
Great video about Python.

KEY POINTS:
- Tip one
- Tip two

TARGET AUDIENCE:
Developers"""

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = summarize_transcript("Python Tips", "TechChan", "some transcript")
        assert "error" not in result
        assert "Python" in result["summary"]
        assert len(result["key_points"]) == 2

    @patch("summarizer.time.sleep")  # Don't actually sleep in tests
    @patch("summarizer.get_openrouter_client")
    def test_rate_limit_retries_then_fails(self, mock_get_client, mock_sleep):
        import openai

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}
        mock_resp.json.return_value = {}
        mock_client.chat.completions.create.side_effect = openai.RateLimitError(
            message="rate limited",
            response=mock_resp,
            body=None,
        )
        mock_get_client.return_value = mock_client

        result = summarize_transcript("Title", "Channel", "transcript")
        assert "error" in result
        assert "rate limit" in result["error"].lower() or "Rate limit" in result["error"]
        # Should have been called MAX_RETRIES times
        assert mock_client.chat.completions.create.call_count == 3

    @patch("summarizer.get_openrouter_client")
    def test_api_error_returns_error_dict(self, mock_get_client):
        import openai

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.headers = {}
        mock_resp.json.return_value = {}
        mock_client.chat.completions.create.side_effect = openai.APIError(
            message="server error",
            request=MagicMock(),
            body=None,
        )
        mock_get_client.return_value = mock_client

        result = summarize_transcript("Title", "Channel", "transcript")
        assert "error" in result
        assert "API error" in result["error"] or "server error" in result["error"]

    @patch("summarizer.get_openrouter_client", side_effect=ValueError("OPENROUTER_API_KEY not set"))
    def test_missing_api_key(self, mock_get_client):
        result = summarize_transcript("Title", "Channel", "transcript")
        assert "error" in result
