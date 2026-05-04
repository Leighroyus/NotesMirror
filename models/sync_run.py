"""Sync run tracking model."""

from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class SyncRun(BaseModel):
    id: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    status: str = "running"
    notes_fetched: int = 0
    notes_added: int = 0
    notes_updated: int = 0
    notes_deleted: int = 0
    error_message: str | None = None

    def mark_success(self) -> "SyncRun":
        self.status = "success"
        self.finished_at = datetime.now(timezone.utc)
        return self

    def mark_error(self, error: str | BaseException) -> "SyncRun":
        self.status = "error"
        self.finished_at = datetime.now(timezone.utc)
        self.error_message = str(error)
        return self

    def to_insert_sql(self) -> str:
        cols = ["id", "started_at", "finished_at", "status", "notes_fetched",
                "notes_added", "notes_updated", "notes_deleted", "error_message"]
        placeholders = ", ".join("?" for _ in cols)
        return f"INSERT INTO sync_runs ({', '.join(cols)}) VALUES ({placeholders})"

    def insert_params(self) -> tuple[object, ...]:
        return (
            self.id,
            self.started_at,
            self.finished_at,
            self.status,
            self.notes_fetched,
            self.notes_added,
            self.notes_updated,
            self.notes_deleted,
            self.error_message,
        )

    def to_dict(self) -> dict:
        d = self.model_dump()
        d["started_at"] = d["started_at"].isoformat()
        if d["finished_at"]:
            d["finished_at"] = d["finished_at"].isoformat()
        return d
