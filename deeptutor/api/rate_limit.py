"""Small dependency-free rate limiters for HTTP and WebSocket entry points."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import threading
import time
from typing import Callable, Hashable

from fastapi import Request


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0
    limit: int = 0
    window_seconds: int = 0


class SlidingWindowRateLimiter:
    """Thread-safe in-process sliding-window limiter.

    It intentionally keys requests by the direct socket peer rather than
    trusting forwarding headers. Deployments behind a trusted reverse proxy
    can enforce an additional distributed limit at that proxy; this limiter is
    the application-level backstop and does not treat spoofable headers as
    identity.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("rate limit and window must be positive")
        self.limit = int(limit)
        self.window_seconds = int(window_seconds)
        self._clock = clock
        self._max_keys = max(1, int(max_keys))
        self._events: dict[Hashable, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: Hashable) -> RateLimitDecision:
        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._events.get(key)
            if bucket is None:
                if len(self._events) >= self._max_keys:
                    self._prune_empty_or_old(cutoff)
                if len(self._events) >= self._max_keys:
                    # Bound memory even under connection churn. Evict the
                    # stalest bucket; the peer still immediately starts a new
                    # bounded window rather than growing the map without limit.
                    oldest_key = min(
                        self._events,
                        key=lambda item: (
                            self._events[item][0] if self._events[item] else float("inf")
                        ),
                    )
                    self._events.pop(oldest_key, None)
                bucket = deque()
                self._events[key] = bucket

            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self.limit:
                retry_after = max(1, math.ceil(self.window_seconds - (now - bucket[0])))
                return RateLimitDecision(
                    allowed=False,
                    retry_after=retry_after,
                    limit=self.limit,
                    window_seconds=self.window_seconds,
                )

            bucket.append(now)
            return RateLimitDecision(
                allowed=True,
                limit=self.limit,
                window_seconds=self.window_seconds,
            )

    def _prune_empty_or_old(self, cutoff: float) -> None:
        stale: list[Hashable] = []
        for key, bucket in self._events.items():
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if not bucket:
                stale.append(key)
        for key in stale:
            self._events.pop(key, None)


_HTTP_GENERAL = SlidingWindowRateLimiter(limit=600, window_seconds=60)
_HTTP_AUTH = SlidingWindowRateLimiter(limit=20, window_seconds=60)
_HTTP_EXPENSIVE = SlidingWindowRateLimiter(limit=60, window_seconds=60)

_AUTH_LIMITED_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
}
_EXPENSIVE_PREFIXES = (
    "/api/v1/chat",
    "/api/v1/question",
    "/api/v1/education",
    "/api/v1/learning",
)
_WS_EXPENSIVE_TYPES = frozenset({"message", "start_turn", "regenerate"})


def _peer_key(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _expensive_scope(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    return parts[2] if len(parts) >= 3 else path


def check_http_rate_limit(request: Request) -> RateLimitDecision:
    """Apply a broad endpoint limit plus stricter auth/high-cost request limits."""
    if request.method in {"OPTIONS", "HEAD"}:
        return RateLimitDecision(allowed=True)

    path = request.url.path
    if not path.startswith("/api/"):
        return RateLimitDecision(allowed=True)

    peer = _peer_key(request)
    general = _HTTP_GENERAL.check((peer, path))
    if not general.allowed:
        return general

    if request.method == "POST" and path in _AUTH_LIMITED_PATHS:
        return _HTTP_AUTH.check((peer, path))

    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and path.startswith(
        _EXPENSIVE_PREFIXES
    ):
        return _HTTP_EXPENSIVE.check((peer, _expensive_scope(path)))

    return general


def check_ws_message_rate_limit(
    *,
    general: SlidingWindowRateLimiter,
    expensive: SlidingWindowRateLimiter,
    msg_type: str,
) -> tuple[RateLimitDecision, str]:
    """Return the applicable per-connection WebSocket rate decision and scope."""
    decision = general.check("messages")
    if not decision.allowed:
        return decision, "messages"
    if msg_type in _WS_EXPENSIVE_TYPES:
        return expensive.check("expensive"), "expensive"
    return decision, "messages"


def new_ws_limiters() -> tuple[SlidingWindowRateLimiter, SlidingWindowRateLimiter]:
    """Create per-connection WS limiters: 120 msgs/min, 12 costly turns/min."""
    return (
        SlidingWindowRateLimiter(limit=120, window_seconds=60, max_keys=2),
        SlidingWindowRateLimiter(limit=12, window_seconds=60, max_keys=2),
    )


__all__ = [
    "RateLimitDecision",
    "SlidingWindowRateLimiter",
    "check_http_rate_limit",
    "check_ws_message_rate_limit",
    "new_ws_limiters",
]
