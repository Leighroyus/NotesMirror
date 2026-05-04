"""Apple Notes sync adapter layer."""

from __future__ import annotations

import json
import subprocess

from NotesMirror.utils.platform import NOTES_APP_TARGET, is_macos


class AppleNotesSyncer:
    """Fetches notes from macOS Apple Notes via AppleScript/JXA."""

    JXA_SCRIPT = r"""
    const app = Application("/System/Applications/Notes.app");
    const result = [];

    for (const folder of app.folders()) {
      result.push({
        id: folder.id(),
        name: folder.name(),
        created: null,
        updated: null
      });

      for (const note of folder.notes()) {
        result.push({
          id: note.id(),
          notebookId: folder.id(),
          notebookName: folder.name(),
          title: note.name(),
          content: note.body().replace(/\r/g, '\n'),
          content_type: 'html',
          created: note.creationDate().toISOString(),
          updated: note.modificationDate().toISOString(),
          is_archived: false,
        });
      }
    }

    JSON.stringify(result);
    """

    def __init__(self, verbose: bool = False, timeout_seconds: int = 600):
        self.verbose = verbose
        self.timeout_seconds = timeout_seconds

    def fetch_all(self) -> tuple[list[dict], list[dict]]:
        """Run JXA script and return parsed (notes, notebooks) list."""
        if not is_macos():
            raise RuntimeError("Apple Notes sync is only available on macOS.")

        try:
            result = subprocess.run(
                ["osascript", "-l", "JavaScript", "-e", self.JXA_SCRIPT],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Apple Notes export timed out after "
                f"{self.timeout_seconds} seconds. "
                "Try increasing sync_timeout_seconds in the config if your Notes library is large."
            ) from exc

        if result.returncode != 0:
            raise RuntimeError(
                f"Apple Notes access failed (exit {result.returncode}):\n"
                f"{result.stderr or 'No error output.\n'}"
                f"Hint: grant Full Disk Access to your terminal in System Preferences > Security & Privacy."
            )

        data = json.loads(result.stdout)
        return self._split_payload(data)

    @staticmethod
    def _split_payload(data: list[dict]) -> tuple[list[dict], list[dict]]:
        """Split the mixed JXA payload into note and notebook collections."""
        notebooks: list[dict] = []
        notes: list[dict] = []

        for item in data:
            if "title" not in item:
                notebooks.append(item)
                continue

            note_item = dict(item)
            if "notebookId" in note_item:
                note_item["notebook_id"] = note_item.pop("notebookId")
            notes.append(note_item)

        return notes, notebooks
