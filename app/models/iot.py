"""IoT devices, calibrated weight readings, and derived feeding events."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IotDevice(Base):
    """An ESP32 or other authenticated sensor assigned to a smart cat house."""

    __tablename__ = "iot_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    cat_house_id: Mapped[int] = mapped_column(ForeignKey("cat_houses.id"), index=True)
    device_uid: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    device_type: Mapped[str] = mapped_column(String(40), default="WEIGHT_SCALE", index=True)
    status: Mapped[str] = mapped_column(String(30), default="READY", index=True)
    firmware_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    auth_key_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SensorCalibration(Base):
    """Versioned HX711 calibration parameters and their human provenance."""

    __tablename__ = "sensor_calibrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("iot_devices.id"), index=True)
    scale_factor: Mapped[float] = mapped_column(Float)
    offset: Mapped[float] = mapped_column(Float)
    reference_weight_grams: Mapped[float | None] = mapped_column(Float, nullable=True)
    calibrated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    calibrated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SensorReading(Base):
    """Append-only raw and filtered weight sample received from one device."""

    __tablename__ = "sensor_readings"
    __table_args__ = (
        UniqueConstraint("device_id", "sequence_no", name="uq_sensor_device_sequence"),
        Index("ix_sensor_device_measured", "device_id", "measured_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("iot_devices.id"), index=True)
    pet_id: Mapped[int | None] = mapped_column(ForeignKey("pets.id"), nullable=True, index=True)
    sequence_no: Mapped[int] = mapped_column(BigInteger)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    raw_value: Mapped[int] = mapped_column(BigInteger)
    raw_weight_grams: Mapped[float] = mapped_column(Float)
    filtered_weight_grams: Mapped[float] = mapped_column(Float)
    quality: Mapped[str] = mapped_column(String(30), index=True)
    source: Mapped[str] = mapped_column(String(30), default="HX711")
    simulated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class FeedingEvent(Base):
    """Explainable candidate feeding event derived from stable weight changes."""

    __tablename__ = "feeding_events"
    __table_args__ = (
        UniqueConstraint("device_id", "start_reading_id", name="uq_feeding_device_start"),
        Index("ix_feeding_pet_started", "pet_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("iot_devices.id"), index=True)
    cat_house_id: Mapped[int] = mapped_column(ForeignKey("cat_houses.id"), index=True)
    pet_id: Mapped[int | None] = mapped_column(ForeignKey("pets.id"), nullable=True, index=True)
    start_reading_id: Mapped[int] = mapped_column(ForeignKey("sensor_readings.id"))
    end_reading_id: Mapped[int] = mapped_column(ForeignKey("sensor_readings.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    weight_before_grams: Mapped[float] = mapped_column(Float)
    weight_after_grams: Mapped[float] = mapped_column(Float)
    estimated_consumed_grams: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="CANDIDATE", index=True)
    source: Mapped[str] = mapped_column(String(40), default="WEIGHT_RULE")
    simulated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
