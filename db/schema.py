"""Database schema definitions for the DuckDB cache."""

import duckdb
from pathlib import Path

SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS notebooks (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created     TIMESTAMP,
    updated     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notes (
    id           TEXT PRIMARY KEY,
    notebook_id  TEXT REFERENCES notebooks(id),
    title        TEXT NOT NULL DEFAULT '(untitled)',
    content      TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT 'text',
    created      TIMESTAMP NOT NULL,
    updated      TIMESTAMP NOT NULL,
    is_archived  BOOLEAN NOT NULL DEFAULT FALSE,
    content_hash TEXT,
    last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id             BIGINT PRIMARY KEY,
    started_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at    TIMESTAMP,
    status         TEXT NOT NULL DEFAULT 'running',
    notes_fetched  INTEGER NOT NULL DEFAULT 0,
    notes_added    INTEGER NOT NULL DEFAULT 0,
    notes_updated  INTEGER NOT NULL DEFAULT 0,
    notes_deleted  INTEGER NOT NULL DEFAULT 0,
    error_message  TEXT
);

CREATE TABLE IF NOT EXISTS app_metadata (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notes_title ON notes(title);
CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated);
CREATE INDEX IF NOT EXISTS idx_notes_notebook ON notes(notebook_id);
"""


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Execute the schema DDL against the connection."""
    for stmt in SCHEMA_SQL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)


DEFAULT_METADATA: dict[str, str] = {
    "schema_version": "1",
    "app_version": "0.1.0",
    "database_origin": "localhost",
}
