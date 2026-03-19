"""Custom exception hierarchy for the YouTube summarizer pipeline.

Two-tier error system:
- VideoError: Problem with a specific video (retry up to 3 times, then skip)
- APIError: Account/service-level problem (stop pipeline, wait for next run)
"""


class PipelineError(Exception):
    """Base exception for all pipeline errors."""
    pass


class VideoError(PipelineError):
    """Error specific to a single video. Pipeline should skip this video and continue.

    Examples: no captions, video deleted, unparseable LLM response.
    """

    def __init__(self, message: str, video_id: str = ""):
        self.video_id = video_id
        super().__init__(message)


class APIError(PipelineError):
    """Account-level or service-level error. Pipeline should stop immediately.

    Examples: API key invalid, out of credits, quota exceeded, service down.

    Attributes:
        service: Name of the failing service (e.g., "OpenRouter", "Supadata").
        action_required: True if human action is needed; False if it will auto-resolve.
        user_message: Clear, actionable message for Slack notification.
        initial_backoff_minutes: How long to wait before first retry.
            Progression: initial → 3hr → 24hr → 3 days (cap).
    """

    def __init__(
        self,
        message: str,
        service: str,
        action_required: bool,
        user_message: str,
        initial_backoff_minutes: int = 30,
    ):
        self.service = service
        self.action_required = action_required
        self.user_message = user_message
        self.initial_backoff_minutes = initial_backoff_minutes
        super().__init__(message)
