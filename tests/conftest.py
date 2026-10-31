"""Force every pytest run onto a fresh isolated SQLite database.

This module is imported before test modules, so the production Supabase URL in
the project's .env can never be used accidentally by the test suite.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4


TEST_ROOT = Path(__file__).resolve().parent / ".tmp"
TEST_ROOT.mkdir(parents=True, exist_ok=True)
TEST_DATABASE = TEST_ROOT / f"app_{uuid4().hex}.db"

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ["APP_SECRET_KEY"] = "pytest-isolated-session-key"

