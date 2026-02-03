"""
Notion API client module for saving video summaries.

This module handles:
- Creating and managing a Notion client connection
- Querying the database for already-processed videos (deduplication)
- Creating summary pages for successfully processed videos
- Creating error pages for videos that failed processing
"""

import os
import logging
from datetime import datetime, timezone
from notion_client import Client

logger = logging.getLogger(__name__)


def get_notion_client() -> Client:
    """
    Create and return a Notion client using the API key from environment variables.

    Returns:
        A configured Notion Client instance.

    Raises:
        KeyError: If NOTION_API_KEY environment variable is not set.

    Example:
        >>> client = get_notion_client()
        >>> # Use client for database operations
    """
    api_key = os.environ["NOTION_API_KEY"]
    return Client(auth=api_key)


def get_processed_video_ids(client: Client, database_id: str) -> set[str]:
    """
    Query the Notion database for all video IDs that have already been processed.

    This is used for deduplication - we skip videos that are already in the database.
    Handles pagination to retrieve all entries even in large databases.

    Args:
        client: An authenticated Notion client.
        database_id: The ID of the Notion database to query.

    Returns:
        A set of video IDs (strings) that exist in the database.

    Example:
        >>> client = get_notion_client()
        >>> processed = get_processed_video_ids(client, "abc123...")
        >>> if "dQw4w9WgXcQ" in processed:
        ...     print("Video already processed, skipping")
    """
    video_ids: set[str] = set()
    has_more = True
    start_cursor = None

    while has_more:
        # Build query parameters
        query_params = {"database_id": database_id}
        if start_cursor:
            query_params["start_cursor"] = start_cursor

        # Query the database
        response = client.databases.query(**query_params)

        # Extract video IDs from results
        for page in response.get("results", []):
            properties = page.get("properties", {})
            video_id_prop = properties.get("Video ID", {})
            rich_text = video_id_prop.get("rich_text", [])

            if rich_text:
                video_id = rich_text[0].get("text", {}).get("content", "")
                if video_id:
                    video_ids.add(video_id)

        # Check for pagination
        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")

    logger.info(f"Found {len(video_ids)} already processed videos in database")
    return video_ids


def create_summary_page(client: Client, database_id: str, video_data: dict) -> str:
    """
    Create a new page in the Notion database for a successfully summarized video.

    Args:
        client: An authenticated Notion client.
        database_id: The ID of the Notion database.
        video_data: Dictionary containing video information with keys:
            - video_id (str): YouTube video ID
            - title (str): Video title
            - url (str): Full URL to the video
            - channel (str): Channel name
            - summary (str): AI-generated summary
            - key_points (str): Bullet points of key takeaways
            - target_audience (str): Who the video is for (optional)
            - duration (str): Video length (e.g., "10:30")

    Returns:
        The ID of the created Notion page.

    Example:
        >>> video_data = {
        ...     "video_id": "dQw4w9WgXcQ",
        ...     "title": "Never Gonna Give You Up",
        ...     "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
        ...     "channel": "Rick Astley",
        ...     "summary": "A classic 80s pop song...",
        ...     "key_points": "- Catchy melody\\n- Iconic music video",
        ...     "duration": "3:33"
        ... }
        >>> page_id = create_summary_page(client, database_id, video_data)
    """
    # Get current date in ISO format
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Build properties for the new page
    properties = {
        "Title": {
            "title": [{"text": {"content": video_data.get("title", "Untitled")}}]
        },
        "Video ID": {
            "rich_text": [{"text": {"content": video_data.get("video_id", "")}}]
        },
        "URL": {"url": video_data.get("url", "")},
        "Channel": {
            "rich_text": [{"text": {"content": video_data.get("channel", "")}}]
        },
        "Summary": {
            "rich_text": [{"text": {"content": _truncate_text(video_data.get("summary", ""), 2000)}}]
        },
        "Key Points": {
            "rich_text": [{"text": {"content": _truncate_text(video_data.get("key_points", ""), 2000)}}]
        },
        "Duration": {
            "rich_text": [{"text": {"content": video_data.get("duration", "")}}]
        },
        "Added": {"date": {"start": current_date}},
        "Status": {"select": {"name": "Summarized"}},
    }

    # Create the page
    response = client.pages.create(
        parent={"database_id": database_id}, properties=properties
    )

    page_id = response["id"]
    logger.info(f"Created summary page for video: {video_data.get('title', 'Unknown')} (ID: {page_id})")
    return page_id


def create_error_page(
    client: Client, database_id: str, video_data: dict, error: str
) -> str:
    """
    Create a page in the Notion database for a video that failed processing.

    This is useful for tracking videos that couldn't be summarized (e.g., no transcript
    available, API errors, etc.) so they can be reviewed or retried later.

    Args:
        client: An authenticated Notion client.
        database_id: The ID of the Notion database.
        video_data: Dictionary containing video information with keys:
            - video_id (str): YouTube video ID
            - title (str): Video title
            - url (str): Full URL to the video
            - channel (str): Channel name (optional)
            - duration (str): Video length (optional)
        error: A description of what went wrong.

    Returns:
        The ID of the created Notion page.

    Example:
        >>> video_data = {
        ...     "video_id": "abc123",
        ...     "title": "Some Video",
        ...     "url": "https://youtube.com/watch?v=abc123",
        ...     "channel": "Some Channel"
        ... }
        >>> page_id = create_error_page(client, database_id, video_data, "No transcript available")
    """
    # Get current date in ISO format
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Build properties for the error page
    properties = {
        "Title": {
            "title": [{"text": {"content": video_data.get("title", "Untitled")}}]
        },
        "Video ID": {
            "rich_text": [{"text": {"content": video_data.get("video_id", "")}}]
        },
        "URL": {"url": video_data.get("url", "")},
        "Channel": {
            "rich_text": [{"text": {"content": video_data.get("channel", "")}}]
        },
        "Summary": {
            "rich_text": [{"text": {"content": f"Error: {error}"}}]
        },
        "Key Points": {"rich_text": [{"text": {"content": ""}}]},
        "Duration": {
            "rich_text": [{"text": {"content": video_data.get("duration", "")}}]
        },
        "Added": {"date": {"start": current_date}},
        "Status": {"select": {"name": "Error"}},
    }

    # Create the page
    response = client.pages.create(
        parent={"database_id": database_id}, properties=properties
    )

    page_id = response["id"]
    logger.warning(
        f"Created error page for video: {video_data.get('title', 'Unknown')} "
        f"(ID: {page_id}) - Error: {error}"
    )
    return page_id


def _truncate_text(text: str, max_length: int) -> str:
    """
    Truncate text to a maximum length, adding ellipsis if truncated.

    Notion rich_text properties have a 2000 character limit per text block.
    This helper ensures we don't exceed that limit.

    Args:
        text: The text to potentially truncate.
        max_length: Maximum allowed length.

    Returns:
        The original text if within limit, otherwise truncated with "..." suffix.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
