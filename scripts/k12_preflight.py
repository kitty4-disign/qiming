#!/usr/bin/env python
"""K12 竞赛赛前自检脚本。

检查所有竞赛演示必需的依赖、配置和服务状态。
退出码 0 = 全部必需项通过；非 0 = 有必需项失败。

用法:
    python scripts/k12_preflight.py
    python scripts/k12_preflight.py --json
    python scripts/k12_preflight.py --port 8001 --frontend-port 3782
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DEEPTUTOR_HOME", str(ROOT))

# 四个 K12 阶段知识库（与 deeptutor.education.catalog 对齐）。
K12_KB_NAMES = (
    "k12-ai-primary-lower",
    "k12-ai-primary-upper",
    "k12-ai-middle",
    "k12-ai-high",
)

DEFAULT_BACKEND_PORT = 8001
DEFAULT_FRONTEND_PORT = 3782
MIN_DISK_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB


# ── 报告数据结构 ──────────────────────────────────────────────────────


@dataclass
class CheckResult:
    name: str
    passed: bool
    required: bool
    detail: str = ""
    suggestion: str = ""


@dataclass
class PreflightReport:
    results: list[CheckResult] = field(default_factory=list)

    def add(
        self,
        name: str,
        passed: bool,
        required: bool,
        detail: str = "",
        suggestion: str = "",
    ) -> None:
        self.results.append(CheckResult(name, passed, required, detail, suggestion))

    @property
    def all_required_passed(self) -> bool:
        return all(r.passed for r in self.results if r.required)

    def print(self) -> None:
        for r in self.results:
            # Keep status markers ASCII so strict mode also works in Windows
            # consoles whose active code page cannot encode emoji.
            tag = "[PASS]" if r.passed else ("[FAIL]" if r.required else "[WARN]")
            print(f"  {tag}  {r.name}")
            if r.detail:
                print(f"         {r.detail}")
            if not r.passed and r.suggestion:
                print(f"         -> {r.suggestion}")
        required_total = sum(1 for r in self.results if r.required)
        required_failures = [r for r in self.results if r.required and not r.passed]
        warnings = [r for r in self.results if not r.required and not r.passed]
        print(f"\n必需项: {required_total} 项, 失败 {len(required_failures)} 项")
        print(f"可选项: 警告 {len(warnings)} 项")
        if self.all_required_passed:
            print("[PASS] Strict Preflight: PASS")
        else:
            print("[FAIL] Strict Preflight: FAIL")

    def to_dict(self) -> dict:
        return {
            "all_required_passed": self.all_required_passed,
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "required": r.required,
                    "detail": r.detail,
                    "suggestion": r.suggestion,
                }
                for r in self.results
            ],
        }


# ── 工具函数 ──────────────────────────────────────────────────────────


def _path_service():
    """获取路径服务实例；导入失败时返回异常对象。"""
    try:
        from deeptutor.services.path_service import get_path_service

        return get_path_service()
    except Exception as exc:  # noqa: BLE001
        return exc


def _is_writable(path: Path) -> bool:
    """通过实际写入临时文件来验证目录可写。"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".preflight_write_probe"
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        probe.unlink(missing_ok=True)
        return True
    except Exception:  # noqa: BLE001
        return False


def _port_bindable(port: int, host: str = "127.0.0.1") -> bool:
    """端口是否可绑定（即未被占用）。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False


def _http_get(url: str, timeout: float = 3.0) -> tuple[int | None, str]:
    """GET 一个 URL，返回 (状态码或 None, 说明文本)。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "k12-preflight/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(2048).decode("utf-8", "replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _http_post_json(url: str, payload: dict, timeout: float = 30.0) -> tuple[int | None, str]:
    """POST JSON and return ``(status, response body or error detail)``."""
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "k12-preflight/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(64 * 1024).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read(4096).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            detail = f"HTTP {exc.code}"
        return exc.code, detail
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _ws_handshake(host: str, port: int, path: str, timeout: float = 3.0) -> tuple[bool, str]:
    """原始 WebSocket 升级握手；返回 (是否 101, 状态行/说明)。"""
    try:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(request.encode("ascii"))
            data = s.recv(4096).decode("utf-8", "replace")
        status_line = data.split("\r\n", 1)[0] if data else "（无响应）"
        return "101" in status_line, status_line
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _load_model_catalog() -> tuple[dict | None, str | None]:
    """加载 model_catalog.json，返回 (数据字典或 None, 错误说明或 None)。"""
    ps = _path_service()
    if isinstance(ps, Exception):
        return None, f"路径服务不可用: {ps}"
    catalog_file = ps.get_settings_dir() / "model_catalog.json"
    if not catalog_file.exists():
        return None, f"未找到模型目录: {catalog_file}"
    try:
        with open(catalog_file, encoding="utf-8") as f:
            return json.load(f), None
    except Exception as exc:  # noqa: BLE001
        return None, f"解析失败: {exc}"


# ── 检查函数 ──────────────────────────────────────────────────────────


def check_python_version(report: PreflightReport) -> None:
    major, minor = sys.version_info[0], sys.version_info[1]
    passed = sys.version_info >= (3, 11)
    detail = f"Python {major}.{minor}.{sys.version_info[2]}"
    report.add(
        "Python 版本 (>= 3.11)",
        passed,
        required=True,
        detail=detail,
        suggestion="安装 Python 3.11+ 并用它运行后端" if not passed else "",
    )


def check_node_version(report: PreflightReport) -> None:
    try:
        proc = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        report.add(
            "Node 版本 (>= 20)",
            False,
            required=True,
            detail="未找到 node 可执行文件",
            suggestion="安装 Node.js 20+ 并确保其在 PATH 中",
        )
        return
    except Exception as exc:  # noqa: BLE001
        report.add(
            "Node 版本 (>= 20)",
            False,
            required=True,
            detail=f"调用 node 失败: {exc}",
            suggestion="安装 Node.js 20+ 并确保其在 PATH 中",
        )
        return

    raw = (proc.stdout or "").strip()
    if proc.returncode != 0 or not raw.startswith("v"):
        report.add(
            "Node 版本 (>= 20)",
            False,
            required=True,
            detail=f"node --version 输出异常: {raw or proc.stderr.strip()}",
            suggestion="安装 Node.js 20+",
        )
        return
    try:
        major = int(raw[1:].split(".")[0])
    except ValueError:
        report.add(
            "Node 版本 (>= 20)",
            False,
            required=True,
            detail=f"无法解析版本号: {raw}",
            suggestion="安装 Node.js 20+",
        )
        return
    passed = major >= 20
    report.add(
        "Node 版本 (>= 20)",
        passed,
        required=True,
        detail=f"Node {raw}",
        suggestion="安装 Node.js 20+（前端构建需要）" if not passed else "",
    )


def check_ports(
    report: PreflightReport,
    backend_port: int,
    frontend_port: int,
    *,
    allow_stopped: bool = False,
) -> dict:
    """Verify that the expected backend and frontend answer on their ports."""
    backend_code, backend_body = _http_get(f"http://127.0.0.1:{backend_port}/", timeout=3.0)
    backend_online = backend_code == 200 and "Welcome to DeepTutor API" in backend_body
    if backend_online:
        report.add(
            f"Backend ({backend_port})",
            True,
            required=True,
            detail="DeepTutor 根路径 HTTP 200",
        )
    elif backend_code is None:
        report.add(
            f"Backend ({backend_port})",
            allow_stopped,
            required=True,
            detail=f"后端无 HTTP 响应: {backend_body}",
            suggestion="启动后端服务，或仅做安装检查时使用 --allow-stopped",
        )
    else:
        report.add(
            f"Backend ({backend_port})",
            False,
            required=True,
            detail=f"HTTP {backend_code}，响应不是 DeepTutor Backend",
            suggestion="确认该端口运行的是正确的 DeepTutor Backend",
        )

    frontend_code, frontend_body = _http_get(
        f"http://127.0.0.1:{frontend_port}/education", timeout=10.0
    )
    proxy_code, _ = _http_get(
        f"http://127.0.0.1:{frontend_port}/api/v1/education/catalog", timeout=5.0
    )
    frontend_online = frontend_code is not None and 200 <= frontend_code < 400 and proxy_code == 200
    if frontend_online:
        report.add(
            f"Frontend ({frontend_port})",
            True,
            required=True,
            detail=f"/education HTTP {frontend_code}，Backend 代理 HTTP {proxy_code}",
        )
    elif frontend_code is None:
        report.add(
            f"Frontend ({frontend_port})",
            allow_stopped,
            required=True,
            detail=f"/education 无 HTTP 响应: {frontend_body}",
            suggestion="启动 Frontend，确认 /education 可访问",
        )
    else:
        report.add(
            f"Frontend ({frontend_port})",
            False,
            required=True,
            detail=f"/education HTTP {frontend_code}，Backend 代理 HTTP {proxy_code}",
            suggestion="检查 Next.js 页面、proxy.ts 与 Backend 连接，不能返回 4xx/5xx",
        )

    return {"backend_online": backend_online, "frontend_online": frontend_online}


def check_api_health(
    report: PreflightReport,
    backend_port: int,
    backend_online: bool,
    *,
    allow_stopped: bool = False,
) -> None:
    """检查 /education、关键 API、WebSocket 健康。

    后端未运行时不视为失败（端口可用即可启动）；后端在线时验证路由可达。
    """
    if not backend_online:
        report.add(
            "关键 API 与 WebSocket 健康",
            allow_stopped,
            required=True,
            detail="后端未运行，无法验证 API 与 WebSocket",
            suggestion="启动后端服务后重新执行 preflight",
        )
        return

    # 根路径
    root_code, _ = _http_get(f"http://127.0.0.1:{backend_port}/", timeout=3.0)
    # /education/catalog
    edu_code, _ = _http_get(
        f"http://127.0.0.1:{backend_port}/api/v1/education/catalog", timeout=3.0
    )
    # WebSocket /api/v1/ws
    ws_ok, ws_status = _ws_handshake("127.0.0.1", backend_port, "/api/v1/ws", timeout=3.0)

    notes = []
    passed = True
    if root_code != 200:
        notes.append(f"根路径 HTTP {root_code}")
        passed = False
    else:
        notes.append("根路径 200")
    if edu_code == 200:
        notes.append("/api/v1/education/catalog 200")
    else:
        notes.append(f"/api/v1/education/catalog HTTP {edu_code}")
        passed = False
    if ws_ok:
        notes.append("WebSocket /api/v1/ws 101 升级成功")
    else:
        notes.append(f"WebSocket /api/v1/ws 未升级（{ws_status}）")
        passed = False

    report.add(
        "关键 API 与 WebSocket 健康",
        passed,
        required=True,
        detail="；".join(notes),
        suggestion="检查后端路由注册与鉴权配置" if not passed else "",
    )


async def _probe_llm() -> str:
    from deeptutor.services.llm import get_llm_client

    response = await get_llm_client().complete(
        "Reply with OK.",
        system_prompt="This is a health check. Reply briefly.",
        max_tokens=64,
        temperature=0,
    )
    if not (response or "").strip():
        raise RuntimeError("LLM returned an empty response")
    return "completion returned non-empty text"


async def _probe_embedding() -> str:
    from deeptutor.services.embedding.client import get_embedding_client

    vectors = await get_embedding_client().embed(
        ["qiming embedding probe", "qiming retrieval probe"]
    )
    if len(vectors) != 2 or any(not vector for vector in vectors):
        raise RuntimeError("embedding response is empty or has the wrong batch size")
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1:
        raise RuntimeError("embedding response dimensions are inconsistent")
    return f"batch=2, dimension={dimensions.pop()}"


def _run_probe(probe, timeout: float = 60.0) -> str:
    async def _timed() -> str:
        return await asyncio.wait_for(probe(), timeout=timeout)

    return asyncio.run(_timed())


def check_model_config(report: PreflightReport) -> None:
    """Verify active LLM and embedding selections with real provider calls."""
    data, err = _load_model_catalog()
    if data is None:
        for name in ("LLM Provider", "Embedding Provider"):
            report.add(
                name,
                False,
                required=True,
                detail=err or "",
                suggestion="在 设置 > 模型目录 中配置并激活对应模型",
            )
        return

    chat_count = 0
    emb_count = 0
    chat_active: str | None = None
    emb_active: str | None = None

    services = data.get("services") if isinstance(data, dict) else None
    if isinstance(services, dict):
        llm = services.get("llm", {}) or {}
        emb = services.get("embedding", {}) or {}
        chat_active = llm.get("active_model_id")
        emb_active = emb.get("active_model_id")
        for profile in llm.get("profiles", []) or []:
            chat_count += len((profile or {}).get("models", []) or [])
        for profile in emb.get("profiles", []) or []:
            emb_count += len((profile or {}).get("models", []) or [])
    else:
        # 兼容旧式扁平结构
        models = data.get("models", []) if isinstance(data, dict) else []
        for m in models:
            if isinstance(m, dict):
                if m.get("kind") == "chat":
                    chat_count += 1
                elif m.get("kind") == "embedding":
                    emb_count += 1

    probes = (
        ("LLM Provider", chat_count, chat_active, _probe_llm),
        ("Embedding Provider", emb_count, emb_active, _probe_embedding),
    )
    for name, count, active_id, probe in probes:
        if not count or not active_id:
            report.add(
                name,
                False,
                required=True,
                detail=f"配置模型 {count} 个，当前模型={active_id or '未设置'}",
                suggestion="在 设置 > 模型目录 中配置并激活对应模型",
            )
            continue
        try:
            live_detail = _run_probe(probe)
        except Exception as exc:  # noqa: BLE001
            report.add(
                name,
                False,
                required=True,
                detail=f"当前模型={active_id}，真实调用失败: {exc}",
                suggestion="检查 provider endpoint、模型名、API Key 与网络连接",
            )
            continue
        report.add(
            name,
            True,
            required=True,
            detail=f"当前模型={active_id}，真实调用成功（{live_detail}）",
        )


K12_KB_SMOKE_QUERIES = {
    "k12-ai-primary-lower": "清楚的指令为什么需要先后顺序？",
    "k12-ai-primary-upper": "训练集和测试集有什么区别？",
    "k12-ai-middle": "有标签数据由哪些部分组成？",
    "k12-ai-high": "灰度图像如何表示为二维数组？",
}


async def _retrieve_kb(kb_root: Path, name: str, query: str) -> dict:
    from deeptutor.services.rag.service import RAGService

    service = RAGService(kb_base_dir=str(kb_root), provider="llamaindex")
    return await service.search(query=query, kb_name=name)


def _has_ready_kb_index(kb_dir: Path) -> bool:
    from deeptutor.services.rag.index_probe import has_ready_provider_index

    return has_ready_provider_index(kb_dir, "llamaindex")


def check_k12_knowledge_bases(
    report: PreflightReport,
    *,
    kb_root: Path | None = None,
    manager=None,
) -> None:
    """Verify each K12 LlamaIndex with a real stage-specific retrieval."""
    ps = _path_service() if kb_root is None else None
    if kb_root is None and isinstance(ps, Exception):
        report.add(
            "K12 Knowledge Bases",
            False,
            required=True,
            detail=f"路径服务不可用: {ps}",
            suggestion="确认 deeptutor.services.path_service 可正常导入",
        )
        return

    if kb_root is None:
        kb_root = ps.get_knowledge_bases_root()

    if manager is None:
        try:
            from deeptutor.knowledge.manager import KnowledgeBaseManager

            manager = KnowledgeBaseManager(base_dir=str(kb_root))
        except Exception as exc:  # noqa: BLE001
            report.add(
                "K12 Knowledge Bases",
                False,
                required=True,
                detail=f"KnowledgeBaseManager 初始化失败: {exc}",
                suggestion="确认 deeptutor.knowledge.manager 模块及其依赖可用",
            )
            return

    for name in K12_KB_NAMES:
        kb_dir = kb_root / name
        if not kb_dir.exists():
            report.add(
                name,
                False,
                required=True,
                detail="知识库目录缺失",
                suggestion="运行 python scripts/init_k12_knowledge_bases.py --force",
            )
            continue

        status = "unknown"
        try:
            info = manager.get_info(name)
            status = info.get("status", "unknown")
        except Exception:  # noqa: BLE001
            pass

        has_metadata = (kb_dir / "metadata.json").is_file()
        try:
            index_ready = _has_ready_kb_index(kb_dir)
        except Exception:  # noqa: BLE001
            index_ready = False
        if status != "ready" or not has_metadata or not index_ready:
            report.add(
                name,
                False,
                required=True,
                detail=(
                    f"状态={status}，LlamaIndex={'就绪' if index_ready else '未就绪'}，"
                    f"元数据={'有' if has_metadata else '无'}"
                ),
                suggestion="运行 python scripts/init_k12_knowledge_bases.py --force 重建索引",
            )
            continue

        try:
            result = asyncio.run(
                asyncio.wait_for(
                    _retrieve_kb(kb_root, name, K12_KB_SMOKE_QUERIES[name]),
                    timeout=90.0,
                )
            )
            sources = result.get("sources") or []
            expected_source = kb_dir / "raw"
            source_hit = any(
                expected_source in Path(str(source.get("source") or "")).parents
                for source in sources
                if source.get("source")
            )
            retrieval_ready = bool(result.get("content")) and source_hit
            if result.get("needs_reindex") or result.get("error_type"):
                retrieval_ready = False
        except Exception as exc:  # noqa: BLE001
            retrieval_ready = False
            sources = []
            retrieval_error = str(exc)
        else:
            retrieval_error = ""

        report.add(
            name,
            retrieval_ready,
            required=True,
            detail=(
                f"状态=ready，真实检索命中 {len(sources)} 个教材 chunk"
                if retrieval_ready
                else f"索引存在但真实检索失败: {retrieval_error or '无对应教材 source'}"
            ),
            suggestion="确认活动 Embedding 与索引签名一致，并用 --force 重建"
            if not retrieval_ready
            else "",
        )


def check_sandbox(
    report: PreflightReport,
    backend_port: int = DEFAULT_BACKEND_PORT,
    backend_online: bool = False,
) -> None:
    """Run a real program through the Backend's K12 Coding Lab endpoint."""
    if not backend_online:
        report.add(
            "Sandbox",
            False,
            required=True,
            detail="Backend 未在线，无法验证真实 Coding Lab 执行",
            suggestion="启动含可用 Sandbox backend 的 Backend 后重试",
        )
        return

    payload = {
        "course_id": "python-image-classifier",
        "task_id": "image-features-nearest-centroid",
        "language": "python",
        "source_code": 'print("qiming sandbox ok")',
        "stdin": "",
    }
    code, body = _http_post_json(
        f"http://127.0.0.1:{backend_port}/api/v1/education/code/run",
        payload,
        timeout=90.0,
    )
    try:
        result = json.loads(body).get("result", {}) if code == 200 else {}
    except json.JSONDecodeError:
        result = {}
    passed = (
        code == 200
        and result.get("stdout", "").strip() == "qiming sandbox ok"
        and result.get("exit_code") == 0
        and result.get("timed_out") is False
    )
    report.add(
        "Sandbox",
        passed,
        required=True,
        detail=(
            "Coding Lab 真实执行成功，stdout=qiming sandbox ok"
            if passed
            else f"Coding Lab 执行失败（HTTP {code}）: {body[:500]}"
        ),
        suggestion="检查 RunnerSidecar、执行工作目录与 /api/v1/education/code/run"
        if not passed
        else "",
    )


def check_k12_catalog(report: PreflightReport) -> None:
    """检查 catalog v2 是否有 4 教材 8 课程。"""
    try:
        from deeptutor.education.catalog import load_catalog
    except Exception as exc:  # noqa: BLE001
        report.add(
            "K12 课程目录 (catalog v2)",
            False,
            required=True,
            detail=f"导入失败: {exc}",
            suggestion="确认 deeptutor.education.catalog 模块及 catalog.yaml 存在",
        )
        return

    try:
        catalog = load_catalog()
        version = catalog.version
        textbooks = list(catalog.textbooks)
        courses = [c for tb in textbooks for c in tb.courses]
        passed = version == 2 and len(textbooks) == 4 and len(courses) == 8
        detail = f"version={version}, 教材={len(textbooks)}, 课程={len(courses)}"
        report.add(
            "K12 课程目录 (catalog v2)",
            passed,
            required=True,
            detail=detail,
            suggestion="确认 deeptutor/education/catalog.yaml 为 v2 且含 4 教材 8 课程"
            if not passed
            else "",
        )
    except Exception as exc:  # noqa: BLE001
        report.add(
            "K12 课程目录 (catalog v2)",
            False,
            required=True,
            detail=f"加载失败: {exc}",
            suggestion="检查 catalog.yaml 格式与 pydantic 校验",
        )


def check_disk_space(report: PreflightReport) -> None:
    """检查项目根目录所在磁盘至少有 1GB 可用空间。"""
    ps = _path_service()
    if isinstance(ps, Exception):
        target = ROOT
    else:
        target = ps.project_root
    try:
        usage = shutil.disk_usage(target)
    except Exception as exc:  # noqa: BLE001
        report.add(
            "磁盘可用空间 (>= 1GB)",
            False,
            required=True,
            detail=f"无法获取磁盘信息: {exc}",
            suggestion="确认项目根目录可访问",
        )
        return

    free_gb = usage.free / (1024**3)
    passed = usage.free >= MIN_DISK_BYTES
    report.add(
        "磁盘可用空间 (>= 1GB)",
        passed,
        required=True,
        detail=f"{target}: 可用 {free_gb:.2f} GB / 总 {usage.total / (1024**3):.2f} GB",
        suggestion="清理磁盘空间至至少 1GB 可用" if not passed else "",
    )


def check_data_dir_writable(report: PreflightReport) -> None:
    """检查 data/ 目录是否可写（输出目录权限）。

    优先通过实际写入探针文件验证；若探针被沙箱/杀软等拦截，
    回退到 os.access 权限检查，避免受限环境下的误报。
    """
    ps = _path_service()
    if isinstance(ps, Exception):
        data_dir = ROOT / "data"
    else:
        data_dir = ps.project_root / "data"

    if _is_writable(data_dir):
        report.add(
            "输出目录权限 (data/)",
            True,
            required=True,
            detail=f"可写: {data_dir}",
        )
        return

    # 探针写入失败：可能是权限不足，也可能是沙箱/杀软拦截了文件创建。
    access_ok = os.access(data_dir, os.W_OK)
    if access_ok:
        report.add(
            "输出目录权限 (data/)",
            True,
            required=True,
            detail=(f"可写 (os.access=是；探针写入被拦截，可能受沙箱/杀软限制): {data_dir}"),
        )
    else:
        report.add(
            "输出目录权限 (data/)",
            False,
            required=True,
            detail=f"不可写: {data_dir}",
            suggestion="检查 data/ 目录的写入权限，或以有权限的用户运行",
        )


def check_web_build(report: PreflightReport) -> None:
    """检查前端是否已构建（web/.next/BUILD_ID）。"""
    ps = _path_service()
    if isinstance(ps, Exception):
        project_root = ROOT
    else:
        project_root = ps.project_root

    build_id = project_root / "web" / ".next" / "BUILD_ID"
    if build_id.exists():
        try:
            bid = build_id.read_text(encoding="utf-8").strip()
        except Exception:  # noqa: BLE001
            bid = "?"
        report.add(
            "前端构建产物 (web/.next/BUILD_ID)",
            True,
            required=True,
            detail=f"已构建, BUILD_ID={bid[:24]}",
        )
    else:
        report.add(
            "前端构建产物 (web/.next/BUILD_ID)",
            False,
            required=True,
            detail=f"未找到: {build_id}",
            suggestion="在 web/ 目录下执行 npm run build 构建前端",
        )


def check_optional_capabilities(
    report: PreflightReport, backend_port: int, backend_online: bool
) -> None:
    """Voice / 动画等可选能力状态（失败只警告）。"""
    import importlib.util

    # 动画能力：Manim 是否安装
    manim_available = importlib.util.find_spec("manim") is not None
    report.add(
        "动画能力 (Manim)",
        manim_available,
        required=False,
        detail="manim 已安装" if manim_available else "manim 未安装",
        suggestion="pip install manim 可启用数学动画渲染（可选）" if not manim_available else "",
    )

    # Voice 能力：检查 model_catalog 的 tts/stt 配置，并在后端在线时探测路由。
    voice_configured = False
    voice_cfg_detail = ""
    data, _ = _load_model_catalog()
    if isinstance(data, dict):
        services = data.get("services") or {}
        configured_svcs = []
        for svc_key in ("tts", "stt"):
            svc_cfg = services.get(svc_key, {}) or {}
            profiles = svc_cfg.get("profiles", []) or []
            if profiles:
                configured_svcs.append(svc_key)
        if configured_svcs:
            voice_configured = True
            voice_cfg_detail = f"已配置 {','.join(configured_svcs)}"
        else:
            voice_cfg_detail = "tts/stt 均未配置"

    voice_router_importable = importlib.util.find_spec("deeptutor.api.routers.voice") is not None

    if backend_online:
        code, _ = _http_get(f"http://127.0.0.1:{backend_port}/api/v1/voice", timeout=2.0)
        online_detail = (
            f"，后端 voice 路由 HTTP {code}" if code is not None else "，后端 voice 路由无响应"
        )
        passed = voice_configured or code is not None
        report.add(
            "Voice 语音能力",
            passed,
            required=False,
            detail=f"{voice_cfg_detail}{online_detail}",
            suggestion="在 设置 中配置 TTS/STT 模型可启用语音（可选能力）" if not passed else "",
        )
    else:
        report.add(
            "Voice 语音能力",
            voice_configured,
            required=False,
            detail=(
                f"{voice_cfg_detail}，voice 路由模块"
                f"{'已集成' if voice_router_importable else '缺失'}，后端未运行未在线验证"
            ),
            suggestion="在 设置 中配置 TTS/STT 模型可启用语音（可选能力）"
            if not voice_configured
            else "",
        )


# ── 主入口 ────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="K12 竞赛赛前自检：检查依赖、配置、服务状态。")
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出结果（便于脚本解析）。",
    )
    parser.add_argument(
        "--allow-stopped",
        action="store_true",
        help="安装检查模式：允许前后端尚未启动。默认赛前模式要求服务在线。",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_BACKEND_PORT,
        help=f"后端端口（默认 {DEFAULT_BACKEND_PORT}）。",
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=DEFAULT_FRONTEND_PORT,
        help=f"前端端口（默认 {DEFAULT_FRONTEND_PORT}）。",
    )
    args = parser.parse_args()

    report = PreflightReport()

    # 基础环境
    check_python_version(report)
    check_node_version(report)

    # 端口与服务健康
    port_state = check_ports(
        report, args.port, args.frontend_port, allow_stopped=args.allow_stopped
    )
    check_api_health(
        report,
        args.port,
        port_state["backend_online"],
        allow_stopped=args.allow_stopped,
    )

    # 模型与知识库
    check_model_config(report)
    check_k12_knowledge_bases(report)
    check_k12_catalog(report)

    # 沙箱
    check_sandbox(report, args.port, port_state["backend_online"])

    # 磁盘与权限
    check_disk_space(report)
    check_data_dir_writable(report)

    # 前端构建
    check_web_build(report)

    # 可选能力（仅警告）
    check_optional_capabilities(report, args.port, port_state["backend_online"])

    if args.json:
        payload = report.to_dict()
        payload["exit_code"] = 0 if report.all_required_passed else 1
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("\n=== K12 竞赛赛前自检 ===\n")
        report.print()
        print()

    return 0 if report.all_required_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
