"""Targeted tests for sync orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from NotesMirror.db.connection import managed_db
from NotesMirror.db.query import get_status_info, list_notes
from NotesMirror.sync.sync_engine import SyncEngine


class FakeSyncer:
    """Test double that returns a static snapshot."""

    def __init__(self, notes: list[dict], notebooks: list[dict]):
        self._notes = notes
        self._notebooks = notebooks

    def fetch_all(self) -> tuple[list[dict], list[dict]]:
        return self._notes, self._notebooks


def _notebook_row() -> dict:
    return {
        "id": "nb-1",
        "name": "Inbox",
        "created": "2024-01-01T00:00:00+00:00",
        "updated": "2024-01-01T00:00:00+00:00",
    }


def _note_row(note_id: str, title: str, updated: str, content: str) -> dict:
    return {
        "id": note_id,
        "notebook_id": "nb-1",
        "title": title,
        "content": content,
        "content_type": "text",
        "created": "2024-01-01T00:00:00+00:00",
        "updated": updated,
        "is_archived": False,
        "last_seen_at": "2024-01-01T00:00:00+00:00",
    }


def test_sync_engine_inserts_updates_and_deletes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("NotesMirror.sync.sync_engine.is_linux", lambda: False)

    db_path = tmp_path / "notes.duckdb"
    initial_syncer = FakeSyncer(
        notes=[_note_row("n-1", "First", "2024-01-01T01:00:00+00:00", "hello")],
        notebooks=[_notebook_row()],
    )
    engine = SyncEngine(str(db_path), syncer=initial_syncer)
    report = engine.sync()
    assert report.notes_added == 1
    assert report.notes_updated == 0
    assert report.notes_deleted == 0

    second_syncer = FakeSyncer(
        notes=[_note_row("n-1", "First", "2024-01-02T01:00:00+00:00", "hello updated")],
        notebooks=[_notebook_row()],
    )
    engine = SyncEngine(str(db_path), syncer=second_syncer)
    report = engine.sync()
    assert report.notes_added == 0
    assert report.notes_updated == 1
    assert report.notes_deleted == 0

    with managed_db(db_path, read_only=False) as conn:
        notes = list_notes(conn, count=10, archived=True)
        assert len(notes) == 1
        assert notes[0].content == "hello updated"
        status = get_status_info(conn)
        assert status["success_sync_count"] == 2

    empty_syncer = FakeSyncer(notes=[], notebooks=[_notebook_row()])
    engine = SyncEngine(str(db_path), syncer=empty_syncer)
    report = engine.sync()
    assert report.notes_deleted == 1

    with managed_db(db_path, read_only=False) as conn:
        assert list_notes(conn, count=10, archived=True) == []


def test_sync_engine_rejects_linux(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("NotesMirror.sync.sync_engine.is_linux", lambda: True)
    engine = SyncEngine(str(tmp_path / "notes.duckdb"), syncer=FakeSyncer([], []))

    try:
        engine.sync()
    except RuntimeError as exc:
        assert "read-only" in str(exc)
    else:
        raise AssertionError("Expected sync to fail on Linux")
