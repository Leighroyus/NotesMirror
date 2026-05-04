"""DuckDB database layer."""

from NotesMirror.db.connection import managed_db, open_db
from NotesMirror.db.query import get_note, get_status_info, list_notebooks, list_notes, search_notes
from NotesMirror.db.schema import SCHEMA_SQL, ensure_schema

__all__ = [
    "open_db",
    "managed_db",
    "ensure_schema",
    "SCHEMA_SQL",
    "list_notes",
    "get_note",
    "search_notes",
    "list_notebooks",
    "get_status_info",
]
