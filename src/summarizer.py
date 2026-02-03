"""
Claude Haiku Summarization Module

This module provides functionality to summarize YouTube video transcripts
using the Claude Haiku model via the Anthropic API.
"""

import os
import re
import time
from typing import Optional

import anthropic
from anthropic import APIError, RateLimitError


# Constants
MODEL_ID = "claude-3-haiku-20240307"
MAX_TOKENS = 1024
MAX_TRANSCRIPT_LENGTH = 100_000  # Truncate to ~100k chars (Haiku has 200k context)
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0


def get_anthropic_client() -> anthropic.Anthropic:
    """
    Create and return an Anthropic client using the API key from environment.

    Returns:
        anthropic.Anthropic: Configured Anthropic client instance.

    Raises:
        ValueError: If ANTHROPIC_API_KEY environment variable is not set.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Please set it with your Anthropic API key."
        )
    return anthropic.Anthropic(api_key=api_key)


def _truncate_transcript(transcript: str) -> str:
    """
    Truncate transcript to fit within context limits if necessary.

    Args:
        transcript: The full transcript text.

    Returns:
        str: Truncated transcript if over limit, otherwise original.
    """
    if len(transcript) <= MAX_TRANSCRIPT_LENGTH:
        return transcript

    # Truncate and add indicator
    truncated = transcript[:MAX_TRANSCRIPT_LENGTH]
    # Try to end at a sentence boundary
    last_period = truncated.rfind(". ")
    if last_period > MAX_TRANSCRIPT_LENGTH * 0.8:  # Only if reasonably close to end
        truncated = truncated[:last_period + 1]

    return truncated + "\n\n[Transcript truncated due to length...]"


def _parse_response(response_text: str) -> dict:
    """
    Parse the Claude response to extract summary, key points, and target audience.

    Args:
        response_text: Raw response text from Claude.

    Returns:
        dict: Parsed response with 'summary', 'key_points', and 'target_audience' keys.
    """
    result = {
        "summary": "",
        "key_points": [],
        "target_audience": ""
    }

    # Extract SUMMARY section
    summary_match = re.search(
        r"SUMMARY:\s*\n(.*?)(?=\n\s*KEY POINTS:|$)",
        response_text,
        re.DOTALL | re.IGNORECASE
    )
    if summary_match:
        result["summary"] = summary_match.group(1).strip()

    # Extract KEY POINTS section
    key_points_match = re.search(
        r"KEY POINTS:\s*\n(.*?)(?=\n\s*TARGET AUDIENCE:|$)",
        response_text,
        re.DOTALL | re.IGNORECASE
    )
    if key_points_match:
        points_text = key_points_match.group(1).strip()
        # Parse bullet points (handle various bullet formats: -, *, •)
        points = re.findall(r"^[\-\*\u2022]\s*(.+)$", points_text, re.MULTILINE)
        result["key_points"] = [point.strip() for point in points if point.strip()]

    # Extract TARGET AUDIENCE section
    audience_match = re.search(
        r"TARGET AUDIENCE:\s*\n(.*)$",
        response_text,
        re.DOTALL | re.IGNORECASE
    )
    if audience_match:
        result["target_audience"] = audience_match.group(1).strip()

    return result


def summarize_transcript(
    title: str,
    channel: str,
    transcript: str
) -> dict:
    """
    Summarize a YouTube video transcript using Claude Haiku.

    This function sends the transcript to Claude Haiku for summarization
    and returns a structured dict with the summary, key points, and
    target audience information.

    Args:
        title: The title of the YouTube video.
        channel: The name of the YouTube channel.
        transcript: The full transcript text of the video.

    Returns:
        dict: A dictionary containing:
            - summary (str): A 2-3 sentence summary of the video.
            - key_points (list[str]): 3-5 key takeaways as bullet points.
            - target_audience (str): Description of who would find this useful.
            - error (str, optional): Error message if summarization failed.

    Example:
        >>> result = summarize_transcript(
        ...     title="Python Tips and Tricks",
        ...     channel="Tech Channel",
        ...     transcript="Today we're going to cover..."
        ... )
        >>> print(result["summary"])
        "This video covers essential Python tips..."
    """
    # Truncate transcript if needed
    transcript = _truncate_transcript(transcript)

    # Build the user prompt
    user_prompt = f"""Summarize this video transcript.

Title: {title}
Channel: {channel}
Transcript: {transcript}

Provide:
1. A 2-3 sentence summary
2. 3-5 key takeaways as bullet points
3. Who would find this video useful

Format your response as:
SUMMARY:
[your summary]

KEY POINTS:
- [point 1]
- [point 2]
...

TARGET AUDIENCE:
[who would benefit]"""

    system_prompt = "You summarize YouTube video transcripts concisely."

    # Implement retry with exponential backoff for rate limits
    last_error: Optional[Exception] = None
    backoff = INITIAL_BACKOFF_SECONDS

    for attempt in range(MAX_RETRIES):
        try:
            client = get_anthropic_client()

            message = client.messages.create(
                model=MODEL_ID,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Extract text from response
            response_text = message.content[0].text

            # Parse and return the structured response
            return _parse_response(response_text)

        except RateLimitError as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(backoff)
                backoff *= 2  # Exponential backoff
            continue

        except APIError as e:
            # Return error dict for API errors
            return {
                "summary": "",
                "key_points": [],
                "target_audience": "",
                "error": f"Anthropic API error: {str(e)}"
            }

        except ValueError as e:
            # Handle missing API key
            return {
                "summary": "",
                "key_points": [],
                "target_audience": "",
                "error": str(e)
            }

        except Exception as e:
            # Catch any other unexpected errors
            return {
                "summary": "",
                "key_points": [],
                "target_audience": "",
                "error": f"Unexpected error: {str(e)}"
            }

    # If we exhausted retries due to rate limits
    return {
        "summary": "",
        "key_points": [],
        "target_audience": "",
        "error": f"Rate limit exceeded after {MAX_RETRIES} retries: {str(last_error)}"
    }
