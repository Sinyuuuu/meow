"""Read-only schema and optional source-count verification without exposing secrets."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
import app.models  # noqa: E402, F401


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Meow House database schema")
    parser.add_argument("--compare-sqlite", type=Path)
    args = parser.parse_args()

    url = make_url(settings.database_url)
    print(f"Database: {url.render_as_string(hide_password=True)}")
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    expected = set(Base.metadata.tables)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        existing = set(inspect(connection).get_table_names())
        missing = sorted(expected - existing)
        print(f"Connection: OK; expected tables={len(expected)}; existing tables={len(existing)}")
        if missing:
            print("Missing tables: " + ", ".join(missing))
            return 2
        target_counts = {
            table.name: int(connection.scalar(select(func.count()).select_from(table)) or 0)
            for table in Base.metadata.sorted_tables
        }

    if args.compare_sqlite:
        source = args.compare_sqlite.expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        with sqlite3.connect(source) as connection:
            source_tables = {
                row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            mismatches = []
            for table_name in sorted(source_tables & expected):
                source_count = connection.execute(
                    f'SELECT COUNT(*) FROM "{table_name}"'
                ).fetchone()[0]
                if source_count != target_counts.get(table_name):
                    mismatches.append(
                        f"{table_name}: source={source_count}, target={target_counts.get(table_name)}"
                    )
        if mismatches:
            print("Count mismatches: " + "; ".join(mismatches))
            return 3
        print("Source/target counts: MATCH for shared tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
