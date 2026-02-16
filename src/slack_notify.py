"""
Slack notification module for sending video summaries.

Uses Slack incoming webhooks to post formatted messages to a channel.
"""

import logging
import os
import requests

logger = logging.getLogger(__name__)


def get_webhook_url() -> str | None:
    """Get Slack webhook URL from environment."""
    return os.environ.get("SLACK_WEBHOOK_URL")


def send_summary_notification(video_data: dict) -> bool:
    """
    Send a formatted video summary notification to Slack.

    Args:
        video_data: Dictionary containing:
            - title (str): Video title
            - channel (str): YouTube channel name
            - duration (str): Video duration
            - url (str): YouTube video URL
            - summary (str): AI-generated summary
            - key_points (str): Bullet-pointed key takeaways

    Returns:
        True if notification sent successfully, False otherwise.
    """
    webhook_url = get_webhook_url()
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not set, skipping notification")
        return False

    title = video_data.get("title", "Untitled")
    channel = video_data.get("channel", "Unknown")
    duration = video_data.get("duration", "Unknown")
    url = video_data.get("url", "")
    summary = video_data.get("summary", "No summary available")
    key_points = video_data.get("key_points", "")

    # Build Slack message using Block Kit for nice formatting
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📺 {title}",
                "emoji": True
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*Channel:* {channel}  |  *Duration:* {duration}"
                }
            ]
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Summary*\n{summary}"
            }
        },
    ]

    # Add key points if available
    if key_points:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Key Points*\n{key_points}"
            }
        })

    # Add video link button
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "Watch Video",
                    "emoji": True
                },
                "url": url,
                "style": "primary"
            }
        ]
    })

    payload = {
        "blocks": blocks,
        "text": f"New video summary: {title}"  # Fallback for notifications
    }

    return _send_slack_message(payload)


def send_error_notification(error_message: str, attempt: int, next_retry_minutes: int) -> bool:
    """
    Send an error notification to Slack with cooldown context.

    Args:
        error_message: Description of the error.
        attempt: Which consecutive failure this is (1 = first failure).
        next_retry_minutes: Minutes until the next retry attempt.

    Returns:
        True if notification sent successfully, False otherwise.
    """
    webhook_url = get_webhook_url()
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not set, skipping error notification")
        return False

    if next_retry_minutes >= 1440:
        retry_text = "24 hours"
    elif next_retry_minutes >= 60:
        hours = next_retry_minutes // 60
        mins = next_retry_minutes % 60
        retry_text = f"{hours}h {mins}m" if mins else f"{hours}h"
    else:
        retry_text = f"{next_retry_minutes} minutes"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "YouTube Summarizer Failed",
                "emoji": True
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Attempt #{attempt}  |  Next retry in *{retry_text}*"
                }
            ]
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Error*\n```{error_message[:1500]}```"
            }
        },
    ]

    if attempt == 1:
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Retries will continue with increasing delays until the issue is resolved."
                }
            ]
        })

    payload = {
        "blocks": blocks,
        "text": f"YouTube Summarizer failed (attempt #{attempt})"
    }

    return _send_slack_message(payload)


def send_recovery_notification(previous_failures: int) -> bool:
    """
    Send a recovery notification after the workflow starts working again.

    Args:
        previous_failures: How many consecutive failures occurred before recovery.

    Returns:
        True if notification sent successfully, False otherwise.
    """
    webhook_url = get_webhook_url()
    if not webhook_url:
        return False

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "YouTube Summarizer Recovered",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"The workflow is running successfully again after *{previous_failures}* consecutive failures."
            }
        },
    ]

    payload = {
        "blocks": blocks,
        "text": f"YouTube Summarizer recovered after {previous_failures} failures"
    }

    return _send_slack_message(payload)


def _send_slack_message(payload: dict) -> bool:
    """Send a payload to the Slack webhook.

    Args:
        payload: Slack message payload with blocks and fallback text.

    Returns:
        True if sent successfully, False otherwise.
    """
    webhook_url = get_webhook_url()
    if not webhook_url:
        return False

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=10
        )

        if response.status_code == 200:
            logger.info("Sent Slack notification")
            return True
        else:
            logger.error(f"Slack webhook error {response.status_code}: {response.text}")
            return False

    except requests.exceptions.Timeout:
        logger.error("Timeout sending Slack notification")
        return False

    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending Slack notification: {e}")
        return False
