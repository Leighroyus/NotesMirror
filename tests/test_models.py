"""Tests for Pydantic models."""

from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone

import pytest
import duckdb

from NotesMirror.models.note import Note
from NotesMirror.models.notebook import Notebook
from NotesMirror.models.sync_run import SyncRun
from NotesMirror.db.schema import SCHEMA_SQL
SAMPLE_NOTES_PATH = Path(__file__).parent / "fixtures" / "sample_notes.json"


def test_note_from_row():
    row = {
        "id": "test-note",
        "notebook_id": "nb-1",
        "title": "Test Note",
        "content": "Hello World",
        "content_type": "text",
        "created": "2024-01-01T00:00:00+00:00",
        "updated": "2024-01-02T00:00:00+00:00",
        "is_archived": False,
        "content_hash": None,
        "last_seen_at": "2024-01-02T00:00:00+00:00"
    }
    note = Note.from_row(row)
    assert note.id == "test-note"
    assert note.title == "Test Note"
    assert note.is_archived is False


def test_note_json():
    row = {
        "id": "test-note",
        "notebook_id": "nb-1",
        "title": "Test Note",
        "content": "Hello World",
        "content_type": "text",
        "created": "2024-01-01T00:00:00+00:00",
        "updated": "2024-01-02T00:00:00+00:00",
        "is_archived": False,
        "content_hash": None,
        "last_seen_at": "2024-01-02T00:00:00+00:00"
    }
    note = Note.from_row(row)
    assert "Test Note" in note.to_json()
    # note is properly serializable
    assert '"title":"Test Note"' in note.to_json()


def test_notebook_from_row():
    row = {
        "id": "nb-1",
        "name": "Test Notebook",
        "created": "2024-01-01T00:00:00+00:00",
        "updated": "2024-01-01T00:00:00+00:00"
    }
    nb = Notebook.from_row(row)
    assert nb.id == "nb-1"
    assert nb.name == "Test Notebook"


def test_sync_run_defaults():
    run = SyncRun()
    assert run.status == "running"
    assert run.notes_fetched == 0
    assert run.notes_added == 0
    assert run.notes_updated == 0
    assert run.notes_deleted == 0
    assert run.error_message is None


def test_sync_run_mark_success():
    run = SyncRun()
    result = run.mark_success()
    assert result.status == "success"
    assert result.finished_at is not None


def test_sync_run_mark_error():
    run = SyncRun()
    result = run.mark_error("test error")
    assert result.status == "error"
    assert result.error_message == "test error"


def test_load_sample_fixtures():
    if not os.path.exists(SAMPLE_NOTES_PATH):
        pytest.skip("fixture file missing")
    with open(SAMPLE_NOTES_PATH, "r") as f:
        data = json.load(f)
    assert len(data) == 3
    assert data[0]["title"] == "Sample Note One"


def test_notebook_sql():
    nb = Notebook(id="nb-1", name="Test")
    sql = nb.upsert_sql()
    assert "INSERT INTO notebooks" in sql
    assert "ON CONFLICT" in sql


def test_note_sql():
    note = Note(id="n-1", title="Test", created=datetime.now(timezone.utc),
                updated=datetime.now(timezone.utc))
    sql = note.upsert_sql()
    assert "INSERT INTO notes" in sql
    assert "ON CONFLICT" in sql
