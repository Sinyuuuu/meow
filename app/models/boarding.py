"""Boarding, smart-house, camera, and human care models."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CatHouse(Base):
    __tablename__ = "cat_houses"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    camera_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="AVAILABLE")
    current_pet_id: Mapped[int | None] = mapped_column(ForeignKey("pets.id"), nullable=True)


class BoardingOrder(Base):
    __tablename__ = "boarding_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pets.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date, default=date.today)
    end_date: Mapped[date] = mapped_column(Date, default=date.today)
    cat_house_id: Mapped[int | None] = mapped_column(ForeignKey("cat_houses.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)


class CareTask(Base):
    __tablename__ = "care_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pets.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(80))
    scheduled_time: Mapped[str] = mapped_column(String(10))
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class CareLog(Base):
    __tablename__ = "care_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pets.id"), index=True)
    caregiver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class CameraDevice(Base):
    __tablename__ = "camera_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    cat_house_id: Mapped[int] = mapped_column(ForeignKey("cat_houses.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="READY")

