"""Output formatters for CLI commands."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Any


def to_json(obj: Any, *, indent: int | None = 2) -> str:
    """Convert any object to JSON string (handles datetime serialization)."""
    return json.dumps(obj, default=_json_serializer, indent=indent)


def _json_serializer(obj) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts)


def render_plain_text(content: str, content_type: str) -> str:
    """Render note content for human-readable output."""
    if content_type != "html":
        return content

    stripper = _HTMLStripper()
    stripper.feed(content)
    text = html.unescape(stripper.get_text())
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_excerpt(content: str, *, max_chars: int = 160) -> str:
    """Return a compact single-paragraph excerpt for CLI search results."""
    normalized = re.sub(r"\s+", " ", content).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
