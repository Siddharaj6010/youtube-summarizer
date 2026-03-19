"""Tests for src/exceptions.py — custom exception hierarchy."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from exceptions import PipelineError, VideoError, APIError


class TestExceptionHierarchy:
    def test_video_error_is_pipeline_error(self):
        e = VideoError("no captions", video_id="vid123")
        assert isinstance(e, PipelineError)
        assert isinstance(e, Exception)

    def test_api_error_is_pipeline_error(self):
        e = APIError("out of credits", service="OpenRouter", action_required=True, user_message="Top up")
        assert isinstance(e, PipelineError)
        assert isinstance(e, Exception)

    def test_video_error_attributes(self):
        e = VideoError("no captions available", video_id="abc123")
        assert e.video_id == "abc123"
        assert str(e) == "no captions available"

    def test_video_error_default_video_id(self):
        e = VideoError("unknown error")
        assert e.video_id == ""

    def test_api_error_attributes(self):
        e = APIError(
            "rate limit",
            service="Supadata",
            action_required=False,
            user_message="Monthly limit reached",
            initial_backoff_minutes=1440,
        )
        assert e.service == "Supadata"
        assert e.action_required is False
        assert e.user_message == "Monthly limit reached"
        assert e.initial_backoff_minutes == 1440
        assert str(e) == "rate limit"

    def test_api_error_default_backoff(self):
        e = APIError("error", service="S", action_required=False, user_message="M")
        assert e.initial_backoff_minutes == 30  # default

    def test_api_error_action_required(self):
        e = APIError("bad key", service="OpenRouter", action_required=True, user_message="Fix key")
        assert e.action_required is True

    def test_can_catch_video_error_as_pipeline_error(self):
        try:
            raise VideoError("test", video_id="v1")
        except PipelineError as e:
            assert e.video_id == "v1"

    def test_can_catch_api_error_as_pipeline_error(self):
        try:
            raise APIError("test", service="S", action_required=False, user_message="M")
        except PipelineError as e:
            assert e.service == "S"
