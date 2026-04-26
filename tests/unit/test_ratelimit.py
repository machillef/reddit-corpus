"""Tests for reddit.ratelimit.observe."""

from __future__ import annotations

from reddit_corpus.reddit import ratelimit
from tests.fakes.praw_fakes import FakeAuth, FakeReddit


def test_observe_reads_limits_from_auth():
    client = FakeReddit(
        auth=FakeAuth(limits={"remaining": 87, "used": 13, "reset_timestamp": 1700})
    )
    state = ratelimit.observe(client)
    assert state.remaining == 87
    assert state.used == 13
    # `reset_timestamp` is converted to seconds-from-now via the provided clock.
    assert state.reset_timestamp == 1700


def test_observe_handles_missing_fields_gracefully():
    """If PRAW hasn't seen a request yet, .limits values may be None."""
    client = FakeReddit(
        auth=FakeAuth(limits={"remaining": None, "used": None, "reset_timestamp": None})
    )
    state = ratelimit.observe(client)
    assert state.remaining is None
    assert state.used is None
    assert state.reset_timestamp is None


def test_should_pause_when_below_threshold():
    state = ratelimit.RateLimitState(remaining=5, used=95, reset_timestamp=None)
    assert ratelimit.should_pause(state, threshold=10) is True


def test_should_pause_at_or_above_threshold():
    state = ratelimit.RateLimitState(remaining=10, used=90, reset_timestamp=None)
    assert ratelimit.should_pause(state, threshold=10) is False


def test_should_pause_when_remaining_unknown_does_not_panic():
    """Unknown rate-limit state should not block ingest — assume room until proven otherwise."""
    state = ratelimit.RateLimitState(remaining=None, used=None, reset_timestamp=None)
    assert ratelimit.should_pause(state, threshold=10) is False
