"""
YouTube transcript fetching module.

Uses Supadata API to fetch video transcripts (YouTube's auto-generated or manual captions).
Only uses mode=native to fetch existing captions (1 credit per video).
Does NOT use AI generation to avoid high credit costs.
"""

import logging
import os
import requests

logger = logging.getLogger(__name__)

SUPADATA_API_URL = "https://api.supadata.ai/v1/youtube/transcript"


def _get_api_key() -> str | None:
    """Get Supadata API key from environment."""
    return os.environ.get("SUPADATA_API_KEY")


def get_transcript(video_id: str) -> str | None:
    """
    Fetch the transcript for a YouTube video as plain text.

    Uses Supadata API with mode=native to fetch existing captions only.
    This includes YouTube's auto-generated captions.

    Args:
        video_id: The YouTube video ID (e.g., 'dQw4w9WgXcQ')

    Returns:
        The transcript as a single string,
        or None if no transcript is available.

    Example:
        >>> transcript = get_transcript('dQw4w9WgXcQ')
        >>> if transcript:
        ...     print(transcript[:100])
    """
    api_key = _get_api_key()
    if not api_key:
        logger.error("SUPADATA_API_KEY environment variable not set")
        return None

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

            logger.warning(f"No transcript content in response for video {video_id}")
            return None

        elif response.status_code == 404:
            logger.info(f"No transcript available for video {video_id}")
            return None

        elif response.status_code == 400:
            error_data = response.json() if response.text else {}
            error_msg = error_data.get("error", "Bad request")
            logger.warning(f"Bad request for video {video_id}: {error_msg}")
            return None

        elif response.status_code == 401:
            logger.error("Invalid Supadata API key")
            return None

        elif response.status_code == 429:
            logger.error("Supadata API rate limit exceeded")
            return None

        else:
            logger.error(f"Supadata API error {response.status_code}: {response.text}")
            return None

    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching transcript for video {video_id}")
        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching transcript for {video_id}: {e}")
        return None

    except Exception as e:
        logger.error(f"Unexpected error fetching transcript for {video_id}: {e}")
        return None


def get_transcript_with_timestamps(video_id: str) -> list[dict] | None:
    """
    Fetch the transcript for a YouTube video with timestamp information.

    Note: Supadata returns timestamps in the response when available.

    Args:
        video_id: The YouTube video ID (e.g., 'dQw4w9WgXcQ')

    Returns:
        A list of transcript segments, each containing:
        - text (str): The transcript text for this segment
        - start (float): Start time in seconds
        - duration (float): Duration of the segment in seconds

        Returns None if no transcript is available.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.error("SUPADATA_API_KEY environment variable not set")
        return None

    try:
        response = requests.get(
            SUPADATA_API_URL,
            params={
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "mode": "native",
            },
            headers={
                "x-api-key": api_key,
            },
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()

            segments = data.get("segments") or data.get("transcript")
            if segments and isinstance(segments, list):
                result = []
                for segment in segments:
                    if isinstance(segment, dict):
                        result.append({
                            "text": segment.get("text", ""),
                            "start": segment.get("start", 0),
                            "duration": segment.get("duration", 0),
                        })
                if result:
                    return result

            return None

        else:
            return None

    except Exception as e:
        logger.error(f"Error fetching transcript with timestamps for {video_id}: {e}")
        return None
