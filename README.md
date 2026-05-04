# NotesMirror

Cross-platform CLI for Apple Notes with DuckDB cache. Sync on macOS, query and search on any platform.

## Architecture

- **macOS**: Sync Apple Notes locally using AppleScript/JXA, store in DuckDB
- **Linux/Read-only**: Open DuckDB database in read-only mode for queries
- **Dropbox sync**: Database file syncs between machines via Dropbox

## Requirements

- Python 3.11+
- macOS (for sync), or Linux (read-only mode)
- DuckDB >= 0.10.0 (included as dependency)
- Apple Notes app (full disk access required on macOS)

## Installation

```bash
cd NotesMirror
pip install -e .
```

## Setup (macOS)

### Apple Notes Permissions

Grant Full Disk Access to your terminal:

1. System Settings → Privacy & Security → Full Disk Access
2. Add your terminal app (Terminal.app, iTerm2, VS Code, etc.)

Then verify runtime access with:

```bash
notes doctor
```

### Dropbox Setup

1. Put `notes.duckdb` in a Dropbox-synced folder shared by your macOS and Linux machines.
2. Make sure the file is fully synced locally on Linux.
3. Confirm the configured database path with:

```bash
notes config
```

4. Start from `config.example.json` and create your local `config.json`.
5. If needed, update `config.json` manually so `db_path` points at the Dropbox copy of `notes.duckdb`.
6. Run:

```bash
notes status
notes doctor
```

to verify the Linux machine can see the cache and the macOS machine can sync.

## Usage

```bash
# Show database status
notes status
notes status --json

# List notes
notes list
notes list --count 50
notes list --notebook "B2C310D1-013F-7570-88B6-357F6A5C34B0"
notes list --archived
notes list --since 2024-01-01
notes list --json

# Get single note
notes get <note_id>
notes get <note_id> --json

# Search notes
notes search "keyword"
notes search "meeting" --notebook "Inbox"
notes search "budget" --full
notes search "budget" --snippet-length 300
notes search "budget" --json

# List notebooks
notes notebooks
notes notebooks --json

# Sync (macOS only)
notes sync
notes sync --dry-run
notes sync --json
notes sync --dry-run --json

# Diagnostics
notes doctor
notes doctor --json

# Config
notes config
```

### JSON Output

The following commands support `--json` for scripting and automation:

- `notes doctor --json`
- `notes status --json`
- `notes sync --json`
- `notes list --json`
- `notes get <note_id> --json`
- `notes search <query> --json`
- `notes notebooks --json`

### Text Output

Human-readable `notes get` and `notes search` output now:

- strips HTML tags before displaying note content
- shows the note ID
- shows the created timestamp
- shows the updated timestamp

In text mode, `notes search` defaults to a snippet preview. Use:

- `--full` to print the full matching note content
- `--snippet-length <n>` to control the preview length

## File Structure

```
NotesMirror/
├── pyproject.toml
├── NotesMirror/
│   ├── cli/
│   │   ├── config.py
│   │   ├── formatter.py
│   │   └── main.py
│   ├── db/
│   │   ├── connection.py
│   │   ├── schema.py
│   │   └── query.py
│   ├── models/
│   │   ├── note.py
│   │   ├── notebook.py
│   │   └── sync_run.py
```

## Development

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q tests/test_db_query.py
.venv/bin/python -m pytest -q tests/test_models.py
.venv/bin/python -m pytest -q tests/test_cli.py
```

### Apple Notes Integration Test

The default test suite does not call the live `osascript` / JXA adapter. A gated integration test is available for macOS:

```bash
APPLE_NOTES_RUN_INTEGRATION=1 pytest -q tests/test_apple_integration.py
```

This test will skip automatically unless all of the following are true:

1. The machine is running macOS.
2. `APPLE_NOTES_RUN_INTEGRATION=1` is set.
3. The current terminal session has Apple Notes access.

The live test validates that:

- `osascript` can talk to Apple Notes
- the returned payload can be parsed
- note rows include the normalized `notebook_id` field
- date fields are valid ISO timestamps

### Manual Sync Smoke Test

Use this on macOS when you want to verify the full end-to-end path:

```bash
source .venv/bin/activate
notes doctor
notes config
notes sync
notes status
notes list --count 5
```

Expected result:

1. `notes sync` completes without a permission or JXA runtime error.
2. `notes status` shows a recent sync timestamp.
3. `notes list --count 5` returns notes from the local DuckDB cache.

If the smoke test fails, check:

- Full Disk Access for the terminal app
- macOS Automation prompts for Apple Notes
- whether the current login session can control the Notes app via `osascript`

`notes doctor` is the fastest way to see whether the current machine can:

- find the configured DuckDB path
- access `osascript`
- talk to Apple Notes on macOS
- distinguish macOS sync mode from Linux read-only mode

## License

MIT
