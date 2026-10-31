"""Create or safely recognize the original 16-table application schema.

Revision ID: 20261028_0000
Revises: None

This bootstrap is intentionally conservative:
- an empty application schema receives the original 16 tables;
- a complete existing 16-table schema is left untouched;
- a partially present schema is rejected for manual review.
"""

from alembic import op
from sqlalchemy import inspect


revision = "20261028_0000"
down_revision = None
branch_labels = None
depends_on = None


LEGACY_COLUMNS = {
    "users": {"id", "name", "email", "password_hash", "role"},
    "user_states": {"user_id", "status", "updated_at"},
    "pets": {
        "id", "owner_id", "name", "photo", "gender", "age", "breed", "weight",
        "personality", "food_notes", "care_notes", "medical_notes",
    },
    "pet_access": {"id", "user_id", "pet_id", "active"},
    "cat_houses": {"id", "room_number", "camera_url", "status", "current_pet_id"},
    "boarding_orders": {"id", "pet_id", "start_date", "end_date", "cat_house_id", "status"},
    "care_tasks": {"id", "pet_id", "task_type", "scheduled_time", "completed"},
    "care_logs": {"id", "pet_id", "caregiver_id", "type", "note", "created_at"},
    "camera_devices": {"id", "cat_house_id", "name", "source", "status"},
    "device_heartbeats": {"camera_device_id", "last_seen_at", "source", "detail"},
    "activity_records": {"id", "pet_id", "zone", "entered_at", "left_at", "duration_seconds"},
    "alerts": {"id", "pet_id", "type", "message", "created_at", "resolved"},
    "alert_handling": {"alert_id", "status", "handled_by", "note", "updated_at"},
    "audit_logs": {"id", "actor_id", "action", "detail", "created_at"},
    "system_settings": {"key", "value", "updated_at"},
    "system_tasks": {"id", "title", "status", "created_at", "done_at"},
}

IOT_TABLES = {"iot_devices", "sensor_calibrations", "sensor_readings", "feeding_events"}


def _legacy_metadata_tables():
    """Return the dependency-sorted, guarded snapshot used by this bootstrap."""
    import app.models  # noqa: F401  # Register models with Base.metadata.
    from app.database import Base

    tables = [table for table in Base.metadata.sorted_tables if table.name in LEGACY_COLUMNS]
    actual_names = {table.name for table in tables}
    if actual_names != set(LEGACY_COLUMNS):
        raise RuntimeError("Legacy model registry does not match the 16-table migration manifest")
    for table in tables:
        actual_columns = {column.name for column in table.columns}
        if actual_columns != LEGACY_COLUMNS[table.name]:
            raise RuntimeError(f"Legacy model columns changed for {table.name}; create a new revision")
    return tables


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    expected = set(LEGACY_COLUMNS)
    present = existing & expected

    if present and present != expected:
        missing = ", ".join(sorted(expected - present))
        raise RuntimeError(
            "Refusing to bootstrap a partial application schema; missing tables: " + missing
        )
    if present == expected:
        column_mismatches = []
        for table_name, expected_columns in LEGACY_COLUMNS.items():
            actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
            if actual_columns != expected_columns:
                column_mismatches.append(table_name)
        if column_mismatches:
            raise RuntimeError(
                "Existing application tables have incompatible columns: "
                + ", ".join(sorted(column_mismatches))
            )
        return
    if existing & IOT_TABLES:
        raise RuntimeError("IoT tables exist without the original 16-table schema; manual review required")

    # Use the frozen table/column manifest above and create only the original
    # tables in foreign-key order. No demo rows are inserted by migrations.
    for table in _legacy_metadata_tables():
        table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    # Never delete an existing or imported application schema automatically.
    pass
