"""
Gemini 3 Flash Summarization Module

This module provides functionality to summarize YouTube video transcripts
using the Gemini 3 Flash model via the OpenRouter API.
"""

import os
import re
import time
from typing import Optional

import openai
from openai import OpenAI


# Constants
MODEL_ID = "google/gemini-3-flash-preview"
MAX_TOKENS = 1024
MAX_TRANSCRIPT_LENGTH = 500_000  # Gemini has 1M token context, can handle much more
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0


def get_openrouter_client() -> OpenAI:
    """
    Create and return an OpenAI client configured for OpenRouter.

    Returns:
        OpenAI: Configured OpenAI client pointing at OpenRouter.

    Raises:
        ValueError: If OPENROUTER_API_KEY environment variable is not set.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY environment variable is not set. "
            "Please set it with your OpenRouter API key."
        )
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


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
    Parse the model response to extract summary, key points, and target audience.

    Args:
        response_text: Raw response text from the model.

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
    Summarize a YouTube video transcript using Gemini 3 Flash via OpenRouter.

    This function sends the transcript to Gemini 3 Flash for summarization
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
            client = get_openrouter_client()

            response = client.chat.completions.create(
                model=MODEL_ID,
                max_tokens=MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            # Extract text from response
            response_text = response.choices[0].message.content

            # Parse and return the structured response
            return _parse_response(response_text)

        except openai.RateLimitError as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(backoff)
                backoff *= 2  # Exponential backoff
            continue

        except openai.APIError as e:
            # Return error dict for API errors
            return {
                "summary": "",
                "key_points": [],
                "target_audience": "",
                "error": f"OpenRouter API error: {str(e)}"
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
