"""
Notion API client module for saving video summaries.

This module handles:
- Creating and managing a Notion client connection
- Querying the database for already-processed videos (deduplication)
- Creating summary pages for successfully processed videos
- Tracking retry counts for failed videos
- Marking videos as skipped after max retries
"""

import os
import logging
from datetime import datetime, timezone
from notion_client import Client

from exceptions import APIError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def get_notion_client() -> Client:
    """
    Create and return a Notion client using the API key from environment variables.

    Returns:
        A configured Notion Client instance.

    Raises:
        APIError: If NOTION_API_KEY environment variable is not set.
    """
    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key:
        raise APIError(
            "NOTION_API_KEY not set",
            service="Notion",
            action_required=True,
            user_message="Notion API Key Missing — Pipeline paused. Add the NOTION_API_KEY secret in GitHub repository settings.",
            initial_backoff_minutes=1440,
        )
    return Client(auth=api_key)


def _handle_notion_error(e: Exception, context: str) -> None:
    """Convert Notion API errors to our exception hierarchy.

    Args:
        e: The exception from the Notion client.
        context: What operation was being performed.

    Raises:
        APIError: Always, with appropriate service/action_required/user_message.
    """
    from notion_client import APIResponseError

    if isinstance(e, APIResponseError):
        status = e.status

        if status == 401:
            raise APIError(
                f"Notion unauthorized while {context}",
                service="Notion",
                action_required=True,
                user_message="Notion Integration Disconnected — Pipeline paused. The NOTION_API_KEY may be invalid or the integration was removed. Re-connect it in Notion settings.",
                initial_backoff_minutes=1440,
            )

        if status == 404:
            raise APIError(
                f"Notion database not found while {context}",
                service="Notion",
                action_required=True,
                user_message="Notion Database Not Found — Pipeline paused. The database may have been deleted, or the integration needs to be re-connected to it.",
                initial_backoff_minutes=1440,
            )

        if status == 429:
            raise APIError(
                f"Notion rate limit while {context}",
                service="Notion",
                action_required=False,
                user_message="Notion Rate Limit Hit — Pipeline paused. Will retry automatically on next scheduled run.",
                initial_backoff_minutes=120,
            )

        if status >= 500:
            raise APIError(
                f"Notion server error while {context}",
                service="Notion",
                action_required=False,
                user_message=f"Notion API Temporarily Down (HTTP {status}) — Pipeline paused. Will retry automatically on next scheduled run.",
                initial_backoff_minutes=30,
            )

    # Fallback for unexpected errors
    raise APIError(
        f"Notion error while {context}: {e}",
        service="Notion",
        action_required=False,
        user_message=f"Notion API Error — Pipeline paused. Error: {str(e)[:200]}. Will retry automatically on next scheduled run.",
        initial_backoff_minutes=30,
    )


def get_processed_video_ids(client: Client, database_id: str) -> set[str]:
    """
    Query the Notion database for video IDs that should NOT be processed again.

    Includes videos with Status "Summarized" (done) and "Skipped" (gave up).

    Args:
        client: An authenticated Notion client.
        database_id: The ID of the Notion database to query.

    Returns:
        A set of video IDs (strings) that exist in the database.

    Raises:
        APIError: If the Notion API returns an error.
    """
    video_ids: set[str] = set()
    has_more = True
    start_cursor = None

    try:
        while has_more:
            query_params = {
                "database_id": database_id,
                "filter": {
                    "or": [
                        {"property": "Status", "select": {"equals": "Summarized"}},
                        {"property": "Status", "select": {"equals": "Skipped"}},
                    ]
                },
            }
            if start_cursor:
                query_params["start_cursor"] = start_cursor

            response = client.databases.query(**query_params)

            for page in response.get("results", []):
                properties = page.get("properties", {})
                video_id_prop = properties.get("Video ID", {})
                rich_text = video_id_prop.get("rich_text", [])

                if rich_text:
                    video_id = rich_text[0].get("text", {}).get("content", "")
                    if video_id:
                        video_ids.add(video_id)

            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")
    except Exception as e:
        _handle_notion_error(e, "querying processed video IDs")

    logger.info(f"Found {len(video_ids)} already processed/skipped videos in database")
    return video_ids


def create_summary_page(client: Client, database_id: str, video_data: dict) -> str:
    """
    Create a new page in the Notion database for a successfully summarized video.

    Args:
        client: An authenticated Notion client.
        database_id: The ID of the Notion database.
        video_data: Dictionary containing video information.

    Returns:
        The ID of the created Notion page.

    Raises:
        APIError: If the Notion API returns an error.
    """
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

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

    try:
        response = client.pages.create(
            parent={"database_id": database_id}, properties=properties
        )
    except Exception as e:
        _handle_notion_error(e, "creating summary page")

    page_id = response["id"]
    logger.info(f"Created summary page for video: {video_data.get('title', 'Unknown')} (ID: {page_id})")
    return page_id


def _find_error_page(client: Client, database_id: str, video_id: str) -> dict | None:
    """Find an existing Error page for a video ID.

    Args:
        client: An authenticated Notion client.
        database_id: The ID of the Notion database.
        video_id: The YouTube video ID to search for.

    Returns:
        The Notion page dict if found, None otherwise.
    """
    response = client.databases.query(
        database_id=database_id,
        filter={
            "and": [
                {"property": "Video ID", "rich_text": {"equals": video_id}},
                {"property": "Status", "select": {"equals": "Error"}},
            ]
        },
    )
    results = response.get("results", [])
    return results[0] if results else None


def increment_retry_count(
    client: Client, database_id: str, video_data: dict, error_msg: str
) -> int:
    """
    Record a video processing failure. Creates or updates the error page.

    If an Error page already exists for this video, updates it with the new error
    and increments the retry count. Otherwise creates a new error page with count 1.

    Args:
        client: An authenticated Notion client.
        database_id: The ID of the Notion database.
        video_data: Dict with video_id, title, url, channel, duration.
        error_msg: Description of the error.

    Returns:
        The new retry count after incrementing.

    Raises:
        APIError: If the Notion API returns an error.
    """
    video_id = video_data.get("video_id", "")
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        existing_page = _find_error_page(client, database_id, video_id)

        if existing_page:
            # Get current retry count (default to 0 if property missing or None)
            props = existing_page.get("properties", {})
            retry_prop = props.get("Retry Count", {})
            current_count = retry_prop.get("number") or 0
            new_count = current_count + 1

            # Update existing page
            client.pages.update(
                page_id=existing_page["id"],
                properties={
                    "Summary": {
                        "rich_text": [{"text": {"content": f"Error (attempt {new_count}): {error_msg}"[:2000]}}]
                    },
                    "Retry Count": {"number": new_count},
                },
            )
            logger.info(f"Updated error page for {video_id}: retry {new_count}")
            return new_count

        else:
            # Create new error page with retry count 1
            properties = {
                "Title": {
                    "title": [{"text": {"content": video_data.get("title", "Untitled")}}]
                },
                "Video ID": {
                    "rich_text": [{"text": {"content": video_id}}]
                },
                "URL": {"url": video_data.get("url", "")},
                "Channel": {
                    "rich_text": [{"text": {"content": video_data.get("channel", "")}}]
                },
                "Summary": {
                    "rich_text": [{"text": {"content": f"Error (attempt 1): {error_msg}"[:2000]}}]
                },
                "Key Points": {"rich_text": [{"text": {"content": ""}}]},
                "Duration": {
                    "rich_text": [{"text": {"content": video_data.get("duration", "")}}]
                },
                "Added": {"date": {"start": current_date}},
                "Status": {"select": {"name": "Error"}},
                "Retry Count": {"number": 1},
            }

            client.pages.create(
                parent={"database_id": database_id}, properties=properties
            )
            logger.info(f"Created error page for {video_id}: retry 1")
            return 1

    except APIError:
        raise
    except Exception as e:
        # Don't let retry tracking errors crash the pipeline
        # Return a high count to be safe (triggers skip rather than infinite retry)
        logger.error(f"Failed to update retry count for {video_id}: {e}")
        return MAX_RETRIES


def mark_video_skipped(client: Client, database_id: str, video_id: str) -> None:
    """
    Mark a video as permanently skipped after hitting max retries.

    Args:
        client: An authenticated Notion client.
        database_id: The ID of the Notion database.
        video_id: The YouTube video ID.
    """
    try:
        existing_page = _find_error_page(client, database_id, video_id)
        if existing_page:
            client.pages.update(
                page_id=existing_page["id"],
                properties={
                    "Status": {"select": {"name": "Skipped"}},
                },
            )
            logger.info(f"Marked video {video_id} as Skipped")
        else:
            logger.warning(f"No error page found for {video_id} to mark as Skipped")
    except APIError:
        raise
    except Exception as e:
        logger.error(f"Failed to mark {video_id} as Skipped: {e}")


def _truncate_text(text: str, max_length: int) -> str:
    """
    Truncate text to a maximum length, adding ellipsis if truncated.

    Notion rich_text properties have a 2000 character limit per text block.

    Args:
        text: The text to potentially truncate.
        max_length: Maximum allowed length.

    Returns:
        The original text if within limit, otherwise truncated with "..." suffix.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
