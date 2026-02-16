"""Tests for src/cooldown.py — exponential backoff cooldown logic."""

import sys
import os
import json
import tempfile
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
    BACKOFF_MINUTES,
)


@pytest.fixture
def state_file(tmp_path):
    """Provide a temporary cooldown state file path and patch the env."""
    path = str(tmp_path / "cooldown_state.json")
    with patch.dict(os.environ, {"COOLDOWN_STATE_PATH": path}):
        yield path


class TestGetBackoffMinutes:
    def test_zero_failures(self):
        assert get_backoff_minutes(0) == 0

    def test_first_failure(self):
        assert get_backoff_minutes(1) == BACKOFF_MINUTES[0]  # 15

    def test_second_failure(self):
        assert get_backoff_minutes(2) == BACKOFF_MINUTES[1]  # 30

    def test_third_failure(self):
        assert get_backoff_minutes(3) == BACKOFF_MINUTES[2]  # 120

    def test_caps_at_last_value(self):
        cap = BACKOFF_MINUTES[-1]
        assert get_backoff_minutes(100) == cap
        assert get_backoff_minutes(len(BACKOFF_MINUTES) + 5) == cap


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
            json.dump({"last_error": "oops"}, f)  # no consecutive_failures
        assert load_state() is None


class TestShouldSkipRun:
    def test_no_state_file_does_not_skip(self, state_file):
        skip, state = should_skip_run()
        assert skip is False
        assert state is None

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
        assert state["consecutive_failures"] == 3

    def test_expired_cooldown_does_not_skip(self, state_file):
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        save_state({
            "consecutive_failures": 3,
            "next_retry_after": past,
        })
        skip, state = should_skip_run()
        assert skip is False


class TestRecordFailure:
    def test_first_failure(self, state_file):
        state = record_failure("Token expired")
        assert state["consecutive_failures"] == 1
        assert state["last_error"] == "Token expired"
        assert state["backoff_minutes"] == BACKOFF_MINUTES[0]
        assert "next_retry_after" in state

    def test_increments_failures(self, state_file):
        record_failure("Error 1")
        state = record_failure("Error 2")
        assert state["consecutive_failures"] == 2
        assert state["backoff_minutes"] == BACKOFF_MINUTES[1]

    def test_truncates_long_error(self, state_file):
        long_error = "x" * 1000
        state = record_failure(long_error)
        assert len(state["last_error"]) <= 500

    def test_state_persisted_to_file(self, state_file):
        record_failure("persist test")
        loaded = load_state()
        assert loaded["consecutive_failures"] == 1


class TestRecordSuccess:
    def test_clears_state(self, state_file):
        record_failure("some error")
        record_failure("still broken")
        result = record_success()
        assert result is not None
        assert result["consecutive_failures"] == 2

        loaded = load_state()
        assert loaded["consecutive_failures"] == 0

    def test_returns_none_when_no_prior_failures(self, state_file):
        result = record_success()
        assert result is None

    def test_returns_none_when_already_clean(self, state_file):
        save_state({"consecutive_failures": 0})
        result = record_success()
        assert result is None
