"""
YouTube transcript fetching module.

Uses Supadata API to fetch video transcripts (YouTube's auto-generated or manual captions).
Only uses mode=native to fetch existing captions (1 credit per video).
Does NOT use AI generation to avoid high credit costs.
"""

import logging
import os
import requests

from exceptions import VideoError, APIError

logger = logging.getLogger(__name__)

SUPADATA_API_URL = "https://api.supadata.ai/v1/youtube/transcript"


def _get_api_key() -> str | None:
    """Get Supadata API key from environment."""
    return os.environ.get("SUPADATA_API_KEY")


def get_transcript(video_id: str) -> str:
    """
    Fetch the transcript for a YouTube video as plain text.

    Uses Supadata API with mode=native to fetch existing captions only.
    This includes YouTube's auto-generated captions.

    Args:
        video_id: The YouTube video ID (e.g., 'dQw4w9WgXcQ')

    Returns:
        The transcript as a single string.

    Raises:
        VideoError: If the specific video has no transcript available.
        APIError: If there's an account-level issue (auth, quota, server down).
    """
    api_key = _get_api_key()
    if not api_key:
        raise APIError(
            "SUPADATA_API_KEY not set",
            service="Supadata",
            action_required=True,
            user_message="SUPADATA_API_KEY is missing — Pipeline paused. Add the SUPADATA_API_KEY secret in GitHub repository settings.",
            initial_backoff_minutes=1440,
        )

    try:
        response = requests.get(
            SUPADATA_API_URL,
            params={
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "mode": "native",  # Only fetch existing captions (1 credit)
            },
            headers={
                "x-api-key": api_key,
            },
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()

            # Extract transcript content
            content = data.get("content")
            if content:
                logger.info(f"Successfully fetched transcript for video {video_id}")
                return content

            # Sometimes content is in segments
            segments = data.get("segments") or data.get("transcript")
            if segments and isinstance(segments, list):
                text_parts = []
                for segment in segments:
                    if isinstance(segment, dict):
                        text_parts.append(segment.get("text", ""))
                    elif isinstance(segment, str):
                        text_parts.append(segment)
                if text_parts:
                    logger.info(f"Successfully fetched transcript for video {video_id}")
                    return " ".join(text_parts)

            raise VideoError(
                f"Transcript response was empty for video {video_id}",
                video_id=video_id,
            )

        elif response.status_code == 404:
            raise VideoError(
                f"No captions/transcript available for video {video_id}",
                video_id=video_id,
            )

        elif response.status_code == 400:
            error_data = response.json() if response.text else {}
            error_msg = error_data.get("error", "Bad request")
            raise VideoError(
                f"Bad request for video {video_id}: {error_msg}",
                video_id=video_id,
            )

        elif response.status_code == 401:
            raise APIError(
                "Invalid Supadata API key",
                service="Supadata",
                action_required=True,
                user_message="Supadata API Key Invalid — Pipeline paused. The SUPADATA_API_KEY secret in GitHub needs to be updated.",
                initial_backoff_minutes=1440,
            )

        elif response.status_code == 429:
            raise APIError(
                "Supadata rate limit / quota exceeded",
                service="Supadata",
                action_required=False,
                user_message="Supadata Monthly Limit Reached — Pipeline paused. The monthly transcript requests have been used up. No action needed — this will auto-resolve when the new month starts.",
                initial_backoff_minutes=1440,
            )

        elif response.status_code >= 500:
            raise APIError(
                f"Supadata server error: {response.status_code}",
                service="Supadata",
                action_required=False,
                user_message=f"Supadata API Temporarily Down (HTTP {response.status_code}) — Pipeline paused. Will retry automatically on next scheduled run.",
                initial_backoff_minutes=30,
            )

        else:
            raise VideoError(
                f"Supadata API error {response.status_code} for video {video_id}: {response.text}",
                video_id=video_id,
            )

    except (VideoError, APIError):
        raise  # Don't catch our own exceptions

    except requests.exceptions.Timeout:
        raise APIError(
            f"Timeout fetching transcript for video {video_id}",
            service="Supadata",
            action_required=False,
            user_message="Supadata API Timeout — Pipeline paused. The API is not responding. Will retry automatically on next scheduled run.",
            initial_backoff_minutes=30,
        )

    except requests.exceptions.RequestException as e:
        raise APIError(
            f"Network error fetching transcript: {e}",
            service="Supadata",
            action_required=False,
            user_message="Supadata Connection Error — Pipeline paused. Could not connect to the Supadata API. Will retry automatically on next scheduled run.",
            initial_backoff_minutes=30,
        )

    except Exception as e:
        raise VideoError(
            f"Unexpected error fetching transcript for {video_id}: {e}",
            video_id=video_id,
        )
