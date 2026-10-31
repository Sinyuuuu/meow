"""Validate and mark the existing 16-table application schema.

Revision ID: 20261028_0001
Revises: None
"""

from alembic import op
from sqlalchemy import inspect


revision = "20261028_0001"
down_revision = "20261028_0000"
branch_labels = None
depends_on = None

EXPECTED_TABLES = {
    "users",
    "user_states",
    "pets",
    "pet_access",
    "cat_houses",
    "boarding_orders",
    "care_tasks",
    "care_logs",
    "camera_devices",
    "device_heartbeats",
    "activity_records",
    "alerts",
    "alert_handling",
    "audit_logs",
    "system_settings",
    "system_tasks",
}


def upgrade() -> None:
    existing = set(inspect(op.get_bind()).get_table_names())
    missing = EXPECTED_TABLES - existing
    if missing:
        raise RuntimeError(
            "Existing-schema baseline refused because tables are missing: "
            + ", ".join(sorted(missing))
        )


def downgrade() -> None:
    # A baseline must never delete pre-existing application data.
    pass
