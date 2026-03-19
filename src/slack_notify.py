"""
Slack notification module for sending video summaries and error alerts.

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
                "text": f"{title}",
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
        # Convert standard markdown bold (**text**) to Slack mrkdwn bold (*text*)
        slack_key_points = key_points.replace("**", "*")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Key Points*\n{slack_key_points}"
            }
        })

    # Add target audience if available
    target_audience = video_data.get("target_audience", "")
    if target_audience:
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*Target Audience:* {target_audience}"
                }
            ]
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


def send_video_skipped_notification(
    title: str, channel: str, url: str, error_msg: str
) -> bool:
    """
    Send a notification when a video is permanently skipped after max retries.

    Args:
        title: Video title.
        channel: YouTube channel name.
        url: YouTube video URL.
        error_msg: The last error message.

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
                "text": "Video Skipped After 3 Failures",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{title}* by {channel} could not be processed after 3 attempts."
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Last Error*\n```{error_msg[:1500]}```"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "You'll need to watch this one directly on YouTube."
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Watch on YouTube",
                        "emoji": True
                    },
                    "url": url,
                    "style": "primary"
                }
            ]
        },
    ]

    payload = {
        "blocks": blocks,
        "text": f"Video skipped: {title} — {error_msg[:200]}"
    }

    return _send_slack_message(payload)


def send_api_error_notification(
    service: str, user_message: str, action_required: bool
) -> bool:
    """
    Send a notification for an API/account-level error.

    Uses color coding:
    - Red circle = requires manual action (top up credits, fix API key)
    - Yellow circle = will auto-resolve (rate limits, server down, monthly resets)

    Args:
        service: Name of the failing service (e.g., "OpenRouter", "Supadata").
        user_message: Clear, actionable message explaining the issue.
        action_required: True if human action is needed.

    Returns:
        True if notification sent successfully, False otherwise.
    """
    webhook_url = get_webhook_url()
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not set, skipping error notification")
        return False

    emoji = ":red_circle:" if action_required else ":large_yellow_circle:"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{service} Error",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} {user_message}"
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Pipeline paused. Will retry on next scheduled run."
                }
            ]
        },
    ]

    payload = {
        "blocks": blocks,
        "text": f"{service} error: {user_message[:200]}"
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
