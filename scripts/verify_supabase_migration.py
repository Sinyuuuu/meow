"""Read-only, credential-safe verification of SQLite to Supabase migration."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import DateTime, Float, Integer, UniqueConstraint, create_engine, inspect, select, text
from sqlalchemy.exc import DBAPIError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.models  # noqa: E402, F401
from app.database import Base  # noqa: E402
from scripts.migrate_sqlite_to_supabase import supabase_url  # noqa: E402


EXPECTED_HEAD = "20261028_0002"


def normalized_value(value):
    """Make SQLite and PostgreSQL values comparable without printing row data."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return round(value, 9)
    if isinstance(value, memoryview):
        return bytes(value)
    return value


def table_rows(connection, table) -> list[tuple]:
    order = list(table.primary_key.columns)
    statement = select(table)
    if order:
        statement = statement.order_by(*order)
    return [
        tuple(normalized_value(row[column.name]) for column in table.columns)
        for row in connection.execute(statement).mappings()
    ]


def quoted(preparer, name: str) -> str:
    return preparer.quote(name)


def verify(source_path: Path) -> list[str]:
    failures: list[str] = []
    source_engine = create_engine(
        f"sqlite:///{source_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    target_engine = create_engine(
        supabase_url(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 15},
    )

    try:
        source_tables = set(inspect(source_engine).get_table_names())
        target_tables = set(inspect(target_engine).get_table_names())
        expected = set(Base.metadata.tables)
        missing = expected - target_tables
        unexpected = target_tables - expected - {"alembic_version"}
        if missing:
            failures.append("missing tables: " + ", ".join(sorted(missing)))
        if unexpected:
            failures.append("unexpected tables: " + ", ".join(sorted(unexpected)))

        with source_engine.connect() as source, target_engine.connect() as target:
            transaction = target.begin()
            try:
                target.execute(text("SET TRANSACTION READ ONLY"))
                revision = target.scalar(text("SELECT version_num FROM alembic_version"))
                if revision != EXPECTED_HEAD:
                    failures.append("Alembic revision mismatch")

                preparer = target.dialect.identifier_preparer
                for table in Base.metadata.sorted_tables:
                    if table.name not in source_tables or table.name not in target_tables:
                        continue
                    source_rows = table_rows(source, table)
                    target_rows = table_rows(target, table)
                    if source_rows != target_rows:
                        failures.append(f"row content mismatch: {table.name}")
                    print(f"{table.name}: {len(target_rows)}; rows_match={source_rows == target_rows}")

                    # Validate every declared single-column foreign key has no orphan.
                    for column in table.columns:
                        for foreign_key in column.foreign_keys:
                            parent = foreign_key.column
                            child_table = quoted(preparer, table.name)
                            child_column = quoted(preparer, column.name)
                            parent_table = quoted(preparer, parent.table.name)
                            parent_column = quoted(preparer, parent.name)
                            orphan_count = target.scalar(
                                text(
                                    f"SELECT COUNT(*) FROM {child_table} c "
                                    f"LEFT JOIN {parent_table} p ON c.{child_column}=p.{parent_column} "
                                    f"WHERE c.{child_column} IS NOT NULL AND p.{parent_column} IS NULL"
                                )
                            )
                            if orphan_count:
                                failures.append(
                                    f"foreign-key orphan: {table.name}.{column.name}={orphan_count}"
                                )

                    # Check declared unique constraints and unique indexes for duplicates.
                    unique_sets = [
                        [column.name for column in constraint.columns]
                        for constraint in table.constraints
                        if isinstance(constraint, UniqueConstraint)
                    ]
                    unique_sets.extend(
                        [column.name for column in index.columns]
                        for index in table.indexes
                        if index.unique
                    )
                    for columns in unique_sets:
                        group_columns = ", ".join(quoted(preparer, name) for name in columns)
                        table_name = quoted(preparer, table.name)
                        duplicate_groups = target.scalar(
                            text(
                                "SELECT COUNT(*) FROM ("
                                f"SELECT {group_columns} FROM {table_name} "
                                f"GROUP BY {group_columns} HAVING COUNT(*) > 1"
                                ") duplicate_values"
                            )
                        )
                        if duplicate_groups:
                            failures.append(
                                f"unique duplicate: {table.name}({','.join(columns)})"
                            )

                    # Read sequence state without advancing it.
                    for column in table.primary_key.columns:
                        if not isinstance(column.type, Integer):
                            continue
                        sequence_name = target.scalar(
                            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                            {
                                "table_name": f"public.{table.name}",
                                "column_name": column.name,
                            },
                        )
                        if not sequence_name:
                            continue
                        parts = [part.strip('"') for part in sequence_name.split(".")]
                        qualified_sequence = ".".join(quoted(preparer, part) for part in parts)
                        last_value = target.scalar(
                            text(f"SELECT last_value FROM {qualified_sequence}")
                        )
                        maximum = target.scalar(
                            text(
                                f"SELECT MAX({quoted(preparer, column.name)}) "
                                f"FROM {quoted(preparer, table.name)}"
                            )
                        )
                        if maximum is not None and int(last_value) < int(maximum):
                            failures.append(f"sequence behind max id: {table.name}")
            finally:
                transaction.rollback()
    finally:
        source_engine.dispose()
        target_engine.dispose()
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Meow House Supabase migration")
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    if not source.is_file():
        print("Status: FAILED")
        print("Reason: SQLite source does not exist")
        return 2
    try:
        failures = verify(source)
    except DBAPIError:
        print("Status: FAILED")
        print("Reason: database connection or read-only verification failed")
        return 1
    if failures:
        print("Status: FAILED")
        for failure in failures:
            print("- " + failure)
        return 3
    print("Status: OK")
    print("Schema, rows, timestamps, keys, constraints, and sequences verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
