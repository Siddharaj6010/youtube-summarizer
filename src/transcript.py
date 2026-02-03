"""
YouTube transcript fetching module.

Uses the youtube-transcript-api library to fetch video transcripts.
Handles various error cases gracefully by returning None instead of raising exceptions.
"""

import logging
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

logger = logging.getLogger(__name__)

# Create a single API instance
_api = YouTubeTranscriptApi()


def get_transcript(video_id: str) -> str | None:
    """
    Fetch the transcript for a YouTube video as plain text.

    Args:
        video_id: The YouTube video ID (e.g., 'dQw4w9WgXcQ')

    Returns:
        The transcript as a single string with segments joined by spaces,
        or None if no transcript is available.

    Example:
        >>> transcript = get_transcript('dQw4w9WgXcQ')
        >>> if transcript:
        ...     print(transcript[:100])
    """
    transcript_data = get_transcript_with_timestamps(video_id)

    if transcript_data is None:
        return None

    # Join all text segments into a single string
    text_segments = [segment["text"] for segment in transcript_data]
    return " ".join(text_segments)


def get_transcript_with_timestamps(video_id: str) -> list[dict] | None:
    """
    Fetch the transcript for a YouTube video with timestamp information.

    Args:
        video_id: The YouTube video ID (e.g., 'dQw4w9WgXcQ')

    Returns:
        A list of transcript segments, each containing:
        - text (str): The transcript text for this segment
        - start (float): Start time in seconds
        - duration (float): Duration of the segment in seconds

        Returns None if no transcript is available.

    Example:
        >>> segments = get_transcript_with_timestamps('dQw4w9WgXcQ')
        >>> if segments:
        ...     for seg in segments[:3]:
        ...         print(f"{seg['start']:.1f}s: {seg['text']}")
    """
    try:
        # Fetch transcript (library auto-selects best available)
        transcript = _api.fetch(video_id)
        logger.debug(f"Found transcript for video {video_id}")

        # Convert to list of dicts for compatibility
        return [
            {
                "text": snippet.text,
                "start": snippet.start,
                "duration": snippet.duration,
            }
            for snippet in transcript.snippets
        ]

    except TranscriptsDisabled:
        logger.info(f"Transcripts are disabled for video {video_id}")
        return None

    except NoTranscriptFound:
        logger.info(f"No transcript found for video {video_id}")
        return None

    except VideoUnavailable:
        logger.info(f"Video {video_id} is unavailable")
        return None

    except Exception as e:
        # Catch any other unexpected errors
        logger.error(f"Unexpected error fetching transcript for {video_id}: {e}")
        return None
