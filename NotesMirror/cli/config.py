"""Application configuration."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, PrivateAttr


CONFIG_FILENAME = "config.json"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_DIR = PROJECT_ROOT / "db"


def _default_db_path() -> str:
    return str(DB_DIR / "notes.duckdb")


def _default_config_path() -> Path:
    return PROJECT_ROOT / CONFIG_FILENAME


class Settings(BaseModel):
    """Application settings."""

    db_path: str = Field(default_factory=_default_db_path)
    sync_interval_minutes: int = Field(default=5, ge=1)
    sync_timeout_seconds: int = Field(default=600, ge=30)
    auto_sync: bool = True
    stale_after_minutes: int = Field(default=30, ge=1)
    dropbox_path: str | None = None
    _config_path: str | None = PrivateAttr(default=None)

    def save(self, path: Path | None = None) -> None:
        target = path or _default_config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(self.model_dump(), fh, indent=2)
        self._config_path = str(target)

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        target = path or _default_config_path()
        if target.exists():
            with open(target, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            loaded = cls(**data)
            loaded._config_path = str(target)
            return loaded
        default = cls()
        default.save(target)
        return default

    @property
    def config_path(self) -> str:
        return self._config_path or str(_default_config_path())


def db_path_for_platform() -> str:
    """Return the recommended db_path for the current platform."""
    return _default_db_path()
