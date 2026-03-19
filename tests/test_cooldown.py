"""Tests for src/cooldown.py — API-level error cooldown with error-specific backoff."""

import sys
import os
import json
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cooldown import (
    load_state,
    save_state,
    get_backoff_minutes,
    should_skip_run,
    record_failure,
    record_success,
    BACKOFF_STEPS_MINUTES,
)


@pytest.fixture
def state_file(tmp_path):
    """Provide a temporary cooldown state file path and patch the env."""
    path = str(tmp_path / "cooldown_state.json")
    with patch.dict(os.environ, {"COOLDOWN_STATE_PATH": path}):
        yield path


class TestGetBackoffMinutes:
    def test_zero_failures(self):
        assert get_backoff_minutes(0, 30) == 0

    def test_first_failure_uses_initial_backoff(self):
        assert get_backoff_minutes(1, 30) == 30
        assert get_backoff_minutes(1, 1440) == 1440

    def test_second_failure_uses_first_step(self):
        assert get_backoff_minutes(2, 30) == BACKOFF_STEPS_MINUTES[0]  # 180 (3hr)

    def test_third_failure_uses_second_step(self):
        assert get_backoff_minutes(3, 30) == BACKOFF_STEPS_MINUTES[1]  # 1440 (24hr)

    def test_fourth_failure_uses_third_step(self):
        assert get_backoff_minutes(4, 30) == BACKOFF_STEPS_MINUTES[2]  # 4320 (3 days)

    def test_caps_at_last_step(self):
        cap = BACKOFF_STEPS_MINUTES[-1]
        assert get_backoff_minutes(10, 30) == cap
        assert get_backoff_minutes(100, 30) == cap

    def test_high_initial_backoff_still_progresses(self):
        # Monthly quota: starts at 24hr, then 3hr->24hr->3days
        assert get_backoff_minutes(1, 1440) == 1440  # 24hr
        assert get_backoff_minutes(2, 1440) == 180    # 3hr (step 2)
        # Wait, this doesn't make sense — 3hr is less than 24hr.
        # But the progression is: initial -> 3hr -> 24hr -> 3 days
        # For monthly quota (initial=24hr), step 2 is 3hr which is LESS.
        # The design says "only the 1st step can be decided by error type"
        # so step 2 is always 3hr regardless. This is correct per spec.


class TestLoadSaveState:
    def test_load_returns_none_when_no_file(self, state_file):
        assert load_state() is None

    def test_save_and_load_roundtrip(self, state_file):
        state = {"consecutive_failures": 2, "last_error": "test"}
        save_state(state)
        loaded = load_state()
        assert loaded["consecutive_failures"] == 2
        assert loaded["last_error"] == "test"

    def test_load_returns_none_for_invalid_json(self, state_file):
        with open(state_file, "w") as f:
            f.write("not valid json {{{")
        assert load_state() is None

    def test_load_returns_none_for_missing_field(self, state_file):
        with open(state_file, "w") as f:
            json.dump({"last_error": "oops"}, f)
        assert load_state() is None


class TestShouldSkipRun:
    def test_no_state_file_does_not_skip(self, state_file):
        skip, state = should_skip_run()
        assert skip is False

    def test_zero_failures_does_not_skip(self, state_file):
        save_state({"consecutive_failures": 0})
        skip, state = should_skip_run()
        assert skip is False

    def test_active_cooldown_skips(self, state_file):
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        save_state({
            "consecutive_failures": 3,
            "next_retry_after": future,
        })
        skip, state = should_skip_run()
        assert skip is True

    def test_expired_cooldown_does_not_skip(self, state_file):
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        save_state({
            "consecutive_failures": 3,
            "next_retry_after": past,
        })
        skip, state = should_skip_run()
        assert skip is False

    def test_invalid_timestamp_does_not_skip(self, state_file):
        save_state({
            "consecutive_failures": 3,
            "next_retry_after": "not-a-date",
        })
        skip, state = should_skip_run()
        assert skip is False


class TestRecordFailure:
    def test_first_failure_uses_initial_backoff(self, state_file):
        state = record_failure("Server error", initial_backoff_minutes=30)
        assert state["consecutive_failures"] == 1
        assert state["backoff_minutes"] == 30
        assert state["initial_backoff_minutes"] == 30

    def test_first_failure_with_high_initial(self, state_file):
        state = record_failure("Monthly limit", initial_backoff_minutes=1440)
        assert state["consecutive_failures"] == 1
        assert state["backoff_minutes"] == 1440

    def test_increments_failures_and_progresses_backoff(self, state_file):
        record_failure("Error 1", initial_backoff_minutes=30)
        state = record_failure("Error 2", initial_backoff_minutes=30)
        assert state["consecutive_failures"] == 2
        assert state["backoff_minutes"] == BACKOFF_STEPS_MINUTES[0]  # 180 (3hr)

    def test_truncates_long_error(self, state_file):
        long_error = "x" * 1000
        state = record_failure(long_error, initial_backoff_minutes=30)
        assert len(state["last_error"]) <= 500

    def test_state_persisted_to_file(self, state_file):
        record_failure("persist test", initial_backoff_minutes=30)
        loaded = load_state()
        assert loaded["consecutive_failures"] == 1


class TestRecordSuccess:
    def test_clears_state(self, state_file):
        record_failure("error", initial_backoff_minutes=30)
        record_failure("still broken", initial_backoff_minutes=30)
        result = record_success()
        assert result is not None
        assert result["consecutive_failures"] == 2

        loaded = load_state()
        assert loaded["consecutive_failures"] == 0

    def test_returns_none_when_no_prior_failures(self, state_file):
        assert record_success() is None

    def test_returns_none_when_already_clean(self, state_file):
        save_state({"consecutive_failures": 0})
        assert record_success() is None
