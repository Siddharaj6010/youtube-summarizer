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

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=10
        )

        if response.status_code == 200:
            logger.info(f"Sent Slack notification for: {title}")
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
