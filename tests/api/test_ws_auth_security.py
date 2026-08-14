from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from deeptutor.api.routers import auth as auth_router
from deeptutor.multi_user.context import reset_current_user
from deeptutor.services.auth import TokenPayload


@dataclass
class _FakeWebSocket:
    query_params: dict[str, str] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    close_codes: list[int] = field(default_factory=list)

    async def close(self, *, code: int = 1000, reason: str | None = None) -> None:
        _ = reason
        self.close_codes.append(code)


def _payload() -> TokenPayload:
    return TokenPayload(username="alice", role="user", user_id="u_alice")


@pytest.mark.asyncio
async def test_ws_auth_rejects_query_string_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_router, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_router, "decode_token", lambda token: _payload() if token else None)
    ws = _FakeWebSocket(query_params={"token": "secret-in-url"})

    result = await auth_router.ws_require_auth(ws)  # type: ignore[arg-type]

    assert result is auth_router.ws_auth_failed
    assert ws.close_codes == [4001]


@pytest.mark.asyncio
async def test_ws_auth_accepts_http_only_cookie_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_router, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_router, "decode_token", lambda token: _payload() if token else None)
    ws = _FakeWebSocket(cookies={"dt_token": "cookie-secret"})

    user_token: Any = await auth_router.ws_require_auth(ws)  # type: ignore[arg-type]
    try:
        assert user_token is not auth_router.ws_auth_failed
        assert ws.close_codes == []
    finally:
        if user_token is not auth_router.ws_auth_failed:
            reset_current_user(user_token)
