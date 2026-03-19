"""
YouTube Video Summarizer - Main Entry Point

This script orchestrates the entire summarization pipeline:
1. Fetch videos from the "To Summarize" playlist
2. Filter out already-processed videos (tracked in Notion)
3. For each new video: fetch transcript, summarize, save to Notion
4. Move processed videos to the "Summarized" playlist

Error handling uses a two-tier system:
- VideoError: Problem with a specific video (retry up to 3 times, then skip)
- APIError: Account/service-level problem (stop pipeline immediately)
"""

import os
import sys
import logging
from dotenv import load_dotenv

from youtube import get_youtube_service, get_playlist_videos, get_video_details, move_video_to_playlist
from transcript import get_transcript
from summarizer import summarize_transcript
from notion_db import (
    get_notion_client, get_processed_video_ids, create_summary_page,
    increment_retry_count, mark_video_skipped, MAX_RETRIES,
)
from slack_notify import send_summary_notification, send_video_skipped_notification, send_api_error_notification
from cooldown import should_skip_run, record_failure, record_success
from exceptions import VideoError, APIError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def format_duration(duration_iso: str) -> str:
    """Convert ISO 8601 duration to human-readable format.

    Args:
        duration_iso: Duration in ISO 8601 format (e.g., "PT1H30M45S")

    Returns:
        Human-readable duration (e.g., "1:30:45")
    """
    if not duration_iso:
        return "Unknown"

    # Remove PT prefix
    duration = duration_iso.replace("PT", "")

    hours = 0
    minutes = 0
    seconds = 0

    if "H" in duration:
        hours, duration = duration.split("H")
        hours = int(hours)
    if "M" in duration:
        minutes, duration = duration.split("M")
        minutes = int(minutes)
    if "S" in duration:
        seconds = duration.replace("S", "")
        seconds = int(seconds)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"


def _validate_env_vars() -> tuple[str, str, str]:
    """Validate required environment variables.

    Returns:
        Tuple of (input_playlist, output_playlist, database_id).

    Raises:
        APIError: If any required env vars are missing.
    """
    input_playlist = os.environ.get("YOUTUBE_INPUT_PLAYLIST")
    output_playlist = os.environ.get("YOUTUBE_OUTPUT_PLAYLIST")
    database_id = os.environ.get("NOTION_DATABASE_ID")

    missing = []
    if not input_playlist:
        missing.append("YOUTUBE_INPUT_PLAYLIST")
    if not output_playlist:
        missing.append("YOUTUBE_OUTPUT_PLAYLIST")
    if not database_id:
        missing.append("NOTION_DATABASE_ID")

    if missing:
        raise APIError(
            f"Missing required environment variables: {', '.join(missing)}",
            service="Configuration",
            action_required=True,
            user_message=f"Missing Environment Variables — Pipeline paused. Missing secrets: {', '.join(missing)}. Add them in GitHub repository settings.",
            initial_backoff_minutes=1440,
        )

    return input_playlist, output_playlist, database_id


def process_video(youtube_service, notion_client, video: dict, database_id: str) -> bool:
    """Process a single video: fetch transcript, summarize, save to Notion.

    Lets VideoError and APIError propagate to the caller for proper handling.

    Args:
        youtube_service: Authenticated YouTube API service
        notion_client: Authenticated Notion client
        video: Video data dict with video_id, title, channel_name, playlist_item_id
        database_id: Notion database ID

    Returns:
        True if processing succeeded.

    Raises:
        VideoError: If this specific video can't be processed.
        APIError: If an account/service-level error occurs.
    """
    video_id = video["video_id"]
    title = video["title"]
    channel = video["channel_name"]

    logger.info(f"Processing: {title} ({video_id})")

    # Get full video details (non-critical — default to Unknown on video-level errors)
    try:
        details = get_video_details(youtube_service, video_id)
        duration = format_duration(details.get("duration", ""))
    except VideoError:
        duration = "Unknown"
    # Note: APIError from get_video_details will propagate up

    # Fetch transcript — raises VideoError or APIError
    logger.info(f"  Fetching transcript...")
    transcript = get_transcript(video_id)

    # Summarize — raises VideoError or APIError
    logger.info(f"  Summarizing with Gemini 3 Flash...")
    summary_result = summarize_transcript(title, channel, transcript)

    # Build video_data for Notion
    key_points = summary_result.get("key_points", [])
    if isinstance(key_points, list):
        key_points_str = "\n".join(f"\u2022 {point}" for point in key_points)
    else:
        key_points_str = key_points or ""

    video_data = {
        "video_id": video_id,
        "title": title,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "channel": channel,
        "duration": duration,
        "summary": summary_result.get("summary", ""),
        "key_points": key_points_str,
        "target_audience": summary_result.get("target_audience", ""),
    }

    # Save to Notion — APIError propagates, other errors are video-level
    logger.info(f"  Saving to Notion...")
    page_id = create_summary_page(notion_client, database_id, video_data)
    logger.info(f"  Created Notion page: {page_id}")

    # Send Slack notification (non-critical)
    logger.info(f"  Sending Slack notification...")
    if send_summary_notification(video_data):
        logger.info(f"  Slack notification sent")
    else:
        logger.warning(f"  Slack notification skipped or failed")

    return True


def _handle_api_error(e: APIError) -> None:
    """Handle an API-level error: record cooldown, notify (first time only), exit."""
    state = record_failure(str(e), e.initial_backoff_minutes)
    # Only send Slack notification on the first failure (not on subsequent cooldown retries)
    if state["consecutive_failures"] == 1:
        send_api_error_notification(e.service, e.user_message, e.action_required)
    else:
        logger.info(
            f"Suppressing Slack notification (failure #{state['consecutive_failures']}, "
            f"already notified on first failure)"
        )


def main():
    """Main entry point for the YouTube Video Summarizer."""
    load_dotenv()

    # --- Cooldown check ---
    skip, cooldown_state = should_skip_run()
    if skip:
        logger.info("Skipping run due to active cooldown. Exiting cleanly.")
        sys.exit(0)

    logger.info("=" * 60)
    logger.info("YouTube Video Summarizer")
    logger.info("=" * 60)

    # --- Startup: validate config and initialize services ---
    try:
        input_playlist, output_playlist, database_id = _validate_env_vars()
        logger.info("Initializing YouTube service...")
        youtube_service = get_youtube_service()
        logger.info("Initializing Notion client...")
        notion_client = get_notion_client()
    except APIError as e:
        logger.error(f"Startup failed: {e}")
        _handle_api_error(e)
        sys.exit(0)

    # --- Fetch and filter videos ---
    try:
        logger.info(f"Fetching videos from input playlist...")
        playlist_videos = get_playlist_videos(youtube_service, input_playlist)
        logger.info(f"Found {len(playlist_videos)} videos in input playlist")
    except APIError as e:
        logger.error(f"Failed to fetch playlist: {e}")
        _handle_api_error(e)
        sys.exit(0)

    if not playlist_videos:
        logger.info("No videos in input playlist. Nothing to do.")
        record_success()
        return

    try:
        logger.info("Checking for already-processed videos...")
        processed_ids = get_processed_video_ids(notion_client, database_id)
        logger.info(f"Found {len(processed_ids)} already-processed/skipped videos in Notion")
    except APIError as e:
        logger.error(f"Failed to check processed videos: {e}")
        _handle_api_error(e)
        sys.exit(0)

    new_videos = [v for v in playlist_videos if v["video_id"] not in processed_ids]
    logger.info(f"Found {len(new_videos)} new videos to process")

    if not new_videos:
        logger.info("All videos already processed. Nothing to do.")
        record_success()
        return

    # --- Process each video ---
    processed_count = 0
    skipped_count = 0
    error_count = 0

    for video in new_videos:
        video_id = video["video_id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            success = process_video(youtube_service, notion_client, video, database_id)

            if success:
                # Move video to output playlist
                logger.info(f"  Moving to output playlist...")
                try:
                    move_video_to_playlist(
                        youtube_service,
                        video_id,
                        input_playlist,
                        output_playlist,
                        playlist_item_id=video.get("playlist_item_id")
                    )
                    logger.info(f"  Moved successfully")
                    processed_count += 1
                except VideoError as e:
                    logger.warning(f"  Failed to move video (video-level): {e}")
                    processed_count += 1

        except APIError as e:
            # Account-level error: stop the entire pipeline with cooldown
            logger.error(f"API error ({e.service}): {e}")
            _handle_api_error(e)
            logger.info(f"Pipeline stopped. Processed {processed_count} videos before error.")
            sys.exit(0)

        except VideoError as e:
            # Video-specific error: increment retry, maybe skip
            logger.warning(f"Video error for {video_id}: {e}")
            error_count += 1

            video_data = {
                "video_id": video_id,
                "title": video["title"],
                "url": video_url,
                "channel": video["channel_name"],
                "duration": "",
            }

            new_count = increment_retry_count(
                notion_client, database_id, video_data, str(e)
            )

            if new_count >= MAX_RETRIES:
                mark_video_skipped(notion_client, database_id, video_id)
                send_video_skipped_notification(
                    video["title"],
                    video["channel_name"],
                    video_url,
                    str(e),
                )
                skipped_count += 1
                logger.info(f"  Video {video_id} skipped after {MAX_RETRIES} failures")

        except Exception as e:
            # Unexpected error: treat as video-level
            logger.error(f"Unexpected error for {video_id}: {e}")
            error_count += 1

    # --- Summary ---
    logger.info("=" * 60)
    logger.info("Processing complete!")
    logger.info(f"  Successfully processed: {processed_count}")
    logger.info(f"  Errors (will retry): {error_count - skipped_count}")
    logger.info(f"  Skipped (gave up): {skipped_count}")
    logger.info("=" * 60)

    # Clear cooldown on any success (even partial)
    if processed_count > 0:
        record_success()


if __name__ == "__main__":
    main()
