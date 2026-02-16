"""
YouTube Video Summarizer - Main Entry Point

This script orchestrates the entire summarization pipeline:
1. Fetch videos from the "To Summarize" playlist
2. Filter out already-processed videos (tracked in Notion)
3. For each new video: fetch transcript, summarize, save to Notion
4. Move processed videos to the "Summarized" playlist
"""

import os
import sys
import logging
from dotenv import load_dotenv

from youtube import get_youtube_service, get_playlist_videos, get_video_details, move_video_to_playlist
from transcript import get_transcript
from summarizer import summarize_transcript
from notion_db import get_notion_client, get_processed_video_ids, create_summary_page, create_error_page
from slack_notify import send_summary_notification, send_processing_error_notification, send_error_notification, send_recovery_notification
from cooldown import should_skip_run, record_failure, record_success

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


def process_video(youtube_service, notion_client, video: dict, database_id: str) -> bool:
    """Process a single video: fetch transcript, summarize, save to Notion.

    Args:
        youtube_service: Authenticated YouTube API service
        notion_client: Authenticated Notion client
        video: Video data dict with video_id, title, channel_name, playlist_item_id
        database_id: Notion database ID

    Returns:
        True if processing succeeded, False otherwise
    """
    video_id = video["video_id"]
    title = video["title"]
    channel = video["channel_name"]

    logger.info(f"Processing: {title} ({video_id})")

    # Get full video details
    try:
        details = get_video_details(youtube_service, video_id)
        duration = format_duration(details.get("duration", ""))
    except Exception as e:
        logger.warning(f"Could not get video details: {e}")
        duration = "Unknown"

    # Fetch transcript
    logger.info(f"  Fetching transcript...")
    transcript = get_transcript(video_id)

    video_data = {
        "video_id": video_id,
        "title": title,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "channel": channel,
        "duration": duration,
    }

    if transcript is None:
        # No transcript available - create error page but don't move video
        error_msg = "No transcript available (captions disabled or not found)"
        logger.warning(f"  {error_msg}: {title}")
        send_processing_error_notification(title, video_data["url"], error_msg)
        try:
            create_error_page(notion_client, database_id, video_data, error_msg)
            logger.info(f"  Created error entry in Notion")
        except Exception as e:
            logger.error(f"  Failed to create Notion error page: {e}")
        return False

    # Summarize with Claude
    logger.info(f"  Summarizing with Gemini 3 Flash...")
    summary_result = summarize_transcript(title, channel, transcript)

    if "error" in summary_result:
        error_msg = f"Summarization failed: {summary_result['error']}"
        logger.error(f"  {error_msg}")
        send_processing_error_notification(title, video_data["url"], error_msg)
        try:
            create_error_page(notion_client, database_id, video_data, error_msg)
        except Exception as e:
            logger.error(f"  Failed to create Notion error page: {e}")
        return False

    # Save to Notion
    logger.info(f"  Saving to Notion...")

    # Convert key_points list to bullet-point string for Notion
    key_points = summary_result.get("key_points", [])
    if isinstance(key_points, list):
        key_points_str = "\n".join(f"• {point}" for point in key_points)
    else:
        key_points_str = key_points or ""

    video_data.update({
        "summary": summary_result.get("summary", ""),
        "key_points": key_points_str,
        "target_audience": summary_result.get("target_audience", ""),
    })

    try:
        page_id = create_summary_page(notion_client, database_id, video_data)
        logger.info(f"  Created Notion page: {page_id}")

        # Send Slack notification
        logger.info(f"  Sending Slack notification...")
        if send_summary_notification(video_data):
            logger.info(f"  Slack notification sent")
        else:
            logger.warning(f"  Slack notification skipped or failed")

        return True
    except Exception as e:
        logger.error(f"  Failed to create Notion page: {e}")
        return False


def _handle_fatal_error(error_message: str) -> None:
    """Record a fatal error with cooldown and notify via Slack, then exit."""
    state = record_failure(error_message)
    failures = state["consecutive_failures"]
    backoff = state["backoff_minutes"]

    send_error_notification(error_message, attempt=failures, next_retry_minutes=backoff)
    sys.exit(1)


def main():
    """Main entry point for the YouTube Video Summarizer."""
    # Load environment variables
    load_dotenv()

    # --- Cooldown check ---
    # Skip this run if we're in an active cooldown from previous failures
    skip, cooldown_state = should_skip_run()
    if skip:
        logger.info("Skipping run due to active cooldown. Exiting cleanly.")
        sys.exit(0)

    # Get required environment variables
    input_playlist = os.environ.get("YOUTUBE_INPUT_PLAYLIST")
    output_playlist = os.environ.get("YOUTUBE_OUTPUT_PLAYLIST")
    database_id = os.environ.get("NOTION_DATABASE_ID")

    # Validate configuration
    missing = []
    if not input_playlist:
        missing.append("YOUTUBE_INPUT_PLAYLIST")
    if not output_playlist:
        missing.append("YOUTUBE_OUTPUT_PLAYLIST")
    if not database_id:
        missing.append("NOTION_DATABASE_ID")

    if missing:
        error_msg = f"Missing required environment variables: {', '.join(missing)}"
        logger.error(error_msg)
        _handle_fatal_error(error_msg)

    logger.info("=" * 60)
    logger.info("YouTube Video Summarizer")
    logger.info("=" * 60)

    # Initialize services
    logger.info("Initializing YouTube service...")
    try:
        youtube_service = get_youtube_service()
    except Exception as e:
        error_msg = f"Failed to initialize YouTube service: {e}"
        logger.error(error_msg)
        _handle_fatal_error(error_msg)

    logger.info("Initializing Notion client...")
    try:
        notion_client = get_notion_client()
    except Exception as e:
        error_msg = f"Failed to initialize Notion client: {e}"
        logger.error(error_msg)
        _handle_fatal_error(error_msg)

    # Get videos from input playlist
    logger.info(f"Fetching videos from input playlist...")
    try:
        playlist_videos = get_playlist_videos(youtube_service, input_playlist)
        logger.info(f"Found {len(playlist_videos)} videos in input playlist")
    except Exception as e:
        error_msg = f"Failed to fetch playlist videos: {e}"
        logger.error(error_msg)
        _handle_fatal_error(error_msg)

    if not playlist_videos:
        logger.info("No videos in input playlist. Nothing to do.")
        record_success()
        return

    # Get already-processed video IDs from Notion
    logger.info("Checking for already-processed videos...")
    try:
        processed_ids = get_processed_video_ids(notion_client, database_id)
        logger.info(f"Found {len(processed_ids)} already-processed videos in Notion")
    except Exception as e:
        error_msg = f"Failed to fetch processed video IDs: {e}"
        logger.error(error_msg)
        _handle_fatal_error(error_msg)

    # Filter to only new videos
    new_videos = [v for v in playlist_videos if v["video_id"] not in processed_ids]
    logger.info(f"Found {len(new_videos)} new videos to process")

    if not new_videos:
        logger.info("All videos already processed. Nothing to do.")
        record_success()
        return

    # Process each new video
    processed_count = 0
    error_count = 0

    for video in new_videos:
        try:
            success = process_video(youtube_service, notion_client, video, database_id)

            if success:
                # Move video to output playlist
                logger.info(f"  Moving to output playlist...")
                try:
                    move_video_to_playlist(
                        youtube_service,
                        video["video_id"],
                        input_playlist,
                        output_playlist,
                        playlist_item_id=video.get("playlist_item_id")
                    )
                    logger.info(f"  Moved successfully")
                    processed_count += 1
                except Exception as e:
                    logger.error(f"  Failed to move video: {e}")
                    error_count += 1
            else:
                error_count += 1

        except Exception as e:
            logger.error(f"Unexpected error processing {video['video_id']}: {e}")
            error_count += 1

    # Summary
    logger.info("=" * 60)
    logger.info("Processing complete!")
    logger.info(f"  Successfully processed: {processed_count}")
    logger.info(f"  Errors: {error_count}")
    logger.info("=" * 60)

    # --- Cooldown: record outcome ---
    if error_count > 0 and processed_count == 0:
        # Complete failure - activate/extend cooldown
        _handle_fatal_error(f"All {error_count} video(s) failed to process")
    else:
        # At least partial success - clear cooldown
        previous_state = record_success()
        if previous_state:
            prev_failures = previous_state.get("consecutive_failures", 0)
            send_recovery_notification(prev_failures)
            logger.info(f"Sent recovery notification (was failing for {prev_failures} runs)")

        if error_count > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
