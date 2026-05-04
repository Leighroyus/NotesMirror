"""Tests for model classes."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import NotesMirror.__main__ as package_main
from NotesMirror.cli.main import app
from NotesMirror.cli.formatter import make_excerpt, render_plain_text
from NotesMirror.db.connection import managed_db
from NotesMirror.models.note import Note
from NotesMirror.models.notebook import Notebook
from NotesMirror.models.sync_run import SyncRun
from tests.fixtures.load_fixtures import load_sample_notes

runner = CliRunner()


def _seed_cli_db(db_path: str) -> None:
    notes = load_sample_notes()
    with managed_db(db_path, read_only=False) as conn:
        conn.execute(
            "INSERT INTO notebooks (id, name, created, updated) VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            ["B2C310D1-013F-7570-88B6-357F6A5C34B0", "Notes"],
        )
        for note in notes:
            conn.execute(
                """
                INSERT INTO notes
                (id, notebook_id, title, content, content_type, created, updated, is_archived, content_hash, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [
                    note["id"],
                    note["notebook_id"],
                    note["title"],
                    note["content"],
                    note.get("content_type", "text"),
                    note["created"],
                    note["updated"],
                    note["is_archived"],
                    None,
                ],
            )


# --- Note tests ---


def test_note_json_serialization():
    """Note should be JSON-serializable after calling to_json()."""
    note = Note(
        id="test-1",
        notebook_id="nb-1",
        title="Test Title",
        content="Test content",
        content_type="text",
        created=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
        updated=datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc),
    )
    json_str = note.to_json()
    assert json_str is not None
    assert "test-1" in json_str
    assert "Test Title" in json_str

    # round-trip works
    data = json.loads(json_str)
    assert data["id"] == "test-1"


def test_render_plain_text_strips_html():
    content = "<div>Hello <b>world</b><br/>again</div>"
    plain = render_plain_text(content, "html")
    assert "<b>" not in plain
    assert "Hello worldagain" in plain


def test_make_excerpt_truncates():
    excerpt = make_excerpt("a" * 200, max_chars=40)
    assert excerpt.endswith("...")
    assert len(excerpt) == 40


def test_note_upsert_sql():
    """Note.upsert_sql() should contain INSERT ... ON CONFLICT."""
    from NotesMirror.models.note import Note
    note = Note(
        id="test-1",
        title="Title",
        content="Content",
        content_type="text",
        created=datetime.now(timezone.utc),
        updated=datetime.now(timezone.utc),
    )
    sql = note.upsert_sql()
    assert "INSERT INTO notes" in sql
    assert "ON CONFLICT" in sql


# --- Notebook tests ---


def test_notebook_upsert_sql():
    """Notebook.upsert_sql should contain INSERT ... ON CONFLICT."""
    nb = Notebook(id="nb-1", name="Test")
    sql = nb.upsert_sql()
    assert "INSERT INTO notebooks" in sql
    assert "ON CONFLICT" in sql


# --- Sync Run tests ---


def test_sync_run_insert_sql():
    """SyncRun.to_insert_sql should return proper INSERT statement."""
    run = SyncRun()
    sql = run.to_insert_sql()
    assert "INSERT INTO sync_runs" in sql


def test_sync_run_mark_success():
    """mark_success sets status = 'success' and finished_at."""
    run = SyncRun()
    run.mark_success()
    assert run.status == "success"
    assert run.finished_at is not None


def test_sync_run_mark_error():
    """mark_error sets status = 'error' and records error_message."""
    run = SyncRun()
    run.mark_error("oops")
    assert run.status == "error"
    assert run.error_message == "oops"


# --- Config tests ---


def test_config_load_save():
    """Settings load/save round-trips correctly."""
    from NotesMirror.cli.config import Settings
    tmp = Path("/tmp/test_settings.json")
    try:
        s = Settings()
        s.save(tmp)
        loaded = Settings.load(tmp)
        assert loaded.db_path != tmp  # db_path should NOT be the tmp path
        assert loaded.config_path == str(tmp)
    finally:
        tmp.unlink(missing_ok=True)


# --- Platform tests ---


def test_platform_detection():
    """Platform helpers are accessible."""
    from NotesMirror.utils.platform import is_linux, is_macos
    assert is_linux() or is_macos()  # should be one of them


def test_check_apple_notes_access_uses_jxa(monkeypatch):
    from NotesMirror.utils import platform as platform_utils

    class Completed:
        returncode = 0
        stdout = "Notes\n"
        stderr = ""

    calls: list[list[str]] = []

    monkeypatch.setattr(platform_utils, "IS_MACOS", True)
    monkeypatch.setattr(platform_utils, "has_osascript", lambda: True)

    def fake_run(cmd, capture_output, text, timeout):
        calls.append(cmd)
        return Completed()

    monkeypatch.setattr(platform_utils.subprocess, "run", fake_run)

    ok, detail = platform_utils.check_apple_notes_access()

    assert ok is True
    assert detail == "Apple Notes automation is available."
    assert calls == [["osascript", "-l", "JavaScript", "-e", "Application('/System/Applications/Notes.app').name()"]]


# --- Fixtures ---


def test_load_sample_fixture():
    """Fixture file exists and is valid JSON."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_notes.json"
    assert fixture_path.exists(), "sample_notes.json must exist"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) > 0


def test_package_main_invokes_app(monkeypatch):
    called: list[str] = []

    monkeypatch.setattr(package_main, "app", lambda: called.append("app"))
    package_main.main()

    assert called == ["app"]


def test_sync_command_blocks_on_linux(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings
    settings = Settings(db_path=str(tmp_path / "notes.duckdb"))
    monkeypatch.setattr("NotesMirror.cli.main.is_linux", lambda: True)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))

    result = runner.invoke(app, ["sync"])

    assert result.exit_code == 1
    assert "not available on Linux" in result.stdout


def test_sync_command_json_blocks_on_linux(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings

    settings = Settings(db_path=str(tmp_path / "notes.duckdb"))
    monkeypatch.setattr("NotesMirror.cli.main.is_linux", lambda: True)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))

    result = runner.invoke(app, ["sync", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"] == "Sync is not available on Linux."
    assert payload["dry_run"] is False


def test_sync_command_runs_sync_engine(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings
    from NotesMirror.sync.sync_engine import SyncReport

    settings = Settings(db_path=str(tmp_path / "notes.duckdb"))
    monkeypatch.setattr("NotesMirror.cli.main.is_linux", lambda: False)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))

    class FakeEngine:
        def __init__(self, db_path: str, syncer=None):
            assert db_path == settings.db_path
            assert syncer is not None

        def sync(self, dry_run: bool = False):
            assert dry_run is True
            return SyncReport(notes_fetched=3, notes_added=1, notes_updated=1, notes_deleted=0)

    monkeypatch.setattr("NotesMirror.cli.main.SyncEngine", FakeEngine)

    result = runner.invoke(app, ["sync", "--dry-run"])

    assert result.exit_code == 0
    assert "fetched=3 added=1 updated=1 deleted=0" in result.stdout


def test_sync_command_json_runs_sync_engine(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings
    from NotesMirror.sync.sync_engine import SyncReport

    settings = Settings(db_path=str(tmp_path / "notes.duckdb"))
    monkeypatch.setattr("NotesMirror.cli.main.is_linux", lambda: False)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))

    class FakeEngine:
        def __init__(self, db_path: str, syncer=None):
            assert db_path == settings.db_path
            assert syncer is not None

        def sync(self, dry_run: bool = False):
            assert dry_run is True
            return SyncReport(notes_fetched=5, notes_added=2, notes_updated=1, notes_deleted=1)

    monkeypatch.setattr("NotesMirror.cli.main.SyncEngine", FakeEngine)

    result = runner.invoke(app, ["sync", "--dry-run", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["notes_fetched"] == 5
    assert payload["notes_added"] == 2
    assert payload["notes_updated"] == 1
    assert payload["notes_deleted"] == 1


def test_doctor_reports_linux_read_only(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings

    settings = Settings(db_path=str(tmp_path / "notes.duckdb"))
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))
    monkeypatch.setattr("NotesMirror.cli.main.is_linux", lambda: True)
    monkeypatch.setattr("NotesMirror.cli.main.is_macos", lambda: False)
    monkeypatch.setattr("NotesMirror.cli.main.has_osascript", lambda: False)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Linux/read-only" in result.stdout
    assert "Not applicable on Linux/read-only mode" in result.stdout


def test_doctor_reports_missing_macos_permissions(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings

    settings = Settings(db_path=str(tmp_path / "notes.duckdb"))
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))
    monkeypatch.setattr("NotesMirror.cli.main.is_linux", lambda: False)
    monkeypatch.setattr("NotesMirror.cli.main.is_macos", lambda: True)
    monkeypatch.setattr("NotesMirror.cli.main.has_osascript", lambda: True)
    monkeypatch.setattr(
        "NotesMirror.cli.main.check_apple_notes_access",
        lambda: (False, "Apple Notes automation check failed: not authorized"),
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "not authorized" in result.stdout
    assert "Full Disk Access" in result.stdout


def test_doctor_json_output(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings

    settings = Settings(db_path=str(tmp_path / "notes.duckdb"))
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))
    monkeypatch.setattr("NotesMirror.cli.main.is_linux", lambda: True)
    monkeypatch.setattr("NotesMirror.cli.main.is_macos", lambda: False)
    monkeypatch.setattr("NotesMirror.cli.main.has_osascript", lambda: False)

    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == "Linux/read-only"
    assert payload["db_path"] == str(tmp_path / "notes.duckdb")
    assert any(check["check"] == "osascript" for check in payload["checks"])
    assert any("apple_notes_access" in failure for failure in payload["failures"])


def test_status_json_missing_db(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings

    settings = Settings(db_path=str(tmp_path / "missing.duckdb"))
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["db_path"] == str(tmp_path / "missing.duckdb")
    assert payload["exists"] is False
    assert payload["error"] == "No database file."


def test_status_json_with_db(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings

    settings = Settings(db_path=str(tmp_path / "notes.duckdb"))
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))
    monkeypatch.setattr("NotesMirror.cli.main.is_linux", lambda: False)

    with managed_db(settings.db_path, read_only=False) as conn:
        conn.execute(
            "INSERT INTO sync_runs (id, started_at, finished_at, status, notes_fetched, notes_added, notes_updated, notes_deleted, error_message) "
            "VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'success', 0, 0, 0, 0, NULL)",
            [1],
        )

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["exists"] is True
    assert payload["schema_version"] == "1"
    assert payload["db_path"] == settings.db_path
    assert payload["last_sync"] is not None


def test_list_json(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings

    settings = Settings(db_path=str(tmp_path / "notes.duckdb"))
    _seed_cli_db(settings.db_path)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))
    monkeypatch.setattr("NotesMirror.cli.main.is_linux", lambda: False)

    result = runner.invoke(app, ["list", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert len(payload) == 2
    assert payload[0]["id"] == "52F57A81-3E3F-4994-9337-A0E4B84B77A3"


def test_get_json(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings

    settings = Settings(db_path=str(tmp_path / "notes.duckdb"))
    _seed_cli_db(settings.db_path)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))
    monkeypatch.setattr("NotesMirror.cli.main.is_linux", lambda: False)

    result = runner.invoke(app, ["get", "52F57A81-3E3F-4994-9337-A0E4B84B77A3", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["title"] == "Sample Note One"
    assert payload["content"].startswith("This is the content")


def test_get_text_strips_html_and_shows_metadata(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings

    settings = Settings(db_path=str(tmp_path / "notes.duckdb"))
    with managed_db(settings.db_path, read_only=False) as conn:
        conn.execute(
            "INSERT INTO notebooks (id, name, created, updated) VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            ["nb-html", "HTML Notes"],
        )
        conn.execute(
            """
            INSERT INTO notes
            (id, notebook_id, title, content, content_type, created, updated, is_archived, content_hash, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                "html-note",
                "nb-html",
                "Rendered Note",
                "<p>Hello <b>there</b></p>",
                "html",
                "2024-01-01T00:00:00+00:00",
                "2024-01-02T00:00:00+00:00",
                False,
                None,
            ],
        )
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))
    monkeypatch.setattr("NotesMirror.cli.main.is_linux", lambda: False)

    result = runner.invoke(app, ["get", "html-note"])

    assert result.exit_code == 0
    assert "Rendered Note" in result.stdout
    assert "id: html-note" in result.stdout
    assert "created: 2024-01-01T00:00:00+00:00" in result.stdout
    assert "updated: 2024-01-02T00:00:00+00:00" in result.stdout
    assert "<b>" not in result.stdout
    assert "Hello there" in result.stdout


def test_search_json(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings

    settings = Settings(db_path=str(tmp_path / "notes.duckdb"))
    _seed_cli_db(settings.db_path)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))
    monkeypatch.setattr("NotesMirror.cli.main.is_linux", lambda: False)

    result = runner.invoke(app, ["search", "shopping", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["title"] == "Shopping List"


def test_search_text_full_and_snippet(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings

    settings = Settings(db_path=str(tmp_path / "notes.duckdb"))
    with managed_db(settings.db_path, read_only=False) as conn:
        conn.execute(
            "INSERT INTO notebooks (id, name, created, updated) VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            ["nb-1", "Inbox"],
        )
        conn.execute(
            """
            INSERT INTO notes
            (id, notebook_id, title, content, content_type, created, updated, is_archived, content_hash, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                "search-note",
                "nb-1",
                "Budget Plan",
                "<p>Budget planning content with several details and milestones for the next quarter.</p>",
                "html",
                "2024-01-01T00:00:00+00:00",
                "2024-01-02T00:00:00+00:00",
                False,
                None,
            ],
        )
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))
    monkeypatch.setattr("NotesMirror.cli.main.is_linux", lambda: False)

    snippet_result = runner.invoke(app, ["search", "budget", "--snippet-length", "50"])
    assert snippet_result.exit_code == 0
    assert "id: search-note" in snippet_result.stdout
    assert "updated: 2024-01-02T00:00:00+00:00" in snippet_result.stdout
    assert "<p>" not in snippet_result.stdout
    assert "..." in snippet_result.stdout

    full_result = runner.invoke(app, ["search", "budget", "--full"])
    assert full_result.exit_code == 0
    assert "Budget planning content with several details" in full_result.stdout
    assert "<p>" not in full_result.stdout


def test_notebooks_json(monkeypatch, tmp_path: Path):
    from NotesMirror.cli.config import Settings

    settings = Settings(db_path=str(tmp_path / "notes.duckdb"))
    _seed_cli_db(settings.db_path)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: settings))
    monkeypatch.setattr("NotesMirror.cli.main.is_linux", lambda: False)

    result = runner.invoke(app, ["notebooks", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["name"] == "Notes"
