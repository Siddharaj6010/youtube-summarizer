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


class YouTubeAPIError(Exception):
    """Base exception for YouTube API errors."""
    pass


class QuotaExceededError(YouTubeAPIError):
    """Raised when YouTube API quota is exceeded."""
    pass


class InvalidVideoError(YouTubeAPIError):
    """Raised when a video ID is invalid or video not found."""
    pass


class AuthenticationError(YouTubeAPIError):
    """Raised when authentication fails."""
    pass


def get_youtube_service() -> Resource:
    """
    Build and return an authenticated YouTube API service using refresh token.

    Uses OAuth 2.0 credentials from environment variables to create a YouTube
    API service client. The refresh token is used to obtain access tokens
    automatically without browser interaction.

    Environment variables required:
        - YOUTUBE_CLIENT_ID: OAuth 2.0 client ID
        - YOUTUBE_CLIENT_SECRET: OAuth 2.0 client secret
        - YOUTUBE_REFRESH_TOKEN: OAuth 2.0 refresh token

    Returns:
        Resource: Authenticated YouTube API service object.

    Raises:
        AuthenticationError: If credentials are missing or invalid.

    Example:
        >>> service = get_youtube_service()
        >>> # Now use service to make API calls
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
        raise AuthenticationError(
            f"Missing required environment variables: {', '.join(missing_vars)}"
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
        raise AuthenticationError(f"Authentication failed: {e}") from e


def get_playlist_videos(
    service: Resource,
    playlist_id: str,
) -> list[dict[str, str]]:
    """
    Get all video information from a YouTube playlist.

    Fetches all videos from the specified playlist, handling pagination
    automatically to retrieve complete results.

    Args:
        service: Authenticated YouTube API service object.
        playlist_id: The YouTube playlist ID (e.g., 'PLxxxxxx').

    Returns:
        List of dicts, each containing:
            - video_id: The YouTube video ID
            - title: Video title
            - channel_name: Name of the channel that uploaded the video
            - playlist_item_id: The playlist item ID (needed for removal)

    Raises:
        QuotaExceededError: If API quota is exceeded.
        YouTubeAPIError: For other API errors.

    Example:
        >>> service = get_youtube_service()
        >>> videos = get_playlist_videos(service, "PLxxxxxxx")
        >>> for video in videos:
        ...     print(f"{video['title']} by {video['channel_name']}")
    """
    videos = []
    next_page_token = None

    logger.info(f"Fetching videos from playlist: {playlist_id}")

    try:
        while True:
            # Build the request
            request = service.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=50,  # Maximum allowed by API
                pageToken=next_page_token,
            )

            response = request.execute()

            # Process each item in the response
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

            # Check for more pages
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
        Dict containing:
            - title: Video title
            - channel: Channel name
            - duration: Video duration in ISO 8601 format (e.g., 'PT4M13S')
            - description: Video description
            - published_at: Publication date in ISO 8601 format

    Raises:
        InvalidVideoError: If the video ID is invalid or video not found.
        QuotaExceededError: If API quota is exceeded.
        YouTubeAPIError: For other API errors.

    Example:
        >>> service = get_youtube_service()
        >>> details = get_video_details(service, "dQw4w9WgXcQ")
        >>> print(f"Title: {details['title']}, Duration: {details['duration']}")
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
            logger.warning(f"Video not found: {video_id}")
            raise InvalidVideoError(f"Video not found: {video_id}")

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
        InvalidVideoError: If the video ID is invalid.
        QuotaExceededError: If API quota is exceeded.
        YouTubeAPIError: For other API errors.

    Example:
        >>> service = get_youtube_service()
        >>> item_id = add_to_playlist(service, "PLxxxxxxx", "dQw4w9WgXcQ")
        >>> print(f"Added video with playlist item ID: {item_id}")
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

    Note: This requires the playlist_item_id, not the video_id.
    Use get_playlist_videos() to obtain the playlist_item_id for each video.

    Args:
        service: Authenticated YouTube API service object.
        playlist_item_id: The playlist item ID (not the video ID).

    Returns:
        True if removal was successful.

    Raises:
        QuotaExceededError: If API quota is exceeded.
        YouTubeAPIError: For other API errors.

    Example:
        >>> service = get_youtube_service()
        >>> videos = get_playlist_videos(service, "PLxxxxxxx")
        >>> remove_from_playlist(service, videos[0]["playlist_item_id"])
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

    If the add fails, the video remains in the source playlist.
    If the remove fails after add succeeds, the video will be in both playlists.

    Args:
        service: Authenticated YouTube API service object.
        video_id: The video ID to move.
        source_playlist_id: The playlist to remove from.
        target_playlist_id: The playlist to add to.
        playlist_item_id: Optional playlist item ID for removal. If not provided,
            the function will fetch it from the source playlist.

    Returns:
        The new playlist item ID in the target playlist.

    Raises:
        InvalidVideoError: If the video is not found in the source playlist.
        QuotaExceededError: If API quota is exceeded.
        YouTubeAPIError: For other API errors.

    Example:
        >>> service = get_youtube_service()
        >>> new_item_id = move_video_to_playlist(
        ...     service,
        ...     video_id="dQw4w9WgXcQ",
        ...     source_playlist_id="PLsource",
        ...     target_playlist_id="PLtarget",
        ... )
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
            raise InvalidVideoError(
                f"Video {video_id} not found in playlist {source_playlist_id}"
            )

    # First, add to target playlist
    new_item_id = add_to_playlist(service, target_playlist_id, video_id)

    # Then, remove from source playlist
    try:
        remove_from_playlist(service, playlist_item_id)
    except YouTubeAPIError as e:
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
        QuotaExceededError: If API quota is exceeded.
        InvalidVideoError: If a video or resource is not found.
        YouTubeAPIError: For other API errors.
    """
    status_code = error.resp.status
    error_reason = ""

    try:
        # Try to extract the error reason from the response
        import json
        error_details = json.loads(error.content.decode("utf-8"))
        errors = error_details.get("error", {}).get("errors", [])
        if errors:
            error_reason = errors[0].get("reason", "")
    except (json.JSONDecodeError, KeyError, AttributeError):
        pass

    logger.error(f"YouTube API error while {context}: {error}")

    # Handle quota exceeded
    if status_code == 403 and error_reason in ("quotaExceeded", "dailyLimitExceeded"):
        raise QuotaExceededError(
            f"YouTube API quota exceeded. Please try again later. "
            f"Error while {context}: {error}"
        )

    # Handle not found
    if status_code == 404 or error_reason == "videoNotFound":
        raise InvalidVideoError(f"Resource not found while {context}: {error}")

    # Handle other errors
    raise YouTubeAPIError(f"API error while {context}: {error}")
