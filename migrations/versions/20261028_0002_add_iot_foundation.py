"""Add authenticated IoT, calibration, measurement, and feeding-event tables.

Revision ID: 20261028_0002
Revises: 20261028_0001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261028_0002"
down_revision = "20261028_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(inspect(op.get_bind()).get_table_names())
    if "iot_devices" not in existing:
        op.create_table(
            "iot_devices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("cat_house_id", sa.Integer(), sa.ForeignKey("cat_houses.id"), nullable=False),
            sa.Column("device_uid", sa.String(120), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("device_type", sa.String(40), nullable=False),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("firmware_version", sa.String(80), nullable=True),
            sa.Column("auth_key_hash", sa.String(255), nullable=True),
            sa.Column("simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("device_uid", name="uq_iot_devices_device_uid"),
        )
        op.create_index("ix_iot_devices_cat_house_id", "iot_devices", ["cat_house_id"])
        op.create_index("ix_iot_devices_device_uid", "iot_devices", ["device_uid"], unique=True)
        op.create_index("ix_iot_devices_device_type", "iot_devices", ["device_type"])
        op.create_index("ix_iot_devices_status", "iot_devices", ["status"])
        op.create_index("ix_iot_devices_simulated", "iot_devices", ["simulated"])
    if "sensor_calibrations" not in existing:
        op.create_table(
            "sensor_calibrations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("device_id", sa.Integer(), sa.ForeignKey("iot_devices.id"), nullable=False),
            sa.Column("scale_factor", sa.Float(), nullable=False),
            sa.Column("offset", sa.Float(), nullable=False),
            sa.Column("reference_weight_grams", sa.Float(), nullable=True),
            sa.Column("calibrated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("calibrated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
        )
        op.create_index("ix_sensor_calibrations_device_id", "sensor_calibrations", ["device_id"])
    if "sensor_readings" not in existing:
        op.create_table(
            "sensor_readings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("device_id", sa.Integer(), sa.ForeignKey("iot_devices.id"), nullable=False),
            sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id"), nullable=True),
            sa.Column("sequence_no", sa.BigInteger(), nullable=False),
            sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("raw_value", sa.BigInteger(), nullable=False),
            sa.Column("raw_weight_grams", sa.Float(), nullable=False),
            sa.Column("filtered_weight_grams", sa.Float(), nullable=False),
            sa.Column("quality", sa.String(30), nullable=False),
            sa.Column("source", sa.String(30), nullable=False),
            sa.Column("simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("device_id", "sequence_no", name="uq_sensor_device_sequence"),
        )
        op.create_index("ix_sensor_readings_device_id", "sensor_readings", ["device_id"])
        op.create_index("ix_sensor_readings_pet_id", "sensor_readings", ["pet_id"])
        op.create_index("ix_sensor_readings_measured_at", "sensor_readings", ["measured_at"])
        op.create_index("ix_sensor_readings_quality", "sensor_readings", ["quality"])
        op.create_index("ix_sensor_readings_simulated", "sensor_readings", ["simulated"])
        op.create_index("ix_sensor_device_measured", "sensor_readings", ["device_id", "measured_at"])
    if "feeding_events" not in existing:
        op.create_table(
            "feeding_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("device_id", sa.Integer(), sa.ForeignKey("iot_devices.id"), nullable=False),
            sa.Column("cat_house_id", sa.Integer(), sa.ForeignKey("cat_houses.id"), nullable=False),
            sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id"), nullable=True),
            sa.Column("start_reading_id", sa.Integer(), sa.ForeignKey("sensor_readings.id"), nullable=False),
            sa.Column("end_reading_id", sa.Integer(), sa.ForeignKey("sensor_readings.id"), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("weight_before_grams", sa.Float(), nullable=False),
            sa.Column("weight_after_grams", sa.Float(), nullable=False),
            sa.Column("estimated_consumed_grams", sa.Float(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("source", sa.String(40), nullable=False),
            sa.Column("simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("device_id", "start_reading_id", name="uq_feeding_device_start"),
        )
        op.create_index("ix_feeding_events_device_id", "feeding_events", ["device_id"])
        op.create_index("ix_feeding_events_cat_house_id", "feeding_events", ["cat_house_id"])
        op.create_index("ix_feeding_events_pet_id", "feeding_events", ["pet_id"])
        op.create_index("ix_feeding_events_started_at", "feeding_events", ["started_at"])
        op.create_index("ix_feeding_events_status", "feeding_events", ["status"])
        op.create_index("ix_feeding_events_simulated", "feeding_events", ["simulated"])
        op.create_index("ix_feeding_pet_started", "feeding_events", ["pet_id", "started_at"])


def downgrade() -> None:
    existing = set(inspect(op.get_bind()).get_table_names())
    for table in ("feeding_events", "sensor_readings", "sensor_calibrations", "iot_devices"):
        if table in existing:
            op.drop_table(table)
