"""Sync orchestration engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from NotesMirror.db.connection import managed_db
from NotesMirror.models.note import Note
from NotesMirror.models.notebook import Notebook
from NotesMirror.models.sync_run import SyncRun
from NotesMirror.sync.apple import AppleNotesSyncer
from NotesMirror.utils.platform import is_linux


@dataclass
class SyncReport:
    notes_fetched: int = 0
    notes_added: int = 0
    notes_updated: int = 0
    notes_deleted: int = 0


class SyncEngine:
    """Synchronize the Apple Notes snapshot into DuckDB."""

    def __init__(self, db_path: str, syncer: AppleNotesSyncer | None = None):
        self.db_path = db_path
        self.syncer = syncer or AppleNotesSyncer()

    def sync(self, dry_run: bool = False) -> SyncReport:
        if is_linux():
            raise RuntimeError("Sync is not available on Linux. This platform is read-only.")

        started_at = datetime.now(timezone.utc)
        sync_run = SyncRun(id=int(started_at.timestamp() * 1_000_000), started_at=started_at)
        report = SyncReport()

        try:
            note_rows, notebook_rows = self.syncer.fetch_all()
            report.notes_fetched = len(note_rows)

            if not dry_run:
                with managed_db(self.db_path, read_only=False) as conn:
                    existing = self._load_existing(conn)

                    for notebook_row in notebook_rows:
                        notebook = Notebook.from_row(notebook_row)
                        conn.execute(notebook.upsert_sql(), notebook.insert_params())

                    seen_ids: set[str] = set()
                    for note_row in note_rows:
                        note = Note.from_row(note_row)
                        note.content_hash = note.compute_content_hash()
                        note.last_seen_at = started_at
                        seen_ids.add(note.id)

                        previous = existing.get(note.id)
                        if previous is None:
                            report.notes_added += 1
                        elif self._note_changed(previous, note):
                            report.notes_updated += 1

                        conn.execute(note.upsert_sql(), note.insert_params())

                    report.notes_deleted = self._delete_missing_notes(conn, seen_ids)
                    sync_run.mark_success()
                    sync_run.notes_fetched = report.notes_fetched
                    sync_run.notes_added = report.notes_added
                    sync_run.notes_updated = report.notes_updated
                    sync_run.notes_deleted = report.notes_deleted
                    conn.execute(sync_run.to_insert_sql(), sync_run.insert_params())

            return report
        except Exception as exc:
            sync_run.mark_error(exc)
            if not dry_run:
                with managed_db(self.db_path, read_only=False) as conn:
                    conn.execute(sync_run.to_insert_sql(), sync_run.insert_params())
            raise

    @staticmethod
    def _load_existing(conn) -> dict[str, dict]:
        cursor = conn.execute(
            """
            SELECT id, notebook_id, title, content_hash, updated, is_archived
            FROM notes
            """
        )
        columns = [desc[0] for desc in cursor.description]
        return {row[0]: dict(zip(columns, row)) for row in cursor.fetchall()}

    @staticmethod
    def _note_changed(previous: dict, note: Note) -> bool:
        return any(
            [
                previous["notebook_id"] != note.notebook_id,
                previous["title"] != note.title,
                previous["content_hash"] != note.content_hash,
                previous["updated"] != note.updated,
                previous["is_archived"] != note.is_archived,
            ]
        )

    @staticmethod
    def _delete_missing_notes(conn, seen_ids: set[str]) -> int:
        rows = conn.execute("SELECT id FROM notes").fetchall()
        existing_ids = {row[0] for row in rows}
        deleted_ids = sorted(existing_ids - seen_ids)
        if not deleted_ids:
            return 0

        placeholders = ", ".join("?" for _ in deleted_ids)
        conn.execute(f"DELETE FROM notes WHERE id IN ({placeholders})", deleted_ids)
        return len(deleted_ids)
