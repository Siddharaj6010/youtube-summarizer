"""
Gemini 3 Flash Summarization Module

This module provides functionality to summarize YouTube video transcripts
using the Gemini 3 Flash model via the OpenRouter API.
"""

import os
import re

import openai
from openai import OpenAI

from exceptions import VideoError, APIError


# Constants
MODEL_ID = "google/gemini-3-flash-preview"
MAX_TOKENS = 4096
MAX_TRANSCRIPT_LENGTH = 500_000  # Gemini has 1M token context, can handle much more


def get_openrouter_client() -> OpenAI:
    """
    Create and return an OpenAI client configured for OpenRouter.

    Returns:
        OpenAI: Configured OpenAI client pointing at OpenRouter.

    Raises:
        APIError: If OPENROUTER_API_KEY environment variable is not set.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise APIError(
            "OPENROUTER_API_KEY not set",
            service="OpenRouter",
            action_required=True,
            user_message="OpenRouter API Key Missing — Pipeline paused. Add the OPENROUTER_API_KEY secret in GitHub repository settings.",
            initial_backoff_minutes=1440,
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

    Args:
        title: The title of the YouTube video.
        channel: The name of the YouTube channel.
        transcript: The full transcript text of the video.

    Returns:
        dict with 'summary', 'key_points', and 'target_audience' keys.

    Raises:
        VideoError: If the LLM response can't be parsed for this specific video.
        APIError: If there's an account-level issue (auth, credits, rate limit).
    """
    # Truncate transcript if needed
    transcript = _truncate_transcript(transcript)

    # Build the user prompt
    user_prompt = f"""Summarize this YouTube video transcript thoroughly. Your goal is to capture ALL important information so the reader does not need to watch the video.

Title: {title}
Channel: {channel}
Transcript: {transcript}

Provide:
1. A comprehensive summary that covers every major topic, argument, example, and conclusion discussed in the video. Include specific details like names, numbers, tools, techniques, and quotes when mentioned. Write in paragraph form and be thorough — the reader should feel they watched the video after reading this.
2. All key points, insights, and actionable takeaways. Do NOT limit yourself to a small number — include every notable point from the video.
3. Who would find this video useful

Format your response as:
SUMMARY:
[thorough summary covering all major topics discussed — multiple paragraphs are fine]

KEY POINTS:
- [point 1]
- [point 2]
...(include as many points as needed to cover everything important)

TARGET AUDIENCE:
[who would benefit]"""

    system_prompt = "You create thorough, detailed YouTube video summaries that capture all important information so the reader doesn't need to watch the video. You include specific details, examples, names, and numbers rather than vague generalizations."

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
        result = _parse_response(response_text)

        # Check for empty/unparseable response
        if not result["summary"]:
            raise VideoError(
                f"LLM returned unparseable response for '{title}'",
            )

        return result

    except (VideoError, APIError):
        raise  # Don't catch our own exceptions

    except openai.AuthenticationError as e:
        status = getattr(e, "status_code", None)
        if status == 402:
            raise APIError(
                f"OpenRouter payment required: {e}",
                service="OpenRouter",
                action_required=True,
                user_message="OpenRouter API Out of Credits — Pipeline paused. Top up your OpenRouter balance to resume. No videos were affected.",
                initial_backoff_minutes=1440,
            )
        raise APIError(
            f"OpenRouter authentication failed: {e}",
            service="OpenRouter",
            action_required=True,
            user_message="OpenRouter API Key Invalid — Pipeline paused. The OPENROUTER_API_KEY secret in GitHub needs to be updated.",
            initial_backoff_minutes=1440,
        )

    except openai.RateLimitError as e:
        status = getattr(e, "status_code", None)
        if status == 402:
            raise APIError(
                f"OpenRouter payment required: {e}",
                service="OpenRouter",
                action_required=True,
                user_message="OpenRouter API Out of Credits — Pipeline paused. Top up your OpenRouter balance to resume. No videos were affected.",
                initial_backoff_minutes=1440,
            )
        raise APIError(
            f"OpenRouter rate limit: {e}",
            service="OpenRouter",
            action_required=False,
            user_message="OpenRouter Rate Limit Hit — Pipeline paused. Will retry automatically on next scheduled run.",
            initial_backoff_minutes=120,
        )

    except openai.APIError as e:
        status = getattr(e, "status_code", None)
        if status and status >= 500:
            raise APIError(
                f"OpenRouter server error: {e}",
                service="OpenRouter",
                action_required=False,
                user_message=f"OpenRouter API Temporarily Down (HTTP {status}) — Pipeline paused. Will retry automatically on next scheduled run.",
                initial_backoff_minutes=30,
            )
        raise VideoError(f"OpenRouter API error: {e}")

    except Exception as e:
        raise VideoError(f"Unexpected summarization error: {e}")
