from __future__ import annotations

import multiprocessing
from pathlib import Path


def _load_auth_secret_process(
    secret_file: str,
    legacy_secret_file: str,
    start_event,
    result_queue,
) -> None:
    from deeptutor.multi_user import identity

    identity.SECRET_FILE = Path(secret_file)
    identity.LEGACY_SECRET_FILE = Path(legacy_secret_file)
    identity.migrate_legacy_multi_user_tree = lambda: None
    if not start_event.wait(timeout=10):
        result_queue.put((False, "timeout"))
        return
    try:
        result_queue.put((True, identity.load_or_create_auth_secret()))
    except Exception as exc:
        result_queue.put((False, type(exc).__name__))


def test_concurrent_processes_share_one_auth_secret(tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("spawn")
    secret_file = tmp_path / "system" / "auth" / "auth_secret"
    legacy_secret_file = tmp_path / "legacy" / "auth_secret"
    start_event = ctx.Event()
    result_queue = ctx.Queue()
    processes = [
        ctx.Process(
            target=_load_auth_secret_process,
            args=(
                str(secret_file),
                str(legacy_secret_file),
                start_event,
                result_queue,
            ),
        )
        for _ in range(2)
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
    assert all(success for success, _value in outcomes)
    secrets = [value for success, value in outcomes if success]
    assert len(set(secrets)) == 1
    assert secret_file.read_text(encoding="utf-8").strip() == secrets[0]
    assert len(secrets[0]) == 64


def test_auth_secret_migration_wins_over_new_generation(tmp_path: Path) -> None:
    from deeptutor.multi_user import identity

    secret_file = tmp_path / "system" / "auth" / "auth_secret"
    legacy_secret_file = tmp_path / "legacy" / "auth_secret"
    legacy_secret_file.parent.mkdir(parents=True)
    legacy_secret_file.write_text("legacy-stable-secret", encoding="utf-8")

    old_secret = identity.SECRET_FILE
    old_legacy = identity.LEGACY_SECRET_FILE
    old_migrate = identity.migrate_legacy_multi_user_tree
    try:
        identity.SECRET_FILE = secret_file
        identity.LEGACY_SECRET_FILE = legacy_secret_file
        identity.migrate_legacy_multi_user_tree = lambda: None
        result = identity.load_or_create_auth_secret()
    finally:
        identity.SECRET_FILE = old_secret
        identity.LEGACY_SECRET_FILE = old_legacy
        identity.migrate_legacy_multi_user_tree = old_migrate

    assert result == "legacy-stable-secret"
    assert secret_file.read_text(encoding="utf-8") == "legacy-stable-secret"
