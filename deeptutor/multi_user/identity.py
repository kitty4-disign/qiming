"""Canonical identity store for the optional multi-user layer."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import secrets
import threading
from typing import Any, Iterator
from uuid import uuid4

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from .models import Role
from .paths import PROJECT_ROOT, SYSTEM_ROOT, migrate_legacy_multi_user_tree

logger = logging.getLogger(__name__)

# Serialise in-process writes. Separate OS file locks below cover multiple
# Uvicorn workers / Python processes sharing the same identity directory.
_USERS_WRITE_LOCK = threading.Lock()
_AUTH_SECRET_WRITE_LOCK = threading.Lock()

AUTH_DIR = SYSTEM_ROOT / "auth"
USERS_FILE = AUTH_DIR / "users.json"
SECRET_FILE = AUTH_DIR / "auth_secret"
LEGACY_USERS_FILE = PROJECT_ROOT / "data" / "user" / "auth_users.json"
LEGACY_SECRET_FILE = PROJECT_ROOT / "data" / "user" / "auth_secret"


def new_user_id() -> str:
    return f"u_{uuid4().hex}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _users_lock_file() -> Path:
    return USERS_FILE.with_name(f"{USERS_FILE.name}.lock")


def _secret_lock_file() -> Path:
    return SECRET_FILE.with_name(f"{SECRET_FILE.name}.lock")


@contextmanager
def _process_file_lock(lock_path: Path) -> Iterator[None]:
    """Hold an exclusive OS lock on a stable sibling lock file.

    POSIX uses ``flock``; Windows uses ``msvcrt.locking`` on one byte. The
    lock file is deliberately separate from the protected data file so atomic
    replacement of that data file never changes the inode/file descriptor that
    carries the lock.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _users_write_guard() -> Iterator[None]:
    """Serialize identity mutations both within and across processes."""
    with _USERS_WRITE_LOCK:
        with _process_file_lock(_users_lock_file()):
            yield


@contextmanager
def _auth_secret_write_guard() -> Iterator[None]:
    """Serialize auth-secret migration/creation within and across processes."""
    with _AUTH_SECRET_WRITE_LOCK:
        with _process_file_lock(_secret_lock_file()):
            yield


def _canonical_record(
    username: str,
    value: Any,
    *,
    default_role: Role = "user",
) -> dict[str, Any] | None:
    if isinstance(value, str):
        return {
            "id": new_user_id(),
            "hash": value,
            "role": default_role,
            "created_at": utc_now(),
            "disabled": False,
            "avatar": "",
        }
    if not isinstance(value, dict):
        return None
    hashed = str(value.get("hash") or value.get("password_hash") or "")
    if not hashed:
        return None
    role = str(value.get("role") or default_role)
    if role not in {"admin", "user"}:
        role = default_role
    return {
        "id": str(value.get("id") or new_user_id()),
        "hash": hashed,
        "role": role,
        "created_at": str(value.get("created_at") or utc_now()),
        "disabled": bool(value.get("disabled", False)),
        "avatar": str(value.get("avatar") or ""),
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return {}


def _write_users(users: dict[str, dict[str, Any]]) -> None:
    """Atomically replace users.json so readers never observe partial JSON."""
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = USERS_FILE.with_name(
        f".{USERS_FILE.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        temp_path.write_text(
            json.dumps(users, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temp_path.replace(USERS_FILE)
    finally:
        temp_path.unlink(missing_ok=True)


def _write_secret(secret: str) -> None:
    """Atomically persist the JWT signing secret with owner-only permissions."""
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = SECRET_FILE.with_name(
        f".{SECRET_FILE.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        temp_path.write_text(secret, encoding="utf-8")
        try:
            temp_path.chmod(0o600)
        except OSError:
            pass
        temp_path.replace(SECRET_FILE)
        try:
            SECRET_FILE.chmod(0o600)
        except OSError:
            pass
    finally:
        temp_path.unlink(missing_ok=True)


def _migrate_legacy_users() -> dict[str, dict[str, Any]] | None:
    if USERS_FILE.exists() or not LEGACY_USERS_FILE.exists():
        return None
    legacy = _read_json(LEGACY_USERS_FILE)
    users: dict[str, dict[str, Any]] = {}
    for username, value in legacy.items():
        role: Role = "admin" if not users else "user"
        if isinstance(value, dict) and str(value.get("role") or "") in {"admin", "user"}:
            role = str(value.get("role"))  # type: ignore[assignment]
        record = _canonical_record(username, value, default_role=role)
        if record is not None:
            users[str(username)] = record
    if users:
        _write_users(users)
        logger.info("Migrated auth users from %s to %s", LEGACY_USERS_FILE, USERS_FILE)
        return users
    return None


def _migrate_secret() -> None:
    if SECRET_FILE.exists() or not LEGACY_SECRET_FILE.exists():
        return
    secret = LEGACY_SECRET_FILE.read_text(encoding="utf-8").strip()
    if secret:
        _write_secret(secret)
        logger.info("Migrated auth secret from %s to %s", LEGACY_SECRET_FILE, SECRET_FILE)


def load_users(  # nosec B107 - empty defaults mean "no env fallback supplied".
    env_username: str = "",
    env_password_hash: str = "",
) -> dict[str, dict[str, Any]]:
    """Load canonical users, migrating legacy records and env fallback in memory."""
    migrate_legacy_multi_user_tree()
    users: dict[str, dict[str, Any]] | None = None
    if USERS_FILE.exists():
        users = _read_json(USERS_FILE)
    else:
        users = _migrate_legacy_users()

    if users is None:
        users = {}

    canonical: dict[str, dict[str, Any]] = {}
    changed = False
    for index, (username, value) in enumerate(users.items()):
        role: Role = "admin" if index == 0 else "user"
        if isinstance(value, dict) and str(value.get("role") or "") in {"admin", "user"}:
            role = str(value.get("role"))  # type: ignore[assignment]
        record = _canonical_record(str(username), value, default_role=role)
        if record is None:
            changed = True
            continue
        canonical[str(username)] = record
        changed = changed or record != value

    if USERS_FILE.exists() and changed:
        _write_users(canonical)

    if canonical:
        return canonical

    if env_username and env_password_hash:
        return {
            env_username: {
                "id": "env-admin",
                "hash": env_password_hash,
                "role": "admin",
                "created_at": "",
                "disabled": False,
            }
        }

    return {}


def _new_user_record(
    username: str,
    hashed_password: str,
    role: Role,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = existing or {}
    return {
        "id": str(existing.get("id") or new_user_id()),
        "hash": hashed_password,
        "role": role,
        "created_at": str(existing.get("created_at") or utc_now()),
        "disabled": bool(existing.get("disabled", False)),
        "avatar": str(existing.get("avatar") or ""),
    }


def save_user(username: str, hashed_password: str, role: Role = "user") -> dict[str, Any]:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _users_write_guard():
        users = load_users()
        effective_role: Role = "admin" if not users else role
        record = _new_user_record(
            username,
            hashed_password,
            effective_role,
            users.get(username),
        )
        users[username] = record
        _write_users(users)
    return record


def save_first_user(username: str, hashed_password: str) -> dict[str, Any] | None:
    """Create the bootstrap admin iff the shared user store is still empty.

    The emptiness check and write happen while holding the same cross-process
    lock, so at most one concurrent public registration can succeed. A loser
    returns ``None`` and must be rejected by the HTTP bootstrap endpoint.
    """
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _users_write_guard():
        users = load_users()
        if users:
            return None
        record = _new_user_record(username, hashed_password, "admin")
        users[username] = record
        _write_users(users)
        return record


def list_user_info(  # nosec B107 - empty defaults mean "no env fallback supplied".
    env_username: str = "",
    env_password_hash: str = "",
) -> list[dict[str, Any]]:
    return [
        {
            "id": record.get("id", ""),
            "username": username,
            "role": record.get("role", "user"),
            "created_at": record.get("created_at", ""),
            "disabled": bool(record.get("disabled", False)),
            "avatar": str(record.get("avatar") or ""),
        }
        for username, record in load_users(env_username, env_password_hash).items()
    ]


def get_user(username: str) -> dict[str, Any] | None:
    return load_users().get(username)


def get_user_by_id(user_id: str) -> tuple[str, dict[str, Any]] | None:
    for username, record in load_users().items():
        if str(record.get("id") or "") == user_id:
            return username, record
    return None


def delete_user(username: str) -> bool:
    with _users_write_guard():
        if not USERS_FILE.exists():
            return False
        users = load_users()
        if username not in users:
            return False
        users.pop(username, None)
        _write_users(users)
        return True


def set_avatar(username: str, avatar: str) -> bool:
    """Update the avatar marker for an existing user. Returns True on success."""
    with _users_write_guard():
        if not USERS_FILE.exists():
            return False
        users = load_users()
        if username not in users:
            return False
        users[username]["avatar"] = avatar
        _write_users(users)
        return True


# ---------------------------------------------------------------------------
# Avatar image files — stored next to the user store, keyed by user id
# ---------------------------------------------------------------------------

# Extensions are derived from server-side content sniffing, never from the
# uploaded filename, so this list is also the full set of files we may serve.
AVATAR_EXTENSIONS = ("png", "jpg", "webp")


def _avatar_dir() -> Path:
    # Resolved lazily so tests that monkeypatch AUTH_DIR keep avatars isolated.
    return AUTH_DIR / "avatars"


def get_avatar_file(user_id: str) -> Path | None:
    """Return the stored avatar image for ``user_id``, or None."""
    for ext in AVATAR_EXTENSIONS:
        candidate = _avatar_dir() / f"{user_id}.{ext}"
        if candidate.is_file():
            return candidate
    return None


def save_avatar_file(user_id: str, data: bytes, ext: str) -> Path:
    """Atomically persist an avatar image, replacing any previous one."""
    if ext not in AVATAR_EXTENSIONS:
        raise ValueError(f"Unsupported avatar extension: {ext!r}")
    directory = _avatar_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{user_id}.{ext}"
    tmp = directory / f"{user_id}.{ext}.tmp"
    tmp.write_bytes(data)
    tmp.replace(target)
    # A re-upload may change the extension; drop stale siblings.
    for other in AVATAR_EXTENSIONS:
        if other != ext:
            (directory / f"{user_id}.{other}").unlink(missing_ok=True)
    return target


def delete_avatar_file(user_id: str) -> None:
    for ext in AVATAR_EXTENSIONS:
        (_avatar_dir() / f"{user_id}.{ext}").unlink(missing_ok=True)


def set_role(username: str, role: Role) -> bool:
    if role not in {"admin", "user"}:
        raise ValueError("role must be 'admin' or 'user'")
    with _users_write_guard():
        if not USERS_FILE.exists():
            return False
        users = load_users()
        if username not in users:
            return False
        users[username]["role"] = role
        _write_users(users)
        return True


def load_or_create_auth_secret() -> str:
    """Return one stable JWT signing secret shared by all local workers.

    Migration, first creation and the read-back happen under the same OS lock.
    If persistence fails we raise instead of returning a per-process fallback:
    divergent signing keys would make authentication nondeterministic and can
    invalidate tokens depending on which worker handles a request.
    """
    migrate_legacy_multi_user_tree()
    try:
        with _auth_secret_write_guard():
            _migrate_secret()
            if SECRET_FILE.exists():
                existing = SECRET_FILE.read_text(encoding="utf-8").strip()
                if existing:
                    return existing

            generated = secrets.token_hex(32)
            _write_secret(generated)
            persisted = SECRET_FILE.read_text(encoding="utf-8").strip()
            if not persisted:
                raise RuntimeError("auth secret file is empty after creation")
            logger.warning(
                "Auth is enabled and no auth_secret file existed. Generated a stable local "
                "secret at %s.",
                SECRET_FILE,
            )
            return persisted
    except Exception as exc:
        logger.error("Failed to load or create auth secret at %s", SECRET_FILE, exc_info=True)
        raise RuntimeError("Unable to establish a persistent authentication secret") from exc
