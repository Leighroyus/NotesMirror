"""Platform detection helpers."""

from __future__ import annotations

import platform
import shutil
import subprocess

SYSTEM = platform.system()
IS_MACOS = SYSTEM == "Darwin"
IS_LINUX = SYSTEM == "Linux"
NOTES_APP_TARGET = "/System/Applications/Notes.app"


def is_macos() -> bool:
    return IS_MACOS


def is_linux() -> bool:
    return IS_LINUX


def is_readonly_platform() -> bool:
    return IS_LINUX


def has_apple_notes_access() -> bool:
    if not IS_MACOS:
        return False
    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", f"Application({NOTES_APP_TARGET!r}).name()"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and "Notes" in result.stdout
    except Exception:
        return False


def has_osascript() -> bool:
    return shutil.which("osascript") is not None


def check_apple_notes_access() -> tuple[bool, str]:
    """Return Apple Notes access state with a short diagnostic message."""
    if not IS_MACOS:
        return False, "Apple Notes sync is only available on macOS."
    if not has_osascript():
        return False, "`osascript` is not available in PATH."

    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", f"Application({NOTES_APP_TARGET!r}).name()"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return False, f"`osascript` check failed: {exc}"

    if result.returncode == 0 and "Notes" in result.stdout:
        return True, "Apple Notes automation is available."

    detail = (result.stderr or result.stdout or "unknown error").strip()
    return False, f"Apple Notes automation check failed: {detail}"


def full_disk_access_hint(app_name: str = "your terminal app") -> str:
    return (
        "System Settings > Privacy & Security > Full Disk Access "
        f"and ensure {app_name} is enabled."
    )
