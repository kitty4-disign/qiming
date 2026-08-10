from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import sys
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def preflight():
    path = ROOT / "scripts" / "k12_preflight.py"
    spec = importlib.util.spec_from_file_location("k12_preflight_strict_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_report_prints_on_windows_gbk_console(preflight, monkeypatch):
    output = io.BytesIO()
    console = io.TextIOWrapper(output, encoding="gbk", errors="strict")
    monkeypatch.setattr(sys, "stdout", console)
    report = preflight.PreflightReport()
    report.add("后端", True, required=True)
    report.add("可选能力", False, required=False, suggestion="按需安装")

    report.print()
    console.flush()

    rendered = output.getvalue().decode("gbk")
    assert "[PASS]" in rendered
    assert "[WARN]" in rendered


@pytest.mark.parametrize(
    "error",
    [TimeoutError("timed out"), urllib.error.URLError("connection refused")],
)
def test_http_get_handles_timeout_and_connection_refused(preflight, monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(preflight.urllib.request, "urlopen", fail)
    code, detail = preflight._http_get("http://127.0.0.1:1", timeout=0.01)
    assert code is None
    assert detail


def test_backend_and_frontend_require_real_health(preflight, monkeypatch):
    def healthy(url: str, timeout: float = 3.0):
        if url.endswith(":8001/"):
            return 200, '{"message":"Welcome to DeepTutor API"}'
        if url.endswith("/education"):
            return 200, "education page"
        if url.endswith("/api/v1/education/catalog"):
            return 200, "{}"
        raise AssertionError(url)

    monkeypatch.setattr(preflight, "_http_get", healthy)
    report = preflight.PreflightReport()
    state = preflight.check_ports(report, 8001, 3782)
    assert state == {"backend_online": True, "frontend_online": True}
    assert all(item.passed for item in report.results)

    monkeypatch.setattr(
        preflight,
        "_http_get",
        lambda url, timeout=3.0: (500, "error"),
    )
    report = preflight.PreflightReport()
    state = preflight.check_ports(report, 8001, 3782)
    assert state == {"backend_online": False, "frontend_online": False}
    assert not any(item.passed for item in report.results)


def test_websocket_failure_is_required_failure(preflight, monkeypatch):
    monkeypatch.setattr(preflight, "_http_get", lambda url, timeout=3.0: (200, "ok"))
    monkeypatch.setattr(
        preflight,
        "_ws_handshake",
        lambda *args, **kwargs: (False, "connection refused"),
    )
    report = preflight.PreflightReport()
    preflight.check_api_health(report, 8001, True)
    assert report.results[0].passed is False
    assert report.results[0].required is True


def test_model_checks_require_live_probes(preflight, monkeypatch):
    catalog = {
        "services": {
            "llm": {
                "active_model_id": "chat-id",
                "profiles": [{"models": [{"id": "chat-id"}]}],
            },
            "embedding": {
                "active_model_id": "embedding-id",
                "profiles": [{"models": [{"id": "embedding-id"}]}],
            },
        }
    }
    monkeypatch.setattr(preflight, "_load_model_catalog", lambda: (catalog, None))
    monkeypatch.setattr(preflight, "_run_probe", lambda probe: "live")
    report = preflight.PreflightReport()
    preflight.check_model_config(report)
    assert [item.name for item in report.results] == [
        "LLM Provider",
        "Embedding Provider",
    ]
    assert all(item.passed for item in report.results)

    monkeypatch.setattr(
        preflight,
        "_run_probe",
        lambda probe: (_ for _ in ()).throw(TimeoutError("provider timeout")),
    )
    report = preflight.PreflightReport()
    preflight.check_model_config(report)
    assert not any(item.passed for item in report.results)


def test_kb_status_and_retrieval_use_temp_windows_paths(preflight, monkeypatch, tmp_path):
    kb_root = tmp_path / "knowledge bases"
    for name in preflight.K12_KB_NAMES:
        (kb_root / name / "raw").mkdir(parents=True)
        (kb_root / name / "metadata.json").write_text("{}", encoding="utf-8")

    class Manager:
        def get_info(self, name):
            return {"status": "ready"}

    async def retrieve(root, name, query):
        source = root / name / "raw" / f"{name}.md"
        return {"content": "教材 chunk", "sources": [{"source": str(source)}]}

    monkeypatch.setattr(preflight, "_has_ready_kb_index", lambda path: True)
    monkeypatch.setattr(preflight, "_retrieve_kb", retrieve)
    report = preflight.PreflightReport()
    preflight.check_k12_knowledge_bases(report, kb_root=kb_root, manager=Manager())
    assert len(report.results) == 4
    assert all(item.passed for item in report.results)

    monkeypatch.setattr(preflight, "_has_ready_kb_index", lambda path: False)
    report = preflight.PreflightReport()
    preflight.check_k12_knowledge_bases(report, kb_root=kb_root, manager=Manager())
    assert not any(item.passed for item in report.results)


def test_sandbox_runs_real_coding_lab_probe(preflight, monkeypatch):
    body = (
        '{"result":{"stdout":"qiming sandbox ok\\n","stderr":"","exit_code":0,"timed_out":false}}'
    )
    monkeypatch.setattr(preflight, "_http_post_json", lambda *args, **kwargs: (200, body))
    report = preflight.PreflightReport()
    preflight.check_sandbox(report, 8001, True)
    assert report.results[0].passed is True

    monkeypatch.setattr(
        preflight,
        "_http_post_json",
        lambda *args, **kwargs: (503, '{"detail":"sandbox_unavailable"}'),
    )
    report = preflight.PreflightReport()
    preflight.check_sandbox(report, 8001, True)
    assert report.results[0].passed is False


def test_optional_failure_does_not_fail_strict_report(preflight):
    report = preflight.PreflightReport()
    report.add("required", True, required=True)
    report.add("optional", False, required=False)
    assert report.all_required_passed is True
