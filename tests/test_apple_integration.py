"""Integration coverage for the Apple Notes JXA adapter."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime

import pytest

from NotesMirror.sync.apple import AppleNotesSyncer
from NotesMirror.utils.platform import has_apple_notes_access, is_macos


def test_split_payload_normalizes_note_rows() -> None:
    payload = [
        {
            "id": "nb-1",
            "name": "Inbox",
            "created": "2024-01-01T00:00:00+00:00",
            "updated": "2024-01-01T00:00:00+00:00",
        },
        {
            "id": "note-1",
            "notebookId": "nb-1",
            "title": "Hello",
            "content": "World",
            "content_type": "text",
            "created": "2024-01-01T00:00:00+00:00",
            "updated": "2024-01-01T01:00:00+00:00",
            "is_archived": False,
        },
    ]

    notes, notebooks = AppleNotesSyncer._split_payload(payload)

    assert len(notebooks) == 1
    assert len(notes) == 1
    assert notes[0]["notebook_id"] == "nb-1"
    assert "notebookId" not in notes[0]


def test_jxa_script_preserves_escape_sequences() -> None:
    assert r"replace(/\r/g, '\n')" in AppleNotesSyncer.JXA_SCRIPT


def test_fetch_all_uses_configured_timeout(monkeypatch) -> None:
    monkeypatch.setattr("NotesMirror.sync.apple.is_macos", lambda: True)

    class Completed:
        returncode = 0
        stdout = "[]"
        stderr = ""

    captured: dict[str, object] = {}

    def fake_run(cmd, capture_output, text, timeout):
        captured["cmd"] = cmd
        captured["timeout"] = timeout
        return Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)

    syncer = AppleNotesSyncer(timeout_seconds=321)
    notes, notebooks = syncer.fetch_all()

    assert notes == []
    assert notebooks == []
    assert captured["timeout"] == 321


def test_fetch_all_timeout_error(monkeypatch) -> None:
    monkeypatch.setattr("NotesMirror.sync.apple.is_macos", lambda: True)

    def fake_run(cmd, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    syncer = AppleNotesSyncer(timeout_seconds=45)

    with pytest.raises(RuntimeError, match="timed out after 45 seconds"):
        syncer.fetch_all()


@pytest.mark.integration
@pytest.mark.skipif(not is_macos(), reason="Apple Notes integration only runs on macOS")
def test_fetch_all_live_macos() -> None:
    if os.environ.get("APPLE_NOTES_RUN_INTEGRATION") != "1":
        pytest.skip("Set APPLE_NOTES_RUN_INTEGRATION=1 to run the live Apple Notes integration test")
    if not has_apple_notes_access():
        pytest.skip("Apple Notes access is unavailable or permissions have not been granted")

    notes, notebooks = AppleNotesSyncer().fetch_all()

    assert isinstance(notes, list)
    assert isinstance(notebooks, list)

    for notebook in notebooks:
        assert "id" in notebook
        assert "name" in notebook

    for note in notes:
        assert "id" in note
        assert "title" in note
        assert "content" in note
        assert "notebook_id" in note
        datetime.fromisoformat(note["created"])
        datetime.fromisoformat(note["updated"])
