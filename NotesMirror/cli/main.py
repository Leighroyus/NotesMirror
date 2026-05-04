"""NotesMirror — entry point."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from NotesMirror.cli.config import Settings
from NotesMirror.cli.formatter import make_excerpt, render_plain_text, to_json
from NotesMirror.db.connection import managed_db
from NotesMirror.db.query import get_note, get_status, list_notebooks, list_notes, search_notes
from NotesMirror.sync.apple import AppleNotesSyncer
from NotesMirror.sync.sync_engine import SyncEngine
from NotesMirror.utils.platform import (
    check_apple_notes_access,
    full_disk_access_hint,
    has_osascript,
    is_linux,
    is_macos,
)

console = Console()
app = typer.Typer()


def _build_doctor_report(settings: Settings) -> dict[str, object]:
    db_path = Path(settings.db_path)
    checks: list[dict[str, object]] = []
    failures: list[str] = []

    def add_check(check: str, ok: bool, detail: str) -> None:
        checks.append({"check": check, "ok": ok, "detail": detail})
        if not ok:
            failures.append(f"{check}: {detail}")

    add_check("platform", True, "macOS" if is_macos() else "Linux/read-only" if is_linux() else "unsupported")
    add_check("db_path_parent", db_path.parent.exists(), str(db_path.parent))
    add_check("db_file", db_path.exists(), str(db_path))

    osascript_ok = has_osascript()
    add_check("osascript", osascript_ok, "available" if osascript_ok else "`osascript` not found in PATH")

    if is_macos():
        access_ok, access_detail = check_apple_notes_access()
        add_check("apple_notes_access", access_ok, access_detail)
        if not access_ok:
            add_check("full_disk_access_hint", False, full_disk_access_hint())
    else:
        add_check("apple_notes_access", False, "Not applicable on Linux/read-only mode")

    return {
        "mode": "macOS" if is_macos() else "Linux/read-only" if is_linux() else "unsupported",
        "db_path": str(db_path),
        "checks": checks,
        "failures": failures,
    }


def _build_status_report(settings: Settings) -> dict[str, object]:
    db_path = Path(settings.db_path)
    report: dict[str, object] = {
        "db_path": str(db_path),
        "exists": db_path.exists(),
    }
    if not db_path.exists():
        report["error"] = "No database file."
        return report

    with managed_db(db_path, read_only=is_linux()) as conn:
        report.update(get_status(conn))
    return report


def _build_sync_report(report: object, *, dry_run: bool) -> dict[str, object]:
    return {
        "dry_run": dry_run,
        "notes_fetched": int(getattr(report, "notes_fetched")),
        "notes_added": int(getattr(report, "notes_added")),
        "notes_updated": int(getattr(report, "notes_updated")),
        "notes_deleted": int(getattr(report, "notes_deleted")),
    }


def _note_payload(note: object) -> dict[str, object]:
    return {
        "id": str(getattr(note, "id")),
        "notebook_id": getattr(note, "notebook_id"),
        "title": str(getattr(note, "title")),
        "content": str(getattr(note, "content")),
        "content_type": str(getattr(note, "content_type")),
        "created": getattr(note, "created").isoformat(),
        "updated": getattr(note, "updated").isoformat(),
        "is_archived": bool(getattr(note, "is_archived")),
        "content_hash": getattr(note, "content_hash"),
        "last_seen_at": getattr(note, "last_seen_at").isoformat(),
    }


def _notebook_payload(notebook: object) -> dict[str, object]:
    created = getattr(notebook, "created")
    updated = getattr(notebook, "updated")
    return {
        "id": str(getattr(notebook, "id")),
        "name": str(getattr(notebook, "name")),
        "created": created.isoformat() if created is not None else None,
        "updated": updated.isoformat() if updated is not None else None,
        "note_count": int(getattr(notebook, "note_count")),
    }


def _print_note_text(note: object, *, full_content: bool, snippet_length: int = 160) -> None:
    plain_content = render_plain_text(str(getattr(note, "content")), str(getattr(note, "content_type")))
    console.print(f"[bold]{getattr(note, 'title')}[/bold]")
    console.print(f"id: {getattr(note, 'id')}")
    console.print(f"created: {getattr(note, 'created').isoformat()}")
    console.print(f"updated: {getattr(note, 'updated').isoformat()}")
    console.print("")
    if full_content:
        console.print(plain_content)
    else:
        console.print(make_excerpt(plain_content, max_chars=snippet_length))


@app.command()
def status(as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON output.")):
    """Show database status."""
    settings = Settings.load()
    report = _build_status_report(settings)

    if as_json:
        typer.echo(to_json(report))
        return

    if not bool(report["exists"]):
        console.print("No database file.")
        return

    table = Table()
    table.add_row("schema_version", str(report["schema_version"]))
    table.add_row("last_sync", str(report["last_sync"]))
    table.add_row("note_count", str(report["note_count"]))
    table.add_row("db_path", str(report["db_path"]))
    console.print(table)


@app.command()
def list(
    count: int = typer.Option(20, "-c", "--count"),
    notebook: str | None = typer.Option(None, "-n", "--notebook"),
    since: str | None = typer.Option(None, "-s", "--since"),
    archived: bool = typer.Option(False, "-a", "--archived"),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON output."),
):
    """List notes."""
    db_path = Settings.load().db_path
    with managed_db(db_path, read_only=is_linux()) as conn:
        notes = list_notes(conn, count=count, notebook=notebook, since=since, archived=archived)
    if as_json:
        typer.echo(to_json([_note_payload(note) for note in notes]))
        return
    table = Table()
    table.add_column("id")
    table.add_column("title")
    for note in notes:
        table.add_row(note.id, note.title or "(untitled)")
    console.print(table)


@app.command()
def get(note_id: str, as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON output.")):
    """Get one note."""
    db_path = Settings.load().db_path
    with managed_db(db_path, read_only=is_linux()) as conn:
        note = get_note(conn, note_id)
    if as_json:
        typer.echo(to_json(_note_payload(note)))
        return
    _print_note_text(note, full_content=True)


@app.command()
def search(
    query: str,
    notebook: str = typer.Option(None, "-n", "--notebook"),
    full: bool = typer.Option(False, "--full", help="Show full matching note content in text mode."),
    snippet_length: int = typer.Option(160, "--snippet-length", min=20, help="Snippet length for text-mode search results."),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON output."),
):
    """Search notes."""
    db_path = Settings.load().db_path
    with managed_db(db_path, read_only=is_linux()) as conn:
        results = search_notes(conn, query, notebook=notebook)
    if as_json:
        typer.echo(to_json([_note_payload(note) for note in results]))
        return
    for note in results:
        _print_note_text(note, full_content=full, snippet_length=snippet_length)
        console.print("")


@app.command()
def sync(
    dry_run: bool = typer.Option(False, "--dry-run"),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON output."),
):
    """Sync notes from Apple Notes into the local cache."""
    if is_linux():
        message = "Sync is not available on Linux."
        if as_json:
            typer.echo(to_json({"ok": False, "error": message, "dry_run": dry_run}))
            raise typer.Exit(code=1)
        console.print(message)
        raise typer.Exit(code=1)

    settings = Settings.load()
    report = SyncEngine(
        settings.db_path,
        syncer=AppleNotesSyncer(timeout_seconds=settings.sync_timeout_seconds),
    ).sync(dry_run=dry_run)
    payload = _build_sync_report(report, dry_run=dry_run)
    if as_json:
        typer.echo(to_json({"ok": True, **payload}))
        return
    console.print(
        f"fetched={payload['notes_fetched']} added={payload['notes_added']} "
        f"updated={payload['notes_updated']} deleted={payload['notes_deleted']}"
    )


@app.command()
def notebooks(as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON output.")):
    """List notebooks."""
    db_path = Settings.load().db_path
    with managed_db(db_path, read_only=is_linux()) as conn:
        nbs = list_notebooks(conn)
    if as_json:
        typer.echo(to_json([_notebook_payload(nb) for nb in nbs]))
        return
    table = Table()
    table.add_column("id")
    table.add_column("name")
    for nb in nbs:
        table.add_row(nb.id, nb.name)
    console.print(table)


@app.command()
def config():
    """Show config."""
    settings = Settings.load()
    for k, v in settings.model_dump().items():
        console.print(f"{k} = {v}")


@app.command()
def doctor(as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON output.")):
    """Check runtime prerequisites for sync and query operations."""
    settings = Settings.load()
    report = _build_doctor_report(settings)

    if as_json:
        typer.echo(to_json(report))
        return

    table = Table(title="NotesMirror Diagnostics")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")

    for check in report["checks"]:
        table.add_row(
            str(check["check"]),
            "OK" if bool(check["ok"]) else "FAIL",
            str(check["detail"]),
        )

    console.print(table)
    failures = report["failures"]
    if failures:
        console.print("\nFailures:")
        for failure in failures:
            console.print(f"- {failure}")


cli = app


if __name__ == "__main__":
    app()
