"""Tests for db/query operations."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import duckdb
import pytest

from tests.fixtures.load_fixtures import load_sample_notes
from NotesMirror.db.schema import SCHEMA_SQL
from NotesMirror.db.connection import open_db
from NotesMirror.db.query import list_notes, get_note, search_notes, list_notebooks, get_status_info


def _create_test_db() -> duckdb.DuckDBPyConnection:
    """Create an in-memory test database with sample data."""
    conn = duckdb.connect(":memory:", read_only=False)
    
    # Apply schema
    for stmt in SCHEMA_SQL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    
    # Seed metadata
    conn.execute(
        "INSERT INTO app_metadata (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT (key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        ["schema_version", "1"],
    )
    conn.execute(
        "INSERT INTO app_metadata (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT (key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        ["app_version", "0.1.0"],
    )
    
    # Create the notebook referenced by the fixture data
    conn.execute(
        "INSERT INTO notebooks (id, name, created, updated) VALUES (?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET name=excluded.name",
        [
            "B2C310D1-013F-7570-88B6-357F6A5C34B0",
            "Notes",
            "2024-01-01 00:00:00",
            "2024-01-01 00:00:00",
        ],
    )
    
    # Create test notes
    notes_fixture = load_sample_notes()
    
    for note_data in notes_fixture:
        conn.execute(
            "INSERT INTO notes (id, notebook_id, title, content, created, updated, is_archived) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                note_data["id"],
                note_data["notebook_id"],
                note_data["title"],
                note_data["content"],
                note_data["created"],
                note_data["updated"],
                note_data["is_archived"],
            ],
        )
    
    conn.commit()
    return conn


def test_list_notes():
    conn = _create_test_db()
    try:
        notes = list_notes(conn, count=10)
        assert len(notes) == 2
        assert notes[0].title == "Sample Note One"
    finally:
        conn.close()


def test_list_notes_filter_notebook():
    conn = _create_test_db()
    try:
        notes = list_notes(conn, count=10, notebook="B2C310D1-013F-7570-88B6-357F6A5C34B0")
        assert len(notes) == 2
    finally:
        conn.close()


def test_get_note():
    conn = _create_test_db()
    try:
        note = get_note(conn, "52F57A81-3E3F-4994-9337-A0E4B84B77A3")
        assert note.title == "Sample Note One"
    finally:
        conn.close()


def test_get_note_not_found():
    conn = _create_test_db()
    try:
        with pytest.raises(ValueError, match="Note not found"):
            get_note(conn, "non-existent-id")
    finally:
        conn.close()


def test_search_notes():
    conn = _create_test_db()
    try:
        results = search_notes(conn, "sample")
        assert len(results) >= 1
        assert any("Sample" in n.title or "sample" in n.content.lower() for n in results)
    finally:
        conn.close()


def test_search_notes_title_only():
    conn = _create_test_db()
    try:
        results = search_notes(conn, "Shopping", title_only=True)
        assert len(results) >= 1
    finally:
        conn.close()


def test_list_notebooks():
    conn = _create_test_db()
    try:
        nbs = list_notebooks(conn)
        assert len(nbs) == 1
        assert nbs[0].name == "Notes"
    finally:
        conn.close()


def test_list_notebooks_with_count():
    conn = _create_test_db()
    try:
        nbs = list_notebooks(conn, with_count=True)
        assert len(nbs) == 1
        assert nbs[0].note_count == 3
    finally:
        conn.close()


def test_get_status_info():
    conn = _create_test_db()
    try:
        info = get_status_info(conn)
        assert "schema_version" in info
        assert "app_version" in info
        assert info["note_count"] == 3
        assert info["notebook_count"] == 1
    finally:
        conn.close()
