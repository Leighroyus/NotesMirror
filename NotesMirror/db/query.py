"""Query helper functions for the DuckDB cache layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

from NotesMirror.models.note import Note
from NotesMirror.models.notebook import Notebook
def _to_row_dicts(cursor) -> list[dict]:
    """Convert DuckDB result cursor to list of column-name dicts."""
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# --- Notes ---


def list_notes(conn: "duckdb.DuckDBPyConnection", count: int = 20, notebook: str | None = None,
               since: str | None = None, archived: bool = False) -> list[Note]:
    conditions: list[str] = []
    params: list = []

    if notebook:
        conditions.append("notebook_id = ?")
        params.append(notebook)
    if since:
        conditions.append("created > ?")
        params.append(since)
    if not archived:
        conditions.append("is_archived = FALSE")

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"""
        SELECT id, notebook_id, title, content, content_type, created,
               updated, is_archived, content_hash, last_seen_at
        FROM notes
        {where} ORDER BY updated DESC LIMIT ?
    """
    params.append(count)

    cursor = conn.execute(sql, params)
    return [Note.from_row(row) for row in _to_row_dicts(cursor)]


def get_note(conn: "duckdb.DuckDBPyConnection", note_id: str) -> Note:
    cursor = conn.execute(
        "SELECT id, notebook_id, title, content, content_type, created, updated, "
        "is_archived, content_hash, last_seen_at FROM notes WHERE id = ?",
        [note_id],
    )
    rows = _to_row_dicts(cursor)
    if not rows:
        raise ValueError(f"Note not found: {note_id}")
    return Note.from_row(rows[0])


def search_notes(conn: "duckdb.DuckDBPyConnection", query: str, notebook: str | None = None,
                 title_only: bool = False, updated_since: str | None = None,
                 count: int = 50) -> list[Note]:
    conditions: list[str] = []
    params: list = []
    term = f"%{query}%"

    if notebook:
        conditions.append("notebook_id = ?")
        params.append(notebook)

    if title_only:
        conditions.append("title ILIKE ?")
        params.append(term)
    else:
        conditions.append("(title ILIKE ? OR content ILIKE ?)")
        params.extend([term, term])

    if updated_since:
        conditions.append("updated > ?")
        params.append(updated_since)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"""
        SELECT id, notebook_id, title, content, content_type, created, updated,
               is_archived, content_hash, last_seen_at
        FROM notes {where} ORDER BY updated DESC LIMIT ?
    """
    params.append(count)

    cursor = conn.execute(sql, params)
    return [Note.from_row(row) for row in _to_row_dicts(cursor)]


# --- Notebooks ---


def list_notebooks(conn: "duckdb.DuckDBPyConnection", with_count: bool = False) -> list[Notebook]:
    if with_count:
        sql = """
            SELECT nb.id, nb.name, nb.created, nb.updated,
                   COUNT(n.id) as note_count
            FROM notebooks nb
            LEFT JOIN notes n ON nb.id = n.notebook_id
            GROUP BY nb.id, nb.name, nb.created, nb.updated ORDER BY nb.name
        """
    else:
        sql = "SELECT id, name, created, updated FROM notebooks ORDER BY name"

    cursor = conn.execute(sql)
    return [Notebook.from_row(row) for row in _to_row_dicts(cursor)]


# --- Status / Metadata ---


def get_status_info(conn: "duckdb.DuckDBPyConnection") -> dict:
    info: dict = {}

    row = conn.execute("SELECT started_at FROM sync_runs WHERE status='success' ORDER BY started_at DESC LIMIT 1").fetchone()
    info["last_sync_time"] = row[0] if row else None

    row = conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()
    info["schema_version"] = row[0] if row else "unknown"

    row = conn.execute("SELECT value FROM app_metadata WHERE key='app_version'").fetchone()
    info["app_version"] = row[0] if row else "unknown"

    row = conn.execute("SELECT COUNT(*) FROM notes").fetchone()
    info["note_count"] = row[0]

    row = conn.execute("SELECT COUNT(*) FROM notebooks").fetchone()
    info["notebook_count"] = row[0]

    row = conn.execute("SELECT COUNT(*) FROM sync_runs WHERE status='success'").fetchone()
    info["success_sync_count"] = row[0]

    return info


def get_status(conn: "duckdb.DuckDBPyConnection") -> dict:
    """Backward-compatible alias for status retrieval."""
    info = get_status_info(conn)
    return {
        "schema_version": info["schema_version"],
        "last_sync": info["last_sync_time"],
        "note_count": info["note_count"],
        "notebook_count": info["notebook_count"],
        "app_version": info["app_version"],
        "success_sync_count": info["success_sync_count"],
    }
