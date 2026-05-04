"""Fixture loading helpers for tests."""

from __future__ import annotations

import json
from pathlib import Path


def load_sample_notes() -> list[dict]:
    """Load the sample notes fixture."""
    fixture_path = Path(__file__).with_name("sample_notes.json")
    with fixture_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
