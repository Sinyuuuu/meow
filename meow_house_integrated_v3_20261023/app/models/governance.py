"""Operational governance models layered onto the runnable AI prototype."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserState(Base):
    """Account lifecycle kept separate to avoid destructive prototype migrations."""

    __tablename__ = "user_states"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PetAccess(Base):
    """Explicit caregiver-to-pet authorization."""

    __tablename__ = "pet_access"
    __table_args__ = (UniqueConstraint("user_id", "pet_id", name="uq_pet_access"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pets.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DeviceHeartbeat(Base):
    """Latest health report for a registered camera device."""

    __tablename__ = "device_heartbeats"

    camera_device_id: Mapped[int] = mapped_column(
        ForeignKey("camera_devices.id"), primary_key=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="LOCAL_MONITOR")
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AuditLog(Base):
    """Append-only record of sensitive administrative and care actions."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SystemSetting(Base):
    """Small validated settings store for non-medical activity rules."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SystemTask(Base):
    """Administrator operations checklist, separate from human cat-care tasks."""

    __tablename__ = "system_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="TODO", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AlertHandling(Base):
    """Human handling history for a rule-based alert."""

    __tablename__ = "alert_handling"

    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
