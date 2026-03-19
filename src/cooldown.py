"""
Cooldown manager for API-level errors.

Only used for Bucket 2 (account/service-level) errors, NOT for video-level errors.
Persists state to a JSON file cached between GitHub Actions runs.

Backoff progression: initial (error-specific) -> 3hr -> 24hr -> 3 days (cap)
The initial backoff is set by the error type (e.g., 30min for 5xx, 24hr for quota).

Sends one Slack notification on first occurrence, then silences until recovery.
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Backoff steps after the initial (error-specific) step.
# Progression: initial -> 3hr -> 24hr -> 3 days (cap)
BACKOFF_STEPS_MINUTES = [180, 1440, 4320]

# Default path for cooldown state file (overridable via env var)
DEFAULT_STATE_PATH = "/tmp/cooldown_state.json"


def _get_state_path() -> str:
    return os.environ.get("COOLDOWN_STATE_PATH", DEFAULT_STATE_PATH)


def load_state() -> dict | None:
    """Load cooldown state from the JSON file."""
    path = _get_state_path()
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r") as f:
            state = json.load(f)
        if "consecutive_failures" not in state:
            return None
        return state
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Could not read cooldown state: {e}")
        return None


def save_state(state: dict) -> None:
    """Save cooldown state to the JSON file."""
    path = _get_state_path()
    try:
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
    except IOError as e:
        logger.error(f"Could not write cooldown state: {e}")


def get_backoff_minutes(consecutive_failures: int, initial_backoff: int) -> int:
    """Get the backoff interval for the given failure count.

    Progression: initial -> 3hr -> 24hr -> 3 days (cap)

    Args:
        consecutive_failures: Number of consecutive failures (1-based).
        initial_backoff: The first step's backoff in minutes (error-specific).

    Returns:
        Minutes to wait before next retry.
    """
    if consecutive_failures <= 0:
        return 0
    if consecutive_failures == 1:
        return initial_backoff

    # Steps after the first: index into BACKOFF_STEPS_MINUTES
    step_index = min(consecutive_failures - 2, len(BACKOFF_STEPS_MINUTES) - 1)
    return BACKOFF_STEPS_MINUTES[step_index]


def should_skip_run() -> tuple[bool, dict | None]:
    """Check if the current run should be skipped due to active cooldown.

    Returns:
        Tuple of (should_skip, state).
    """
    state = load_state()
    if state is None or state.get("consecutive_failures", 0) == 0:
        return False, state

    next_retry = state.get("next_retry_after")
    if not next_retry:
        return False, state

    now = datetime.now(timezone.utc)
    try:
        retry_time = datetime.fromisoformat(next_retry)
    except ValueError:
        logger.warning(f"Invalid next_retry_after timestamp: {next_retry}")
        return False, state

    if now < retry_time:
        wait_remaining = retry_time - now
        minutes_left = int(wait_remaining.total_seconds() / 60)
        logger.info(
            f"Cooldown active: {state['consecutive_failures']} consecutive failures. "
            f"Next retry in {minutes_left} minutes (at {next_retry})"
        )
        return True, state

    logger.info(
        f"Cooldown expired. Retrying after {state['consecutive_failures']} "
        f"consecutive failures..."
    )
    return False, state


def record_failure(error_message: str, initial_backoff_minutes: int) -> dict:
    """Record an API-level failure and set the cooldown.

    Args:
        error_message: Description of the error.
        initial_backoff_minutes: First-step backoff (from APIError).

    Returns:
        Updated state dict.
    """
    state = load_state() or {"consecutive_failures": 0}
    failures = state.get("consecutive_failures", 0) + 1
    backoff = get_backoff_minutes(failures, initial_backoff_minutes)
    now = datetime.now(timezone.utc)
    next_retry = now + timedelta(minutes=backoff)

    state.update({
        "consecutive_failures": failures,
        "last_failure_time": now.isoformat(),
        "last_error": error_message[:500],
        "next_retry_after": next_retry.isoformat(),
        "backoff_minutes": backoff,
        "initial_backoff_minutes": initial_backoff_minutes,
    })

    save_state(state)
    logger.info(
        f"Recorded failure #{failures}. Next retry after {backoff} minutes "
        f"(at {next_retry.strftime('%Y-%m-%d %H:%M UTC')})"
    )
    return state


def record_success() -> dict | None:
    """Clear cooldown state after a successful run.

    Returns:
        Previous state if there was an active cooldown, None otherwise.
    """
    state = load_state()
    previous_failures = state.get("consecutive_failures", 0) if state else 0

    clean_state = {"consecutive_failures": 0}
    save_state(clean_state)

    if previous_failures > 0:
        logger.info(
            f"Recovered after {previous_failures} consecutive failures! "
            f"Cooldown cleared."
        )
        return state

    return None
