from __future__ import annotations

import pytest

from deeptutor.api.rate_limit import (
    SlidingWindowRateLimiter,
    check_ws_message_rate_limit,
)


def test_sliding_window_blocks_after_limit_and_recovers() -> None:
    now = [100.0]
    limiter = SlidingWindowRateLimiter(
        limit=2,
        window_seconds=10,
        clock=lambda: now[0],
    )

    assert limiter.check("peer").allowed is True
    assert limiter.check("peer").allowed is True
    denied = limiter.check("peer")
    assert denied.allowed is False
    assert denied.retry_after == 10

    now[0] = 110.01
    assert limiter.check("peer").allowed is True


def test_rate_limiter_isolated_by_key() -> None:
    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60, clock=lambda: 1.0)

    assert limiter.check("alice").allowed is True
    assert limiter.check("alice").allowed is False
    assert limiter.check("bob").allowed is True


def test_rate_limiter_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(limit=0, window_seconds=60)
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(limit=1, window_seconds=0)


def test_ws_expensive_messages_have_separate_tighter_budget() -> None:
    general = SlidingWindowRateLimiter(limit=10, window_seconds=60, clock=lambda: 1.0)
    expensive = SlidingWindowRateLimiter(limit=1, window_seconds=60, clock=lambda: 1.0)

    first, first_scope = check_ws_message_rate_limit(
        general=general,
        expensive=expensive,
        msg_type="start_turn",
    )
    second, second_scope = check_ws_message_rate_limit(
        general=general,
        expensive=expensive,
        msg_type="regenerate",
    )

    assert first.allowed is True
    assert first_scope == "expensive"
    assert second.allowed is False
    assert second_scope == "expensive"


def test_ws_general_budget_applies_to_heartbeats_too() -> None:
    general = SlidingWindowRateLimiter(limit=1, window_seconds=60, clock=lambda: 1.0)
    expensive = SlidingWindowRateLimiter(limit=10, window_seconds=60, clock=lambda: 1.0)

    allowed, scope = check_ws_message_rate_limit(
        general=general,
        expensive=expensive,
        msg_type="ping",
    )
    denied, denied_scope = check_ws_message_rate_limit(
        general=general,
        expensive=expensive,
        msg_type="ping",
    )

    assert allowed.allowed is True
    assert scope == "messages"
    assert denied.allowed is False
    assert denied_scope == "messages"
