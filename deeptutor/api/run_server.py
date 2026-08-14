#!/usr/bin/env python
"""
Uvicorn Server Startup Script
Uses Python API instead of command line to avoid Windows path parsing issues.
"""

import asyncio
import os
from pathlib import Path
import sys

from deeptutor.runtime.home import get_runtime_home

# Windows: uvicorn defaults to SelectorEventLoop which does not support
# asyncio.create_subprocess_exec.  Switch to ProactorEventLoop so that
# child-process APIs (used by Math Animator renderer, etc.) work correctly.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

# Force unbuffered output
os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")


def main() -> None:
    # Runtime workspace root owns data/user/settings and generated outputs.
    project_root = get_runtime_home()
    os.chdir(str(project_root))

    # Get port from configuration
    from deeptutor.logging import configure_logging
    from deeptutor.runtime.mode import RunMode, set_mode
    from deeptutor.runtime.network_policy import require_safe_bind
    from deeptutor.services.config import load_auth_settings
    from deeptutor.services.setup import get_backend_port

    set_mode(RunMode.SERVER)
    configure_logging()
    backend_port = get_backend_port(project_root)
    # Safe-by-default local binding. Exposing the API beyond loopback is an
    # explicit deployer choice and must be paired with authentication unless
    # the deployer explicitly acknowledges the unauthenticated exposure risk.
    api_host = os.getenv("DEEPTUTOR_API_HOST", "127.0.0.1").strip() or "127.0.0.1"
    require_safe_bind(
        api_host,
        auth_enabled=bool(load_auth_settings()["enabled"]),
    )

    # Configure reload_excludes to skip directories that shouldn't trigger reloads
    # Use absolute paths to ensure they're properly resolved
    reload_excludes = [
        str(project_root / "venv"),  # Virtual environment
        str(project_root / ".venv"),  # Virtual environment (alternative name)
        str(project_root / "data"),  # Data directory (includes knowledge_bases, user data, logs)
        str(project_root / "node_modules"),  # Node modules (if any at root)
        str(project_root / "web" / "node_modules"),  # Node modules
        str(project_root / "web" / ".next"),  # Next.js build
        str(project_root / ".git"),  # Git directory
        str(project_root / "scripts"),  # Scripts directory - don't reload on launcher changes
    ]

    # Filter out non-existent directories to avoid warnings
    reload_excludes = [d for d in reload_excludes if Path(d).exists()]

    # Start uvicorn server with reload enabled
    uvicorn.run(
        "deeptutor.api.main:app",
        host=api_host,
        port=backend_port,
        reload=True,
        reload_excludes=reload_excludes,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
