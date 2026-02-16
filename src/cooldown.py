"""
Cooldown manager for handling repeated failures with exponential backoff.

Persists state to a JSON file (cached between GitHub Actions runs) to prevent:
1. Spamming Slack with repeated error notifications
2. Wasting API calls when a persistent error (e.g., expired token) is present
3. Unnecessary workflow runs during known outages

Backoff schedule: 15min -> 30min -> 2hrs -> 8hrs -> 24hrs (capped)
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Backoff intervals in minutes for each consecutive failure
# After the last entry, the schedule stays at the final value (24 hours)
BACKOFF_MINUTES = [15, 30, 120, 480, 1440]

# Default path for cooldown state file (overridable via env var)
DEFAULT_STATE_PATH = "/tmp/cooldown_state.json"


def _get_state_path() -> str:
    return os.environ.get("COOLDOWN_STATE_PATH", DEFAULT_STATE_PATH)


def load_state() -> dict | None:
    """Load cooldown state from the JSON file.

    Returns:
        State dict if file exists and is valid, None otherwise.
    """
    path = _get_state_path()
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r") as f:
            state = json.load(f)
        # Validate required fields
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


def get_backoff_minutes(consecutive_failures: int) -> int:
    """Get the backoff interval in minutes for the given failure count.

    Args:
        consecutive_failures: Number of consecutive failures so far.

    Returns:
        Minutes to wait before next retry.
    """
    if consecutive_failures <= 0:
        return 0
    index = min(consecutive_failures - 1, len(BACKOFF_MINUTES) - 1)
    return BACKOFF_MINUTES[index]


def should_skip_run() -> tuple[bool, dict | None]:
    """Check if the current run should be skipped due to active cooldown.

    Returns:
        Tuple of (should_skip, state). If should_skip is True, the run
        should exit early. State is the current cooldown state (or None).
    """
    state = load_state()
    if state is None or state.get("consecutive_failures", 0) == 0:
        return False, state

    next_retry = state.get("next_retry_after")
    if not next_retry:
        return False, state

    now = datetime.now(timezone.utc)
    retry_time = datetime.fromisoformat(next_retry)

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


def record_failure(error_message: str) -> dict:
    """Record a failure and update the cooldown schedule.

    Args:
        error_message: Description of the error that occurred.

    Returns:
        Updated state dict with new backoff timing.
    """
    state = load_state() or {"consecutive_failures": 0}
    failures = state.get("consecutive_failures", 0) + 1
    backoff = get_backoff_minutes(failures)
    now = datetime.now(timezone.utc)
    next_retry = now + timedelta(minutes=backoff)

    state.update({
        "consecutive_failures": failures,
        "last_failure_time": now.isoformat(),
        "last_error": error_message[:500],  # Truncate long errors
        "next_retry_after": next_retry.isoformat(),
        "backoff_minutes": backoff,
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
        Previous state if there was an active cooldown (for recovery
        notification), None if there was no prior cooldown.
    """
    state = load_state()
    previous_failures = state.get("consecutive_failures", 0) if state else 0

    # Always write a clean state
    clean_state = {"consecutive_failures": 0}
    save_state(clean_state)

    if previous_failures > 0:
        logger.info(
            f"Recovered after {previous_failures} consecutive failures! "
            f"Cooldown cleared."
        )
        return state  # Return old state for recovery notification

    return None
