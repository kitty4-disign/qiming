from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from deeptutor.api import main as api_main
from deeptutor.api.routers.auth import require_auth
from deeptutor.services.path_service import PathService


def _artifact(service: PathService, relative_name: str = "artifact.txt") -> Path:
    path = service.get_task_workspace("chat", "turn-1") / "exec" / relative_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(relative_name, encoding="utf-8")
    return path


def test_outputs_route_is_authenticated() -> None:
    routes = [
        route
        for route in api_main.app.routes
        if isinstance(route, APIRoute) and route.path == "/api/outputs/{path:path}"
    ]
    assert len(routes) == 1
    route = routes[0]
    assert {"GET", "HEAD"}.issubset(route.methods)
    assert any(dep.call is require_auth for dep in route.dependant.dependencies)


@pytest.mark.asyncio
async def test_outputs_resolve_against_request_scoped_path_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_a = PathService(tmp_path / "tenant-a")
    service_b = PathService(tmp_path / "tenant-b")
    artifact_a = _artifact(service_a)
    artifact_b = _artifact(service_b)
    relative_path = "workspace/chat/chat/turn-1/exec/artifact.txt"

    monkeypatch.setattr(api_main, "get_path_service", lambda: service_a)
    response_a = await api_main.serve_public_output(relative_path)
    assert Path(response_a.path).resolve() == artifact_a.resolve()

    monkeypatch.setattr(api_main, "get_path_service", lambda: service_b)
    response_b = await api_main.serve_public_output(relative_path)
    assert Path(response_b.path).resolve() == artifact_b.resolve()
    assert Path(response_a.path).resolve() != Path(response_b.path).resolve()


@pytest.mark.asyncio
async def test_outputs_reject_private_or_missing_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PathService(tmp_path / "tenant-a")
    private_file = _artifact(service, "private.json")
    monkeypatch.setattr(api_main, "get_path_service", lambda: service)

    with pytest.raises(api_main.HTTPException) as exc_info:
        await api_main.serve_public_output(
            "workspace/chat/chat/turn-1/exec/private.json"
        )

    assert private_file.exists()
    assert exc_info.value.status_code == 404
