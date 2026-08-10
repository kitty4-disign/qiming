from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3

import pytest

from deeptutor.services.path_service import PathService
from deeptutor.services.session import sqlite_store as sqlite_store_module
from deeptutor.services.session.sqlite_store import (
    LegacyDBMigrationError,
    SQLiteSessionStore,
)


def test_sqlite_store_defaults_to_data_user_chat_history_db(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        store = SQLiteSessionStore()

        assert store.db_path == tmp_path / "data" / "user" / "chat_history.db"
        assert store.db_path.exists()
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir


def _make_legacy_db(
    tmp_path: Path,
    rows: list[str] | None = None,
    use_wal: bool = False,
) -> tuple[Path, sqlite3.Connection | None]:
    """Create a legacy ``data/chat_history.db`` with a ``legacy`` table.

    Returns ``(legacy_db, conn)``. For the normal (non-WAL) case ``conn``
    is ``None`` (already closed). With ``use_wal=True`` the database is
    switched to WAL with auto-checkpointing disabled and the commit is left
    *uncheckpointed* in the ``-wal`` sidecar, so the caller must keep the
    returned connection open (closing it triggers SQLite's close-time
    checkpoint and would erase the data being probed) and close it when
    done.
    """
    legacy_db = tmp_path / "data" / "chat_history.db"
    legacy_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(legacy_db)
    if use_wal:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE legacy (id INTEGER PRIMARY KEY, val TEXT)")
    for val in rows or ["hello"]:
        conn.execute("INSERT INTO legacy (val) VALUES (?)", (val,))
    conn.commit()
    if not use_wal:
        conn.close()
        return legacy_db, None
    return legacy_db, conn


def _verify_legacy_rows(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = [r[0] for r in conn.execute("SELECT val FROM legacy ORDER BY id")]
    finally:
        conn.close()
    return rows


def _monkeypatch_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the ``PathService`` singleton at ``tmp_path``; restore on exit.

    Using ``monkeypatch.setattr`` keeps the singleton's attributes
    isolated per test, so the tests stay order independent.
    """
    service = PathService.get_instance()
    monkeypatch.setattr(service, "_project_root", tmp_path)
    monkeypatch.setattr(service, "_user_data_dir", tmp_path / "data" / "user")


def _replace_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every ``os.replace`` in the store module raise OSError."""
    def forbidden_replace(src, dst, *args, **kwargs):
        raise OSError(32, "Sharing violation", str(src))

    monkeypatch.setattr(sqlite_store_module.os, "replace", forbidden_replace)


def _replace_fails_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the first ``os.replace`` (the atomic publish) fail, then pass."""
    orig = sqlite_store_module.os.replace
    state = {"n": 0}

    def limited_replace(src, dst, *args, **kwargs):
        state["n"] += 1
        if state["n"] == 1:
            raise OSError(32, "Sharing violation", str(src))
        return orig(src, dst, *args, **kwargs)

    monkeypatch.setattr(sqlite_store_module.os, "replace", limited_replace)


def _legacy_unlink_fails(monkeypatch: pytest.MonkeyPatch, legacy_str: str) -> None:
    """Make removing the legacy file fail as if it were still open."""
    orig_unlink = Path.unlink

    def locked_unlink(self: Path, *args, **kwargs):
        if str(self) == legacy_str:
            raise OSError(32, "Sharing violation", str(self))
        return orig_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked_unlink)


def test_migration_normal_closed_database(monkeypatch, tmp_path: Path) -> None:
    _monkeypatch_paths(tmp_path, monkeypatch)
    legacy_db, _ = _make_legacy_db(tmp_path, ["alpha", "beta"])

    store = SQLiteSessionStore()

    assert store.db_path.exists()
    assert not legacy_db.exists()
    assert _verify_legacy_rows(store.db_path) == ["alpha", "beta"]


def test_migration_folds_uncheckpointed_wal_with_writer_open(monkeypatch, tmp_path: Path) -> None:
    _monkeypatch_paths(tmp_path, monkeypatch)
    legacy_db, conn = _make_legacy_db(tmp_path, ["alpha", "beta", "gamma"], use_wal=True)
    try:
        # The committed rows must still live in the WAL sidecar, not the
        # main database, at the moment the migration runs.
        wal_file = legacy_db.with_name(legacy_db.name + "-wal")
        assert wal_file.exists()
        assert wal_file.stat().st_size > 0

        store = SQLiteSessionStore()

        assert store.db_path.exists()
        assert _verify_legacy_rows(store.db_path) == ["alpha", "beta", "gamma"]
    finally:
        conn.close()


def test_migration_backup_failure_keeps_legacy_and_skips_start(monkeypatch, tmp_path: Path) -> None:
    _monkeypatch_paths(tmp_path, monkeypatch)
    target = tmp_path / "data" / "user" / "chat_history.db"
    legacy_db = tmp_path / "data" / "chat_history.db"
    legacy_db.parent.mkdir(parents=True, exist_ok=True)
    legacy_db.write_bytes(b"this is not a sqlite database at all")

    with pytest.raises(LegacyDBMigrationError, match="Could not migrate"):
        SQLiteSessionStore()

    # A failed migration keeps the legacy DB, never creates the target, and
    # the store cannot be constructed with an empty history.
    assert legacy_db.exists()
    assert not target.exists()


def test_migration_quickcheck_failure_keeps_legacy_and_skips_start(monkeypatch, tmp_path: Path) -> None:
    _monkeypatch_paths(tmp_path, monkeypatch)
    target = tmp_path / "data" / "user" / "chat_history.db"
    legacy_db, _ = _make_legacy_db(tmp_path, ["alpha"])
    conn = sqlite3.connect(legacy_db)
    try:
        conn.execute("PRAGMA writable_schema=ON")
        conn.execute("UPDATE sqlite_schema SET rootpage=12345 WHERE name='legacy'")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(LegacyDBMigrationError):
        SQLiteSessionStore()

    assert legacy_db.exists()
    assert not target.exists()


def test_migration_publish_failure_keeps_legacy_and_cleans_temp(monkeypatch, tmp_path: Path) -> None:
    _monkeypatch_paths(tmp_path, monkeypatch)
    target = tmp_path / "data" / "user" / "chat_history.db"
    legacy_db, _ = _make_legacy_db(tmp_path, ["alpha", "beta"])
    _replace_fails(monkeypatch)

    with pytest.raises(LegacyDBMigrationError, match="Could not migrate"):
        SQLiteSessionStore()

    assert legacy_db.exists()
    assert not target.exists()
    # No staging temp file is left behind either.
    assert list(target.parent.glob(".*.tmp")) == []


def test_migration_publish_then_legacy_delete_failure_keeps_target(monkeypatch, tmp_path: Path) -> None:
    _monkeypatch_paths(tmp_path, monkeypatch)
    legacy_db, _ = _make_legacy_db(tmp_path, ["alpha"])
    _legacy_unlink_fails(monkeypatch, str(legacy_db))

    store = SQLiteSessionStore()

    # The target is fully published and usable even though the old file
    # could not be removed (e.g. a still-open handle on Windows).
    assert store.db_path.exists()
    assert legacy_db.exists()
    assert _verify_legacy_rows(store.db_path) == ["alpha"]


def test_migration_retries_after_failure_and_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    _monkeypatch_paths(tmp_path, monkeypatch)
    target = tmp_path / "data" / "user" / "chat_history.db"
    legacy_db, _ = _make_legacy_db(tmp_path, ["alpha", "beta"])
    _replace_fails_once(monkeypatch)

    with pytest.raises(LegacyDBMigrationError):
        SQLiteSessionStore()
    # First attempt left both the legacy data and the target untouched, so a
    # later launch can retry the migration.
    assert legacy_db.exists()
    assert not target.exists()

    store = SQLiteSessionStore()
    assert target.exists()
    assert not legacy_db.exists()
    assert _verify_legacy_rows(store.db_path) == ["alpha", "beta"]

    # A subsequent launch sees the target and skips migration entirely.
    second = SQLiteSessionStore()
    assert _verify_legacy_rows(second.db_path) == ["alpha", "beta"]


@pytest.fixture
def store(tmp_path: Path) -> SQLiteSessionStore:
    return SQLiteSessionStore(db_path=tmp_path / "test.db")


def _make_items(*specs):
    """Build notebook entry dicts from (qid, question, is_correct) tuples."""
    items = []
    for qid, question, is_correct in specs:
        items.append(
            {
                "question_id": qid,
                "question": question,
                "question_type": "choice",
                "options": {"A": "opt_a", "B": "opt_b"},
                "user_answer": "A",
                "correct_answer": "B",
                "explanation": "expl",
                "difficulty": "medium",
                "is_correct": is_correct,
            }
        )
    return items


# ── Notebook entries ──────────────────────────────────────────────


def test_upsert_notebook_entries_persists_all(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session(title="Test"))
    items = _make_items(("q1", "2+2?", False), ("q2", "3+3?", True), ("q3", "5+5?", False))
    upserted = asyncio.run(store.upsert_notebook_entries(session["id"], items))
    assert upserted == 3
    result = asyncio.run(store.list_notebook_entries())
    assert result["total"] == 3
    assert all(e["session_title"] == "Test" for e in result["items"])


def test_upsert_notebook_entries_updates_on_conflict(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    sid = session["id"]
    asyncio.run(store.upsert_notebook_entries(sid, _make_items(("q1", "Q?", False))))
    result = asyncio.run(store.list_notebook_entries())
    assert result["items"][0]["is_correct"] is False

    asyncio.run(
        store.upsert_notebook_entries(
            sid,
            [
                {
                    "question_id": "q1",
                    "question": "Q?",
                    "user_answer": "B",
                    "correct_answer": "B",
                    "is_correct": True,
                }
            ],
        )
    )
    result = asyncio.run(store.list_notebook_entries())
    assert result["total"] == 1
    assert result["items"][0]["is_correct"] is True
    assert result["items"][0]["user_answer"] == "B"


def test_upsert_skips_blank_questions(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    items = [
        {"question_id": "q1", "question": "", "is_correct": False},
        {"question_id": "", "question": "Valid?", "is_correct": False},
        {"question_id": "q3", "question": "OK?", "is_correct": False},
    ]
    upserted = asyncio.run(store.upsert_notebook_entries(session["id"], items))
    assert upserted == 1


def test_upsert_unknown_session_raises(store: SQLiteSessionStore) -> None:
    with pytest.raises(ValueError, match="Session not found"):
        asyncio.run(store.upsert_notebook_entries("nope", _make_items(("q1", "Q?", False))))


def test_list_entries_filters_bookmarked(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(
        store.upsert_notebook_entries(
            session["id"],
            _make_items(
                ("q1", "Q1?", False),
                ("q2", "Q2?", True),
            ),
        )
    )
    entries = asyncio.run(store.list_notebook_entries())["items"]
    asyncio.run(store.update_notebook_entry(entries[0]["id"], {"bookmarked": True}))
    bm = asyncio.run(store.list_notebook_entries(bookmarked=True))
    assert bm["total"] == 1
    assert bm["items"][0]["bookmarked"] is True


def test_list_entries_filters_is_correct(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(
        store.upsert_notebook_entries(
            session["id"],
            _make_items(
                ("q1", "Q1?", False),
                ("q2", "Q2?", True),
            ),
        )
    )
    wrong = asyncio.run(store.list_notebook_entries(is_correct=False))
    assert wrong["total"] == 1
    assert wrong["items"][0]["question_id"] == "q1"


def test_update_notebook_entry_bookmark_roundtrip(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q?", False))))
    eid = asyncio.run(store.list_notebook_entries())["items"][0]["id"]
    assert asyncio.run(store.update_notebook_entry(eid, {"bookmarked": True})) is True
    assert asyncio.run(store.get_notebook_entry(eid))["bookmarked"] is True
    assert asyncio.run(store.update_notebook_entry(eid, {"bookmarked": False})) is True
    assert asyncio.run(store.get_notebook_entry(eid))["bookmarked"] is False
    assert asyncio.run(store.update_notebook_entry(99999, {"bookmarked": True})) is False


def test_update_followup_session_id(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q?", False))))
    eid = asyncio.run(store.list_notebook_entries())["items"][0]["id"]
    asyncio.run(store.update_notebook_entry(eid, {"followup_session_id": "sess_fu"}))
    entry = asyncio.run(store.get_notebook_entry(eid))
    assert entry["followup_session_id"] == "sess_fu"


def test_find_notebook_entry(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q?", False))))
    found = asyncio.run(store.find_notebook_entry(session["id"], "q1"))
    assert found is not None
    assert found["question_id"] == "q1"
    assert asyncio.run(store.find_notebook_entry(session["id"], "nope")) is None


def test_delete_notebook_entry(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(
        store.upsert_notebook_entries(
            session["id"],
            _make_items(
                ("q1", "Q1?", False),
                ("q2", "Q2?", False),
            ),
        )
    )
    eid = asyncio.run(store.list_notebook_entries())["items"][0]["id"]
    assert asyncio.run(store.delete_notebook_entry(eid)) is True
    assert asyncio.run(store.list_notebook_entries())["total"] == 1
    assert asyncio.run(store.delete_notebook_entry(99999)) is False


def test_entries_cascade_on_session_delete(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q?", False))))
    assert asyncio.run(store.list_notebook_entries())["total"] == 1
    asyncio.run(store.delete_session(session["id"]))
    assert asyncio.run(store.list_notebook_entries())["total"] == 0


# ── Categories ────────────────────────────────────────────────────


def test_category_crud(store: SQLiteSessionStore) -> None:
    cat = asyncio.run(store.create_category("Math"))
    assert cat["name"] == "Math"
    cats = asyncio.run(store.list_categories())
    assert len(cats) == 1
    assert cats[0]["entry_count"] == 0

    asyncio.run(store.rename_category(cat["id"], "Algebra"))
    cats = asyncio.run(store.list_categories())
    assert cats[0]["name"] == "Algebra"

    asyncio.run(store.delete_category(cat["id"]))
    assert asyncio.run(store.list_categories()) == []


def test_entry_category_association(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q?", False))))
    eid = asyncio.run(store.list_notebook_entries())["items"][0]["id"]
    cat = asyncio.run(store.create_category("Physics"))

    assert asyncio.run(store.add_entry_to_category(eid, cat["id"])) is True
    entry = asyncio.run(store.get_notebook_entry(eid))
    assert len(entry["categories"]) == 1
    assert entry["categories"][0]["name"] == "Physics"

    by_cat = asyncio.run(store.list_notebook_entries(category_id=cat["id"]))
    assert by_cat["total"] == 1

    asyncio.run(store.remove_entry_from_category(eid, cat["id"]))
    assert asyncio.run(store.get_entry_categories(eid)) == []


def test_category_cascade_on_entry_delete(store: SQLiteSessionStore) -> None:
    session = asyncio.run(store.create_session())
    asyncio.run(store.upsert_notebook_entries(session["id"], _make_items(("q1", "Q?", False))))
    eid = asyncio.run(store.list_notebook_entries())["items"][0]["id"]
    cat = asyncio.run(store.create_category("History"))
    asyncio.run(store.add_entry_to_category(eid, cat["id"]))
    asyncio.run(store.delete_notebook_entry(eid))
    cats = asyncio.run(store.list_categories())
    assert cats[0]["entry_count"] == 0
