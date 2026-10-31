"""Safely copy the current SQLite database into a migrated Supabase database.

The script never creates, drops, or truncates target tables. Alembic must create
the schema first. It aborts when the schema is incomplete or target application
tables contain data, so an accidental second run cannot duplicate records.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Boolean, DateTime, Integer, create_engine, func, inspect, select, text
from sqlalchemy.engine import URL, Engine, make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import _load_dotenv  # noqa: E402
from app.database import Base  # noqa: E402
import app.models  # noqa: E402, F401  # Registers every model with Base.metadata.


_load_dotenv(PROJECT_ROOT / ".env")


def sqlite_source_path(cli_value: Path | None) -> Path:
    """Resolve the source database without depending on the active DATABASE_URL."""
    raw = cli_value or Path(
        os.getenv(
            "SQLITE_MIGRATION_SOURCE",
            "C:/Users/sinyu/Documents/Codex/MeowHouseData/app.db",
        )
    )
    path = raw.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"找不到 SQLite 來源資料庫：{path}")
    return path


def supabase_url() -> URL:
    """Load and normalize the secret Supabase PostgreSQL connection URL."""
    raw = os.getenv("SUPABASE_DATABASE_URL", "").strip()
    if not raw:
        raise RuntimeError(".env 尚未設定 SUPABASE_DATABASE_URL。")
    if raw.startswith("postgres://"):
        raw = "postgresql+psycopg://" + raw.removeprefix("postgres://")
    elif raw.startswith("postgresql://"):
        raw = "postgresql+psycopg://" + raw.removeprefix("postgresql://")
    url = make_url(raw)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("SUPABASE_DATABASE_URL 必須是 PostgreSQL 連線字串。")
    if url.database != "postgres":
        raise RuntimeError("為避免搬到錯誤資料庫，Supabase database 名稱必須是 postgres。")
    if url.query.get("sslmode") is None:
        url = url.update_query_dict({"sslmode": "require"})
    return url


def normalized_rows(engine: Engine, table) -> list[dict[str, object]]:
    """Read rows and normalize SQLite booleans and naive timestamps for PostgreSQL."""
    with engine.connect() as connection:
        source_rows = connection.execute(select(table)).mappings().all()
    output: list[dict[str, object]] = []
    for source_row in source_rows:
        row = dict(source_row)
        for column in table.columns:
            value = row.get(column.name)
            if value is None:
                continue
            if isinstance(column.type, Boolean):
                row[column.name] = bool(value)
            elif isinstance(column.type, DateTime) and isinstance(value, datetime):
                if value.tzinfo is None:
                    row[column.name] = value.replace(tzinfo=UTC)
        output.append(row)
    return output


def table_counts(engine: Engine, table_names: set[str] | None = None) -> dict[str, int]:
    """Return row counts for application tables that exist in this database."""
    existing = table_names or set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        return {
            table.name: int(connection.scalar(select(func.count()).select_from(table)) or 0)
            for table in Base.metadata.sorted_tables
            if table.name in existing
        }


def reset_postgres_sequences(connection) -> None:
    """Advance generated integer primary-key sequences past imported IDs."""
    preparer = connection.dialect.identifier_preparer
    for table in Base.metadata.sorted_tables:
        integer_keys = [
            column
            for column in table.primary_key.columns
            if isinstance(column.type, Integer) and column.autoincrement in (True, "auto")
        ]
        for column in integer_keys:
            sequence_name = connection.scalar(
                text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                {"table_name": table.name, "column_name": column.name},
            )
            if not sequence_name:
                continue
            quoted_table = preparer.quote(table.name)
            quoted_column = preparer.quote(column.name)
            maximum = connection.scalar(
                text(f"SELECT MAX({quoted_column}) FROM {quoted_table}")
            )
            if maximum is None:
                connection.execute(
                    text("SELECT setval(CAST(:sequence_name AS regclass), 1, false)"),
                    {"sequence_name": sequence_name},
                )
            else:
                connection.execute(
                    text("SELECT setval(CAST(:sequence_name AS regclass), :value, true)"),
                    {"sequence_name": sequence_name, "value": int(maximum)},
                )


def migrate(source_path: Path, target_url: URL) -> None:
    """Create missing target tables and atomically copy every application row."""
    source_engine = create_engine(
        f"sqlite:///{source_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    target_engine = create_engine(
        target_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 15},
    )

    print(f"SQLite 來源：{source_path}")
    print("Supabase 目標：PostgreSQL（連線資訊已隱藏）")

    # Validate connectivity before any application rows are attempted.
    with target_engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    target_tables = set(inspect(target_engine).get_table_names())
    expected_tables = set(Base.metadata.tables)
    missing_tables = expected_tables - target_tables
    if missing_tables:
        raise RuntimeError(
            "Supabase schema 尚未完成 Alembic migration；缺少："
            + ", ".join(sorted(missing_tables))
        )
    populated = {name: count for name, count in table_counts(target_engine).items() if count}
    if populated:
        details = ", ".join(f"{name}={count}" for name, count in populated.items())
        raise RuntimeError(
            "Supabase 目標已有資料，為避免重複或覆蓋，本次搬移已停止：" + details
        )

    source_tables = set(inspect(source_engine).get_table_names())
    source_counts = table_counts(source_engine, source_tables)
    with target_engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in source_tables:
                print(f"  {table.name}: source table absent; created empty")
                continue
            rows = normalized_rows(source_engine, table)
            if rows:
                connection.execute(table.insert(), rows)
            print(f"  {table.name}: {len(rows)}")
        reset_postgres_sequences(connection)

    target_counts = table_counts(target_engine)
    mismatches = {
        name: (count, target_counts.get(name, -1))
        for name, count in source_counts.items()
        if target_counts.get(name) != count
    }
    if mismatches:
        raise RuntimeError(f"搬移後筆數驗證失敗：{mismatches}")
    print("搬移完成：所有資料表筆數一致。")
    print("下一步：將 .env 的 DATABASE_URL 改成 SUPABASE_DATABASE_URL 的相同內容。")


def main() -> int:
    parser = argparse.ArgumentParser(description="Move Meow House SQLite data to Supabase")
    parser.add_argument("--source", type=Path, help="SQLite app.db path")
    args = parser.parse_args()
    migrate(sqlite_source_path(args.source), supabase_url())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        message = str(exc).lower()
        if "authentication" in message or "password" in message:
            reason = "資料庫認證失敗"
        elif "timeout" in message or "timed out" in message:
            reason = "資料庫連線逾時"
        elif "could not translate host" in message or "name or service" in message:
            reason = "資料庫主機名稱解析失敗"
        elif isinstance(exc, RuntimeError):
            # RuntimeError messages in this script contain only table names and
            # counts generated by our own validation code.
            reason = str(exc)
        else:
            reason = "資料搬移或驗證失敗；詳細例外已隱藏"
        print(f"[搬移失敗] {reason}", file=sys.stderr)
        raise SystemExit(1) from exc
