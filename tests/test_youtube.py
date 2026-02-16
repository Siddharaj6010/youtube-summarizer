"""Tests for src/youtube.py — playlist operations, video details, error handling."""

import json
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from youtube import (
    get_playlist_videos,
    get_video_details,
    move_video_to_playlist,
    _handle_http_error,
    YouTubeAPIError,
    QuotaExceededError,
    InvalidVideoError,
)
from googleapiclient.errors import HttpError


def _make_http_error(status, reason="", content=None):
    """Create a mock HttpError for testing."""
    resp = MagicMock()
    resp.status = status
    if content is None:
        content = json.dumps({
            "error": {"errors": [{"reason": reason}], "message": "error"}
        }).encode("utf-8")
    return HttpError(resp=resp, content=content)


# ---------------------------------------------------------------------------
# get_playlist_videos
# ---------------------------------------------------------------------------

class TestGetPlaylistVideos:
    def test_returns_list_of_video_dicts(self):
        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.return_value = {
            "items": [
                {
                    "id": "pli_1",
                    "snippet": {
                        "title": "Video One",
                        "videoOwnerChannelTitle": "Channel A",
                    },
                    "contentDetails": {"videoId": "vid_001"},
                },
                {
                    "id": "pli_2",
                    "snippet": {
                        "title": "Video Two",
                        "videoOwnerChannelTitle": "Channel B",
                    },
                    "contentDetails": {"videoId": "vid_002"},
                },
            ],
            "nextPageToken": None,
        }
        mock_service.playlistItems().list.return_value = mock_request

        videos = get_playlist_videos(mock_service, "PL_test")
        assert len(videos) == 2
        assert videos[0]["video_id"] == "vid_001"
        assert videos[0]["title"] == "Video One"
        assert videos[1]["playlist_item_id"] == "pli_2"

    def test_handles_pagination(self):
        mock_service = MagicMock()

        # Page 1
        page1_request = MagicMock()
        page1_request.execute.return_value = {
            "items": [
                {
                    "id": "pli_1",
                    "snippet": {"title": "Video One", "videoOwnerChannelTitle": "Chan"},
                    "contentDetails": {"videoId": "vid_001"},
                }
            ],
            "nextPageToken": "token_page2",
        }
        # Page 2
        page2_request = MagicMock()
        page2_request.execute.return_value = {
            "items": [
                {
                    "id": "pli_2",
                    "snippet": {"title": "Video Two", "videoOwnerChannelTitle": "Chan"},
                    "contentDetails": {"videoId": "vid_002"},
                }
            ],
            "nextPageToken": None,
        }
        mock_service.playlistItems().list.side_effect = [page1_request, page2_request]

        videos = get_playlist_videos(mock_service, "PL_test")
        assert len(videos) == 2

    def test_empty_playlist(self):
        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.return_value = {"items": [], "nextPageToken": None}
        mock_service.playlistItems().list.return_value = mock_request

        videos = get_playlist_videos(mock_service, "PL_test")
        assert videos == []


# ---------------------------------------------------------------------------
# get_video_details
# ---------------------------------------------------------------------------

class TestGetVideoDetails:
    def test_returns_video_metadata(self):
        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.return_value = {
            "items": [
                {
                    "snippet": {
                        "title": "My Video",
                        "channelTitle": "My Channel",
                        "description": "A description",
                        "publishedAt": "2024-01-01T00:00:00Z",
                    },
                    "contentDetails": {"duration": "PT10M30S"},
                }
            ]
        }
        mock_service.videos().list.return_value = mock_request

        details = get_video_details(mock_service, "vid_001")
        assert details["title"] == "My Video"
        assert details["duration"] == "PT10M30S"
        assert details["channel"] == "My Channel"

    def test_video_not_found_raises(self):
        mock_service = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.return_value = {"items": []}
        mock_service.videos().list.return_value = mock_request

        with pytest.raises(InvalidVideoError):
            get_video_details(mock_service, "nonexistent")


# ---------------------------------------------------------------------------
# _handle_http_error
# ---------------------------------------------------------------------------

class TestHandleHttpError:
    def test_403_quota_exceeded(self):
        error = _make_http_error(403, reason="quotaExceeded")
        with pytest.raises(QuotaExceededError):
            _handle_http_error(error, "test context")

    def test_403_daily_limit(self):
        error = _make_http_error(403, reason="dailyLimitExceeded")
        with pytest.raises(QuotaExceededError):
            _handle_http_error(error, "test context")

    def test_404_raises_invalid_video(self):
        error = _make_http_error(404, reason="notFound")
        with pytest.raises(InvalidVideoError):
            _handle_http_error(error, "test context")

    def test_other_error_raises_youtube_api_error(self):
        error = _make_http_error(500, reason="backendError")
        with pytest.raises(YouTubeAPIError):
            _handle_http_error(error, "test context")

    def test_403_non_quota_raises_youtube_api_error(self):
        error = _make_http_error(403, reason="forbidden")
        with pytest.raises(YouTubeAPIError):
            _handle_http_error(error, "test context")


# ---------------------------------------------------------------------------
# move_video_to_playlist
# ---------------------------------------------------------------------------

class TestMoveVideoToPlaylist:
    @patch("youtube.remove_from_playlist", return_value=True)
    @patch("youtube.add_to_playlist", return_value="new_pli_id")
    def test_moves_with_provided_playlist_item_id(self, mock_add, mock_remove):
        mock_service = MagicMock()

        result = move_video_to_playlist(
            mock_service, "vid_001", "PL_src", "PL_dst",
            playlist_item_id="pli_123",
        )
        assert result == "new_pli_id"
        mock_add.assert_called_once_with(mock_service, "PL_dst", "vid_001")
        mock_remove.assert_called_once_with(mock_service, "pli_123")

    @patch("youtube.remove_from_playlist", return_value=True)
    @patch("youtube.add_to_playlist", return_value="new_pli_id")
    @patch("youtube.get_playlist_videos")
    def test_looks_up_playlist_item_id_if_not_provided(
        self, mock_get_videos, mock_add, mock_remove,
    ):
        mock_service = MagicMock()
        mock_get_videos.return_value = [
            {"video_id": "vid_001", "playlist_item_id": "pli_found"},
        ]

        result = move_video_to_playlist(mock_service, "vid_001", "PL_src", "PL_dst")
        assert result == "new_pli_id"
        mock_remove.assert_called_once_with(mock_service, "pli_found")

    @patch("youtube.get_playlist_videos", return_value=[])
    def test_video_not_in_source_raises(self, mock_get_videos):
        mock_service = MagicMock()
        with pytest.raises(InvalidVideoError):
            move_video_to_playlist(mock_service, "vid_missing", "PL_src", "PL_dst")
