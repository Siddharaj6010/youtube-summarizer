"""
YouTube API Client Module

Handles YouTube API interactions using OAuth 2.0 authentication.
Provides functions for playlist management and video metadata retrieval.
"""

import os
import logging
from typing import Optional

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

from exceptions import VideoError, APIError

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# OAuth 2.0 scopes required for playlist management
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",  # Read playlists
    "https://www.googleapis.com/auth/youtube",  # Modify playlists
]

# YouTube API configuration
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"


def get_youtube_service() -> Resource:
    """
    Build and return an authenticated YouTube API service using refresh token.

    Returns:
        Resource: Authenticated YouTube API service object.

    Raises:
        APIError: If credentials are missing or authentication fails.
    """
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")

    # Validate required credentials
    missing_vars = []
    if not client_id:
        missing_vars.append("YOUTUBE_CLIENT_ID")
    if not client_secret:
        missing_vars.append("YOUTUBE_CLIENT_SECRET")
    if not refresh_token:
        missing_vars.append("YOUTUBE_REFRESH_TOKEN")

    if missing_vars:
        raise APIError(
            f"Missing YouTube credentials: {', '.join(missing_vars)}",
            service="YouTube",
            action_required=True,
            user_message=f"YouTube Credentials Missing — Pipeline paused. Missing secrets: {', '.join(missing_vars)}. Add them in GitHub repository settings.",
            initial_backoff_minutes=1440,
        )

    try:
        # Create credentials using refresh token
        credentials = Credentials(
            token=None,  # Will be refreshed automatically
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=YOUTUBE_SCOPES,
        )

        # Refresh the access token
        credentials.refresh(Request())

        # Build and return the YouTube API service
        service = build(
            YOUTUBE_API_SERVICE_NAME,
            YOUTUBE_API_VERSION,
            credentials=credentials,
        )

        logger.info("Successfully authenticated with YouTube API")
        return service

    except Exception as e:
        logger.error(f"Failed to authenticate with YouTube API: {e}")
        raise APIError(
            f"YouTube authentication failed: {e}",
            service="YouTube",
            action_required=True,
            user_message="YouTube OAuth Token Refresh Failed — Pipeline paused. The YOUTUBE_REFRESH_TOKEN secret may need to be regenerated.",
            initial_backoff_minutes=1440,
        )


def get_playlist_videos(
    service: Resource,
    playlist_id: str,
) -> list[dict[str, str]]:
    """
    Get all video information from a YouTube playlist.

    Args:
        service: Authenticated YouTube API service object.
        playlist_id: The YouTube playlist ID.

    Returns:
        List of dicts with video_id, title, channel_name, playlist_item_id.

    Raises:
        APIError: For quota or authentication errors.
        VideoError: For playlist-specific errors (e.g., not found).
    """
    videos = []
    next_page_token = None

    logger.info(f"Fetching videos from playlist: {playlist_id}")

    try:
        while True:
            request = service.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token,
            )

            response = request.execute()

            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                content_details = item.get("contentDetails", {})

                video_info = {
                    "video_id": content_details.get("videoId", ""),
                    "title": snippet.get("title", ""),
                    "channel_name": snippet.get("videoOwnerChannelTitle", ""),
                    "playlist_item_id": item.get("id", ""),
                }
                videos.append(video_info)

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        logger.info(f"Retrieved {len(videos)} videos from playlist {playlist_id}")
        return videos

    except HttpError as e:
        _handle_http_error(e, f"fetching playlist {playlist_id}")


def get_video_details(
    service: Resource,
    video_id: str,
) -> dict[str, str]:
    """
    Get detailed metadata for a specific video.

    Args:
        service: Authenticated YouTube API service object.
        video_id: The YouTube video ID.

    Returns:
        Dict with title, channel, duration, description, published_at.

    Raises:
        VideoError: If the video is not found.
        APIError: For quota or server errors.
    """
    logger.info(f"Fetching details for video: {video_id}")

    try:
        request = service.videos().list(
            part="snippet,contentDetails",
            id=video_id,
        )

        response = request.execute()

        items = response.get("items", [])
        if not items:
            raise VideoError(f"Video not found: {video_id}", video_id=video_id)

        video = items[0]
        snippet = video.get("snippet", {})
        content_details = video.get("contentDetails", {})

        details = {
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "duration": content_details.get("duration", ""),
            "description": snippet.get("description", ""),
            "published_at": snippet.get("publishedAt", ""),
        }

        logger.info(f"Retrieved details for video: {details['title']}")
        return details

    except (VideoError, APIError):
        raise

    except HttpError as e:
        _handle_http_error(e, f"fetching video {video_id}")


def add_to_playlist(
    service: Resource,
    playlist_id: str,
    video_id: str,
) -> str:
    """
    Add a video to a playlist.

    Args:
        service: Authenticated YouTube API service object.
        playlist_id: The target playlist ID.
        video_id: The video ID to add.

    Returns:
        The playlist item ID of the newly added item.

    Raises:
        VideoError: If the video ID is invalid.
        APIError: For quota or server errors.
    """
    logger.info(f"Adding video {video_id} to playlist {playlist_id}")

    try:
        request = service.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id,
                    },
                },
            },
        )

        response = request.execute()
        playlist_item_id = response.get("id", "")

        logger.info(
            f"Successfully added video {video_id} to playlist {playlist_id} "
            f"(playlist_item_id: {playlist_item_id})"
        )
        return playlist_item_id

    except HttpError as e:
        _handle_http_error(e, f"adding video {video_id} to playlist {playlist_id}")


def remove_from_playlist(
    service: Resource,
    playlist_item_id: str,
) -> bool:
    """
    Remove a video from a playlist using the playlist item ID.

    Args:
        service: Authenticated YouTube API service object.
        playlist_item_id: The playlist item ID (not the video ID).

    Returns:
        True if removal was successful.

    Raises:
        APIError: For quota or server errors.
    """
    logger.info(f"Removing playlist item: {playlist_item_id}")

    try:
        request = service.playlistItems().delete(id=playlist_item_id)
        request.execute()

        logger.info(f"Successfully removed playlist item: {playlist_item_id}")
        return True

    except HttpError as e:
        _handle_http_error(e, f"removing playlist item {playlist_item_id}")


def move_video_to_playlist(
    service: Resource,
    video_id: str,
    source_playlist_id: str,
    target_playlist_id: str,
    playlist_item_id: Optional[str] = None,
) -> str:
    """
    Move a video from one playlist to another.

    This performs two operations:
    1. Add the video to the target playlist
    2. Remove it from the source playlist

    Args:
        service: Authenticated YouTube API service object.
        video_id: The video ID to move.
        source_playlist_id: The playlist to remove from.
        target_playlist_id: The playlist to add to.
        playlist_item_id: Optional playlist item ID for removal.

    Returns:
        The new playlist item ID in the target playlist.

    Raises:
        VideoError: If the video is not found in the source playlist.
        APIError: For quota or server errors.
    """
    logger.info(
        f"Moving video {video_id} from {source_playlist_id} to {target_playlist_id}"
    )

    # If playlist_item_id not provided, find it
    if not playlist_item_id:
        logger.info(f"Looking up playlist_item_id for video {video_id}")
        videos = get_playlist_videos(service, source_playlist_id)

        for video in videos:
            if video["video_id"] == video_id:
                playlist_item_id = video["playlist_item_id"]
                break

        if not playlist_item_id:
            raise VideoError(
                f"Video {video_id} not found in playlist {source_playlist_id}",
                video_id=video_id,
            )

    # First, add to target playlist
    new_item_id = add_to_playlist(service, target_playlist_id, video_id)

    # Then, remove from source playlist
    try:
        remove_from_playlist(service, playlist_item_id)
    except (VideoError, APIError) as e:
        logger.warning(
            f"Failed to remove video from source playlist after adding to target. "
            f"Video {video_id} may now exist in both playlists. Error: {e}"
        )
        raise

    logger.info(
        f"Successfully moved video {video_id} to playlist {target_playlist_id}"
    )
    return new_item_id


def _handle_http_error(error: HttpError, context: str) -> None:
    """
    Handle YouTube API HTTP errors and raise appropriate exceptions.

    Args:
        error: The HttpError from the API.
        context: Description of what operation was being performed.

    Raises:
        APIError: For quota, auth, and server errors.
        VideoError: For resource-specific errors (not found, etc.).
    """
    status_code = error.resp.status
    error_reason = ""

    try:
        import json
        error_details = json.loads(error.content.decode("utf-8"))
        errors = error_details.get("error", {}).get("errors", [])
        if errors:
            error_reason = errors[0].get("reason", "")
    except (json.JSONDecodeError, KeyError, AttributeError):
        pass

    logger.error(f"YouTube API error while {context}: {error}")

    # Quota exceeded — account-level (resets at midnight PT)
    if status_code == 403 and error_reason in ("quotaExceeded", "dailyLimitExceeded"):
        raise APIError(
            f"YouTube API quota exceeded while {context}",
            service="YouTube",
            action_required=False,
            user_message="YouTube Daily Quota Exceeded — Pipeline paused. The YouTube API daily limit (10,000 units) has been hit. No action needed — resets at midnight Pacific Time.",
            initial_backoff_minutes=1440,
        )

    # Auth errors — account-level
    if status_code == 401:
        raise APIError(
            f"YouTube API unauthorized while {context}",
            service="YouTube",
            action_required=True,
            user_message="YouTube API Unauthorized — Pipeline paused. The YouTube OAuth credentials may have been revoked. Check the YOUTUBE_REFRESH_TOKEN secret.",
            initial_backoff_minutes=1440,
        )

    # Server errors — account-level (temporary)
    if status_code >= 500:
        raise APIError(
            f"YouTube API server error while {context}",
            service="YouTube",
            action_required=False,
            user_message=f"YouTube API Temporarily Down (HTTP {status_code}) — Pipeline paused. Will retry automatically on next scheduled run.",
            initial_backoff_minutes=30,
        )

    # Not found — video-level
    if status_code == 404 or error_reason == "videoNotFound":
        raise VideoError(f"Resource not found while {context}: {error}")

    # Other errors — treat as video-level
    raise VideoError(f"YouTube API error while {context}: {error}")
