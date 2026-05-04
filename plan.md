# NotesMirror — Project Plan

## Vision

A cross-platform CLI for Apple Notes where macOS is the sync source and Linux is a read-only consumer of the synced cache. On macOS, the tool reads Apple Notes and writes a local **DuckDB** cache. On Linux, the tool opens that DuckDB file read-only so notes can be searched and viewed offline.

> "Sync on macOS, query anywhere."

### Product Model

- macOS is the only machine that talks to Apple Notes.
- DuckDB is the portable cache artifact.
- Linux never syncs from a source system directly.
- Moving the DuckDB file between machines is handled externally.
- The default transfer mechanism for this project will be Dropbox.

---

## Architecture — 3 Layers

```text
┌───────────────────────────────────────────────────┐
│                   CLI Layer                       │
│      typer commands: list, get, search, sync     │
└──────────────────────────────┬────────────────────┘
                               │
┌──────────────────────────────▼────────────────────┐
│                DuckDB Cache Layer                 │
│        ┌──────────────┐     ┌────────────────┐    │
│        │ notes table  │     │ sync_runs/meta │    │
│        └──────────────┘     └────────────────┘    │
└──────────────────────────────┬────────────────────┘
                               │
┌──────────────────────────────▼────────────────────┐
│              Apple Notes Sync Layer               │
│          osascript -l JavaScript (JXA)            │
└───────────────────────────────────────────────────┘
```

### Platform Behavior

- macOS:
  - can `sync`
  - can query the local DuckDB cache
- Linux:
  - can query the DuckDB cache
  - cannot sync
  - opens the database in read-only mode

### Dropbox Distribution Model

- The DuckDB file lives inside a dedicated Dropbox folder shared by both machines.
- macOS writes the database file into Dropbox after each successful sync.
- Dropbox propagates that file to Linux automatically.
- Linux reads the locally synced Dropbox copy in read-only mode.
- The app does not call the Dropbox API directly in v1; it relies on the installed Dropbox desktop app.

### Flow

1. On macOS, `notes sync` reads Apple Notes via JXA.
2. The sync engine normalizes notes and notebooks.
3. Data is upserted into DuckDB and stale rows are reconciled.
4. Any query command reads from DuckDB.
5. On Linux, query commands read the copied DuckDB file and report cache freshness.

### Recommended Dropbox Layout

```text
Dropbox/
└── apple-notes-cli/
    ├── notes.duckdb
    ├── notes.duckdb.sha256
    └── metadata.json
```

- `notes.duckdb` is the cache consumed by both platforms.
- `notes.duckdb.sha256` stores the checksum of the latest completed export.
- `metadata.json` stores lightweight sync metadata such as export host, export time, schema version, and app version.

---

## DuckDB Schema

```sql
CREATE TABLE IF NOT EXISTS notebooks (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created     TIMESTAMP,
    updated     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notes (
    id           TEXT PRIMARY KEY,
    notebook_id  TEXT REFERENCES notebooks(id) ON DELETE SET NULL,
    title        TEXT NOT NULL DEFAULT '(untitled)',
    content      TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT 'text',
    created      TIMESTAMP NOT NULL,
    updated      TIMESTAMP NOT NULL,
    is_archived  BOOLEAN NOT NULL DEFAULT FALSE,
    content_hash TEXT,
    last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id             BIGINT PRIMARY KEY,
    started_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at    TIMESTAMP,
    status         TEXT NOT NULL DEFAULT 'running',
    notes_fetched  INTEGER NOT NULL DEFAULT 0,
    notes_added    INTEGER NOT NULL DEFAULT 0,
    notes_updated  INTEGER NOT NULL DEFAULT 0,
    notes_deleted  INTEGER NOT NULL DEFAULT 0,
    error_message  TEXT
);

CREATE TABLE IF NOT EXISTS app_metadata (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notes_title ON notes(title);
CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated);
CREATE INDEX IF NOT EXISTS idx_notes_notebook ON notes(notebook_id);
```

### Notes on Schema

- `id` is the Apple Notes note identifier.
- `last_seen_at` supports full-sync reconciliation.
- `content_hash` makes it easy to detect changes without diffing large bodies repeatedly.
- `app_metadata` stores values such as schema version, database origin, and last successful sync time.

---

## Project Structure

```text
NotesMirror/
├── pyproject.toml
├── NotesMirror/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── formatter.py
│   │   └── config.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── schema.py
│   │   └── query.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── note.py
│   │   ├── notebook.py
│   │   └── sync_run.py
│   ├── sync/
│   │   ├── __init__.py
│   │   ├── apple.py
│   │   └── sync_engine.py
│   └── utils/
│       ├── __init__.py
│       └── platform.py
├── tests/
│   ├── test_sync_apple.py
│   ├── test_db_query.py
│   ├── test_cli.py
│   └── fixtures/
├── plan.md
└── README.md
```

---

## CLI Interface

```bash
# Sync and status
notes sync                          # macOS only
notes sync --dry-run
notes sync --verbose
notes status                        # show db path, mode, last sync time, freshness

# Notes
notes list --count 20
notes list --notebook "Work"
notes list --since 2024-01-01
notes list --archived
notes get <note-id>
notes get <note-id> --format json

# Search
notes search <query>
notes search <query> --notebook "Work"
notes search <query> --title-only
notes search <query> --updated-since 2024-01-01

# Notebooks
notes notebooks
notes notebooks --with-count

# Export
notes export --format markdown
notes export --format json --output notes.json

# Config
notes config show
notes config set db_path ~/Library/ApplicationSupport/apple-notes-cli/notes.duckdb
notes config set sync_interval_minutes 5
```

### Platform Rules

- `notes sync` fails on Linux with a clear read-only message.
- `notes notebooks create` is out of scope for v1.
- Query commands work on both macOS and Linux if the DB file exists.

---

## Sync Logic

### Sync Engine (`sync_engine.py`)

The sync engine has two v1 modes:

1. **Full sync:** Fetch all notes, upsert current rows, and remove stale rows.
2. **Dry run:** Compute what would change without writing to the database.

```python
class SyncEngine:
    def __init__(self, db: Connection, syncer: AppleNotesSyncer):
        self.db = db
        self.syncer = syncer

    def sync(self, dry_run: bool = False) -> SyncReport:
        started_at = utcnow()
        notes, notebooks = self.syncer.fetch_all()
        report = self._reconcile_snapshot(
            notes=notes,
            notebooks=notebooks,
            started_at=started_at,
            dry_run=dry_run,
        )
        self._log_run(report)
        return report
```

### Reconciliation Rules

- Insert notes that do not exist locally.
- Update notes whose normalized content or metadata changed.
- Mark every synced row with the current sync timestamp.
- Delete or tombstone rows not seen in the current full snapshot.
- Record one `sync_runs` row per invocation.

### macOS Adapter Details

Uses JavaScript for Automation (JXA) to return structured JSON:

```javascript
const app = Application("Notes");
const notes = [];

app.includeStandardAdditions = true;

for (const nb of app.folders()) {
  for (const note of nb.notes()) {
    notes.push({
      id: note.id(),
      notebookId: nb.id(),
      notebookName: nb.name(),
      title: note.name(),
      content: note.body(),
      created: note.creationDate().toISOString(),
      updated: note.modificationDate().toISOString()
    });
  }
}

JSON.stringify(notes);
```

### Permission Handling

- Detect and report missing macOS Automation or Full Disk Access permissions.
- Fail the sync with a clear remediation message instead of partial writes.

---

## Query Strategy

- Default queries are simple SQL over the local DuckDB cache.
- Title, notebook, and updated timestamp should be indexed.
- Body search in v1 can use `LIKE` or `ILIKE`, but performance claims should stay modest.
- If body search becomes a bottleneck, add a dedicated full-text strategy later.

Example:

```sql
SELECT id, title, updated
FROM notes
WHERE title ILIKE '%' || ? || '%'
   OR content ILIKE '%' || ? || '%'
ORDER BY updated DESC
LIMIT ?;
```

---

## Configuration

Required settings:

- `db_path`: location of the DuckDB file
- `sync_interval_minutes`: when macOS query commands may trigger auto-sync

Optional settings:

- `auto_sync`: enable or disable automatic sync checks on macOS
- `stale_after_minutes`: threshold for warning that the cache is old
- `dropbox_path`: optional explicit path to the shared Dropbox folder if `db_path` is derived from it

### Linux Expectations

- The DB file must already exist at `db_path`.
- Linux opens the DB in read-only mode.
- If the file is missing, commands should fail with a clear message that this machine is a cache consumer, not a sync source.

### Dropbox Setup

Recommended setup on both machines:

1. Install the Dropbox desktop app and sign in to the same Dropbox account.
2. Create a dedicated folder such as `Dropbox/apple-notes-cli/`.
3. Ensure that folder is synced locally on both machines.
4. Point `db_path` to the local Dropbox path for `notes.duckdb`.
5. On Linux, keep the folder locally synced rather than treating it as online-only storage.

Operational guidance:

- Dropbox states that synced files are kept up to date everywhere you use Dropbox, so using one shared `notes.duckdb` file is a good fit for this cache-distribution model.
- Dropbox selective sync is configured per computer, so the app folder can be kept on both machines even if other Dropbox folders are excluded.
- Linux Dropbox support does not include the same online-only behavior as some other platforms, so the notes folder should remain fully local on Linux.

---

## Implementation Phases

### Phase 1: Cache and Query Foundation
- [ ] Project structure and `pyproject.toml`
- [ ] DuckDB connection and schema setup
- [ ] Pydantic models for `Note`, `Notebook`, and `SyncRun`
- [ ] Basic CLI: `status`, `list`, `get`, `search`, `notebooks`
- [ ] Read-only DB open mode for Linux
- [ ] Test suite skeleton

### Phase 2: Apple Notes Sync
- [ ] `AppleNotesSyncer` JXA integration
- [ ] Snapshot normalization for notes and notebooks
- [ ] `SyncEngine` full-sync reconciliation
- [ ] Sync run logging and error handling
- [ ] macOS permission checks

### Phase 3: UX and Platform Rules
- [ ] Auto-sync on macOS query commands
- [ ] Linux read-only guardrails for `sync`
- [ ] Output formatters for text, JSON, and Markdown
- [ ] Staleness reporting in `notes status`
- [ ] Export command
- [ ] Dropbox-oriented setup docs and path validation

### Phase 4: Packaging and Quality
- [ ] Tests for sync, queries, and CLI behavior
- [ ] `README.md` with macOS and Linux usage instructions
- [ ] `pre-commit` hooks with `ruff` and `mypy`
- [ ] GitHub Actions for macOS and Linux
- [ ] Packaging and installation docs

---

## Edge Cases and Gotchas

1. macOS permissions can block Apple Notes access even if the script is otherwise valid.
2. Apple Notes content may contain HTML or rich text markup; define a canonical stored representation early.
3. A full sync must reconcile deletions or the cache will drift permanently.
4. Linux users need clear staleness messaging because that machine never refreshes the source directly.
5. The copied DuckDB file may be temporarily unavailable or mid-sync while Dropbox is still updating it locally.
6. Selective sync settings are per machine, so the shared notes folder can accidentally exist on macOS but not on Linux.
7. If Dropbox is paused, indexing, or not connected, the Linux cache may be older than the last successful macOS sync.

### Dropbox-Specific Export Rules

- Write exports on macOS to a temporary file in the same Dropbox folder, then atomically rename to `notes.duckdb` after the sync succeeds.
- Only update `notes.duckdb.sha256` and `metadata.json` after the final database file is in place.
- On Linux, if the checksum sidecar and database timestamp disagree, warn that Dropbox may still be syncing.
- `notes status` should surface both:
  - the last successful application sync time recorded inside DuckDB
  - the filesystem modification time of the local `notes.duckdb`

These rules are an implementation recommendation rather than a Dropbox requirement. They reduce the chance that Linux opens a partially updated cache while Dropbox is still processing file changes.

---

## Example Flow

```bash
# On macOS
notes sync

# On Linux later
notes search "budget"
```

1. macOS reads Apple Notes and writes `notes.duckdb`.
2. Dropbox syncs `notes.duckdb`, `notes.duckdb.sha256`, and `metadata.json` to the shared folder.
3. Linux opens the DB read-only.
4. The CLI reports the last successful sync time.
5. Query commands return cached results without contacting Apple Notes.

---

## Future Extensions

- [ ] Note creation and editing on macOS
- [ ] Diff support against previous cached revisions
- [ ] Optional note revision history table
- [ ] Better full-text search
- [ ] Support for exporting a portable snapshot bundle alongside the DuckDB file

---

## Ordered Implementation Checklist

### 1. Project Bootstrap
- [ ] Create `pyproject.toml` with `typer`, `rich`, `duckdb`, `pydantic`, and `pytest`
- [ ] Create package layout under `NotesMirror/`
- [ ] Add CLI entry point in `__main__.py`
- [ ] Add base test structure and fixtures directories

### 2. Configuration and Platform Detection
- [ ] Define config model for `db_path`, `sync_interval_minutes`, `auto_sync`, `stale_after_minutes`, and optional `dropbox_path`
- [ ] Implement config load/save logic
- [ ] Implement platform detection helpers for macOS vs Linux
- [ ] Add read-only mode detection for Linux

### 3. DuckDB Foundation
- [ ] Implement database connection management
- [ ] Implement schema creation for `notes`, `notebooks`, `sync_runs`, and `app_metadata`
- [ ] Add schema version tracking in `app_metadata`
- [ ] Support read-write open on macOS and read-only open on Linux

### 4. Query Layer
- [ ] Implement list notes query
- [ ] Implement get note by ID query
- [ ] Implement search query across title and content
- [ ] Implement list notebooks query
- [ ] Implement status query for last successful sync and cache metadata

### 5. Basic Cross-Platform CLI
- [ ] Implement `notes status`
- [ ] Implement `notes list`
- [ ] Implement `notes get`
- [ ] Implement `notes search`
- [ ] Implement `notes notebooks`
- [ ] Add consistent text and JSON output formatting

### 6. Dropbox Path and Cache Validation
- [ ] Validate that `db_path` exists for query commands
- [ ] Add optional checks that `db_path` is under the configured Dropbox folder
- [ ] Read local file modification time for freshness reporting
- [ ] Define user-facing errors for missing DB, unreadable DB, and stale cache

### 7. Apple Notes Adapter
- [ ] Implement JXA script generation or embedded script loading
- [ ] Execute `osascript -l JavaScript` and capture JSON output
- [ ] Parse notebooks and notes into normalized models
- [ ] Add robust error handling for malformed output and command failure

### 8. macOS Permission Handling
- [ ] Detect Apple Notes access failures cleanly
- [ ] Detect likely Automation or Full Disk Access issues
- [ ] Return actionable remediation messages
- [ ] Cover permission-denied cases in tests where possible

### 9. Full Sync Engine
- [ ] Implement sync run start/finish logging
- [ ] Upsert notebooks
- [ ] Upsert notes
- [ ] Compute `content_hash` for change detection
- [ ] Update `last_seen_at` during each sync
- [ ] Reconcile deleted notes not present in the latest snapshot
- [ ] Support `--dry-run` reporting

### 10. Safe Dropbox Export
- [ ] Write the refreshed database to a temporary file in the Dropbox folder
- [ ] Atomically rename the temporary file to `notes.duckdb` after success
- [ ] Write `notes.duckdb.sha256`
- [ ] Write `metadata.json` with export host, export time, schema version, and app version
- [ ] Ensure sidecar files are only updated after the DB write completes

### 11. macOS Sync Command
- [ ] Implement `notes sync`
- [ ] Add `--dry-run`
- [ ] Add `--verbose`
- [ ] Add auto-sync eligibility checks for macOS query commands
- [ ] Prevent sync attempts on Linux with a clear error

### 12. Freshness and Status UX
- [ ] Show last successful sync time from DuckDB
- [ ] Show local filesystem modification time for `notes.duckdb`
- [ ] Warn if Dropbox may still be syncing based on sidecar mismatch or file timing
- [ ] Warn when cache age exceeds `stale_after_minutes`
- [ ] Make `notes status` the canonical diagnostics command

### 13. Export and Formatting
- [ ] Implement `notes export --format markdown`
- [ ] Implement `notes export --format json`
- [ ] Normalize output for piping and scripting
- [ ] Keep human-readable output concise and stable

### 14. Testing
- [ ] Unit tests for config and platform helpers
- [ ] Unit tests for schema creation and queries
- [ ] Unit tests for sync reconciliation logic
- [ ] CLI tests for macOS vs Linux command behavior
- [ ] Tests for stale cache and missing DB messaging
- [ ] Tests for Dropbox sidecar validation behavior

### 15. Documentation and Packaging
- [ ] Document macOS setup for Apple Notes permissions
- [ ] Document Dropbox setup on both machines
- [ ] Document Linux read-only usage expectations
- [ ] Add installation instructions
- [ ] Add GitHub Actions for macOS and Linux test runs
- [ ] Add `ruff`, `mypy`, and `pre-commit`

### Suggested First Milestone

Target the first usable milestone in this order:

1. Local config and DuckDB schema
2. `status`, `list`, `get`, and `search` against an existing DB
3. Apple Notes sync on macOS
4. Dropbox-safe export flow
5. Linux read-only consumption and freshness reporting

That sequence gives you a usable query tool early, then adds source sync, then hardens the cross-machine workflow.
