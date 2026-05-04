"""Utilities for cross-platform support."""

from NotesMirror.utils.platform import (
    check_apple_notes_access,
    full_disk_access_hint,
    has_apple_notes_access,
    has_osascript,
    is_linux,
    is_macos,
    is_readonly_platform,
)

__all__ = [
    "is_linux",
    "is_macos",
    "has_apple_notes_access",
    "has_osascript",
    "check_apple_notes_access",
    "full_disk_access_hint",
    "is_readonly_platform",
]
