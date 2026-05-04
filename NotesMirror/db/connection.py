"""Database connection management."""

from __future__ import annotations

import duckdb
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from NotesMirror.db.schema import ensure_schema, DEFAULT_METADATA
from NotesMirror.utils.platform import IS_MACOS


def open_db(path: str | Path, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection, applying schema if needed."""
    db_path = Path(path)
    need_init = not db_path.exists()

    actual_read_only = read_only or (not IS_MACOS)
    if need_init and actual_read_only:
        raise FileNotFoundError(f"Database does not exist: {db_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path), read_only=actual_read_only)

    if need_init:
        ensure_schema(conn)
        seed_metadata(conn)
        conn.close()
        # Re-open with correct mode after init
        conn = duckdb.connect(str(db_path), read_only=actual_read_only)

    return conn


@contextmanager
def managed_db(path: str | Path, read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    """Context manager for safe DB connection lifecycle."""
    conn = open_db(path, read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()


def seed_metadata(conn: duckdb.DuckDBPyConnection) -> None:
    """Seed initial metadata rows if they don't exist."""
    for key, value in DEFAULT_METADATA.items():
        conn.execute(
            "INSERT INTO app_metadata (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT (key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            [key, value],
        )
