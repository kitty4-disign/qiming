from __future__ import annotations

from collections import deque
import json
from typing import Any, Awaitable, Callable

import pytest
from starlette.requests import Request
from starlette.responses import Response

from deeptutor.api import main as api_main
from deeptutor.api.rate_limit import RateLimitDecision, SlidingWindowRateLimiter
from deeptutor.api.routers import auth as auth_router
from deeptutor.api.routers import unified_ws


def _request(path: str = "/api/v1/settings") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("203.0.113.10", 12345),
            "server": ("testserver", 80),
        }
    )


@pytest.mark.asyncio
async def test_http_rate_limit_middleware_returns_429_and_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api_main,
        "check_http_rate_limit",
        lambda _request: RateLimitDecision(
            allowed=False,
            retry_after=7,
            limit=20,
            window_seconds=60,
        ),
    )

    async def call_next(_request: Request) -> Response:
        raise AssertionError("rate-limited requests must not reach the route")

    response = await api_main.enforce_http_rate_limits(_request(), call_next)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "7"
    assert response.headers["X-RateLimit-Limit"] == "20"


class _FakeWebSocket:
    def __init__(self, messages: list[str]) -> None:
        self._messages = deque(messages)
        self.sent: list[dict[str, Any]] = []
        self.close_codes: list[int] = []
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def receive_text(self) -> str:
        if not self._messages:
            raise AssertionError("websocket handler read past supplied test messages")
        return self._messages.popleft()

    async def send_text(self, data: str) -> None:
        self.sent.append(json.loads(data))

    async def close(self, *, code: int = 1000, reason: str | None = None) -> None:
        _ = reason
        self.close_codes.append(code)


@pytest.mark.asyncio
async def test_websocket_invalid_json_spam_is_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def allow_ws(_ws) -> None:
        return None

    monkeypatch.setattr(auth_router, "ws_require_auth", allow_ws)
    monkeypatch.setattr(
        unified_ws,
        "new_ws_limiters",
        lambda: (
            SlidingWindowRateLimiter(limit=1, window_seconds=60, clock=lambda: 1.0),
            SlidingWindowRateLimiter(limit=10, window_seconds=60, clock=lambda: 1.0),
        ),
    )
    ws = _FakeWebSocket(["not-json", "still-not-json"])

    await unified_ws.unified_websocket(ws)  # type: ignore[arg-type]

    assert ws.accepted is True
    assert ws.close_codes == [4008]
    assert ws.sent[0]["content"] == "Invalid JSON."
    assert ws.sent[1]["metadata"]["rate_limited"] is True
    assert ws.sent[1]["metadata"]["rate_limit_scope"] == "messages"
