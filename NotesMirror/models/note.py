"""Note model and helpers."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Note(BaseModel):
    id: str
    notebook_id: str | None = None
    title: str = "(untitled)"
    content: str = ""
    content_type: str = "text"
    created: datetime
    updated: datetime
    is_archived: bool = False
    content_hash: str | None = None
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_row(cls, row: dict) -> Note:
        return cls(
            id=str(row["id"]),
            notebook_id=row.get("notebook_id"),
            title=row.get("title") or "(untitled)",
            content=row.get("content") or "",
            content_type=row.get("content_type") or "text",
            created=_ensure_utc(row.get("created")),
            updated=_ensure_utc(row.get("updated")),
            is_archived=row.get("is_archived") is True,
            content_hash=row.get("content_hash"),
            last_seen_at=_ensure_utc(row.get("last_seen_at")),
        )

    def compute_content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    @property
    def is_dirty(self) -> bool:
        return self.content_hash is None or self.content_hash != self.compute_content_hash()

    def upsert_sql(self) -> str:
        cols = ["id", "notebook_id", "title", "content", "content_type",
                "created", "updated", "is_archived", "content_hash", "last_seen_at"]
        placeholders = ", ".join("?" for _ in cols)
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "id")
        return (
            f"INSERT INTO notes ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO UPDATE SET {updates}"
        )

    def insert_params(self) -> tuple[object, ...]:
        if self.content_hash is None:
            self.content_hash = self.compute_content_hash()
        return (
            self.id,
            self.notebook_id,
            self.title,
            self.content,
            self.content_type,
            self.created,
            self.updated,
            self.is_archived,
            self.content_hash,
            self.last_seen_at,
        )

    def to_dict(self) -> dict:
        d = self.model_dump()
        d["created"] = d["created"].isoformat()
        d["updated"] = d["updated"].isoformat()
        d["last_seen_at"] = d["last_seen_at"].isoformat()
        return d

    def to_json(self) -> str:
        return self.model_dump_json()


def _ensure_utc(dt):
    if dt is None:
        return datetime.now(timezone.utc)
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
