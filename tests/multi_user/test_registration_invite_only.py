"""M5 regression — first user becomes admin atomically; concurrent races safe."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
from pathlib import Path


def _register_first_user_process(
    users_file: str,
    legacy_users_file: str,
    username: str,
    start_event,
    result_queue,
) -> None:
    from deeptutor.multi_user import identity

    identity.USERS_FILE = Path(users_file)
    identity.LEGACY_USERS_FILE = Path(legacy_users_file)
    if not start_event.wait(timeout=10):
        result_queue.put((username, "timeout"))
        return
    record = identity.save_first_user(username, "$2b$12$placeholder")
    result_queue.put((username, None if record is None else record.get("role")))


def test_first_save_user_promotes_to_admin(mu_isolated_root):
    from deeptutor.multi_user.identity import list_user_info, save_user

    save_user("alice", "$2b$12$placeholder", role="user")
    users = {u["username"]: u for u in list_user_info()}
    assert users["alice"]["role"] == "admin"


def test_second_save_user_keeps_user_role(mu_isolated_root):
    from deeptutor.multi_user.identity import list_user_info, save_user

    save_user("alice", "$2b$12$placeholder", role="user")
    save_user("bob", "$2b$12$placeholder", role="user")
    users = {u["username"]: u for u in list_user_info()}
    assert users["alice"]["role"] == "admin"
    assert users["bob"]["role"] == "user"


def test_concurrent_first_save_only_one_admin(mu_isolated_root):
    """The in-process lock keeps threaded read-modify-write operations safe."""
    from deeptutor.multi_user.identity import list_user_info, save_user

    def _save(name):
        try:
            save_user(name, "$2b$12$placeholder", role="user")
            return True
        except Exception:
            return False

    names = [f"u{i}" for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_save, names))

    users = list_user_info()
    admins = [u for u in users if u["role"] == "admin"]
    assert len(admins) == 1
    assert len(users) == 8


def test_concurrent_process_bootstrap_allows_exactly_one_first_user(tmp_path):
    """Two independent workers must not both pass the public bootstrap gate."""
    ctx = multiprocessing.get_context("spawn")
    users_file = tmp_path / "system" / "auth" / "users.json"
    legacy_users_file = tmp_path / "legacy-auth-users.json"
    start_event = ctx.Event()
    result_queue = ctx.Queue()
    processes = [
        ctx.Process(
            target=_register_first_user_process,
            args=(
                str(users_file),
                str(legacy_users_file),
                username,
                start_event,
                result_queue,
            ),
        )
        for username in ("alice", "bob")
    ]

    for process in processes:
        process.start()
    start_event.set()

    try:
        outcomes = [result_queue.get(timeout=15) for _ in processes]
    finally:
        for process in processes:
            process.join(timeout=15)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)

    assert all(process.exitcode == 0 for process in processes)
    roles = [role for _username, role in outcomes]
    assert roles.count("admin") == 1
    assert roles.count(None) == 1

    users = json.loads(users_file.read_text(encoding="utf-8"))
    assert len(users) == 1
    assert next(iter(users.values()))["role"] == "admin"
