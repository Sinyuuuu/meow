"""Verify Supabase PostgreSQL without exposing credentials or writing data."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, OperationalError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import _database_url, _load_dotenv  # noqa: E402


def _safe_error_kind(exc: BaseException) -> str:
    """Classify an error without returning host, user, password, or URL text."""
    message = str(exc).lower()
    if "password authentication failed" in message or "authentication failed" in message:
        return "authentication failed"
    if "could not translate host" in message or "name or service not known" in message:
        return "host name resolution failed"
    if "timeout" in message or "timed out" in message:
        return "connection timed out"
    if "ssl" in message or "certificate" in message:
        return "TLS/SSL negotiation failed"
    if "connection refused" in message:
        return "connection refused"
    return "PostgreSQL connection or read-only query failed"


def main() -> int:
    _load_dotenv(PROJECT_ROOT / ".env")
    raw = os.getenv("SUPABASE_DATABASE_URL", "").strip()
    if not raw:
        print("Status: FAILED")
        print("Reason: SUPABASE_DATABASE_URL is missing or empty")
        return 2

    normalized = _database_url(raw)
    parsed = make_url(normalized)
    if not parsed.drivername.startswith("postgresql"):
        print("Status: FAILED")
        print("Reason: SUPABASE_DATABASE_URL is not PostgreSQL")
        return 2

    engine = create_engine(
        normalized,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                probe = connection.scalar(text("SELECT 1"))
                table_names = connection.scalars(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                        "ORDER BY table_name"
                    )
                ).all()
                preparer = connection.dialect.identifier_preparer
                counts: list[tuple[str, int]] = []
                for table_name in table_names:
                    qualified = (
                        preparer.quote_schema("public") + "." + preparer.quote(table_name)
                    )
                    count = connection.scalar(text(f"SELECT COUNT(*) FROM {qualified}"))
                    counts.append((table_name, int(count or 0)))
            finally:
                transaction.rollback()
    except (OperationalError, DBAPIError) as exc:
        print("Status: FAILED")
        print("Reason: " + _safe_error_kind(exc))
        return 1
    finally:
        engine.dispose()

    print("Status: OK")
    print(f"SELECT 1: {probe}")
    print(f"Public tables: {len(counts)}")
    for table_name, count in counts:
        print(f"{table_name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
