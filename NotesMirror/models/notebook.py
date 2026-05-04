"""Notebook model."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel


class Notebook(BaseModel):
    id: str
    name: str
    created: datetime | None = None
    updated: datetime | None = None
    note_count: int = 0

    @classmethod
    def from_row(cls, row: dict) -> Notebook:
        return cls(
            id=str(row["id"]),
            name=str(row["name"]),
            created=_ensure_utc(row.get("created")),
            updated=_ensure_utc(row.get("updated")),
            note_count=int(row.get("note_count") or 0),
        )

    def upsert_sql(self) -> str:
        cols = ["id", "name", "created", "updated"]
        placeholders = ", ".join("?" for _ in cols)
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "id")
        return (
            f"INSERT INTO notebooks ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO UPDATE SET {updates}"
        )

    def insert_params(self) -> tuple[object, ...]:
        return (self.id, self.name, self.created, self.updated)


def _ensure_utc(dt):
    if dt is None:
        return datetime.now(timezone.utc)
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
