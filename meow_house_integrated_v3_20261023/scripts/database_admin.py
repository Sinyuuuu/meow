"""Inspect and safely back up the configured SQLite prototype database."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402


IMPORTANT_TABLES = (
    "users",
    "pets",
    "boarding_orders",
    "activity_records",
    "alerts",
    "care_tasks",
    "care_logs",
    "audit_logs",
)


def configured_sqlite_path() -> Path:
    """Return the configured SQLite file and reject unsupported database drivers."""
    url = make_url(settings.database_url)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        raise RuntimeError("This helper currently supports file-based SQLite databases only.")
    return Path(url.database).expanduser().resolve()


def status() -> int:
    """Print the effective database location, integrity, and important row counts."""
    path = configured_sqlite_path()
    print(f"Database: {path}")
    if not path.exists():
        print("Status: NOT CREATED")
        return 1
    with sqlite3.connect(path) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        print(f"Integrity: {integrity}")
        print(f"Size: {path.stat().st_size:,} bytes")
        for table in IMPORTANT_TABLES:
            if table in tables:
                count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                print(f"{table}: {count}")
    return 0 if integrity == "ok" else 2


def backup(destination: Path | None = None) -> int:
    """Create a consistent SQLite online backup, including committed WAL data."""
    source = configured_sqlite_path()
    if not source.exists():
        raise FileNotFoundError(f"Database does not exist: {source}")
    if destination is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = source.parent / "backups" / f"app_{stamp}.db"
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Backup already exists: {destination}")
    with sqlite3.connect(source) as source_connection, sqlite3.connect(destination) as target:
        source_connection.backup(target)
        integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"Backup integrity check failed: {integrity}")
    print(f"Backup created: {destination}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Meow House database status and backup")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.command == "status":
        return status()
    return backup(args.destination)


if __name__ == "__main__":
    raise SystemExit(main())
