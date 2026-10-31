"""Authenticated IoT inventory and sensor-reading query APIs."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles, require_user
from app.config import settings
from app.database import get_db
from app.models.boarding import CatHouse
from app.models.iot import IotDevice, SensorReading
from app.services.governance_service import ensure_pet_access


router = APIRouter(prefix="/api/iot", tags=["iot"])


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat()


@router.get("/devices")
def list_devices(
    member: dict = Depends(require_roles("CAREGIVER", "ADMIN")),
    db: Session = Depends(get_db),
):
    if member["role"] == "CAREGIVER":
        ensure_pet_access(db, member, settings.default_pet_id)
    devices = db.scalars(select(IotDevice).order_by(IotDevice.id)).all()
    return [
        {
            "id": device.id,
            "cat_house_id": device.cat_house_id,
            "device_uid": device.device_uid,
            "name": device.name,
            "device_type": device.device_type,
            "status": device.status,
            "firmware_version": device.firmware_version,
            "simulated": device.simulated,
            "last_seen_at": _iso(device.last_seen_at),
        }
        for device in devices
    ]


@router.get("/measurements")
def list_measurements(
    device_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=1000),
    member: dict = Depends(require_roles("CAREGIVER", "ADMIN")),
    db: Session = Depends(get_db),
):
    if member["role"] == "CAREGIVER":
        ensure_pet_access(db, member, settings.default_pet_id)
    statement = select(SensorReading)
    if device_id is not None:
        statement = statement.where(SensorReading.device_id == device_id)
    rows = db.scalars(
        statement.order_by(SensorReading.measured_at.desc(), SensorReading.id.desc()).limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "device_id": row.device_id,
            "pet_id": row.pet_id,
            "sequence_no": row.sequence_no,
            "measured_at": _iso(row.measured_at),
            "received_at": _iso(row.received_at),
            "raw_value": row.raw_value,
            "raw_weight_grams": row.raw_weight_grams,
            "filtered_weight_grams": row.filtered_weight_grams,
            "quality": row.quality,
            "source": row.source,
            "simulated": row.simulated,
        }
        for row in rows
    ]


@router.get("/pet-status")
def pet_device_status(
    member: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Return an owner-safe device summary for the current pet."""
    ensure_pet_access(db, member, settings.default_pet_id)
    devices = db.scalars(
        select(IotDevice)
        .join(CatHouse, IotDevice.cat_house_id == CatHouse.id)
        .where(CatHouse.current_pet_id == settings.default_pet_id)
        .order_by(IotDevice.id)
    ).all()
    now = datetime.now(timezone.utc)
    result = []
    for device in devices:
        latest = db.scalar(
            select(SensorReading)
            .where(SensorReading.device_id == device.id, SensorReading.pet_id == settings.default_pet_id)
            .order_by(SensorReading.measured_at.desc(), SensorReading.id.desc())
            .limit(1)
        )
        seen = device.last_seen_at
        if seen and seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        online = bool(seen and now - seen.astimezone(timezone.utc) <= timedelta(minutes=5))
        result.append({
            "id": device.id,
            "name": device.name,
            "device_type": device.device_type,
            "status": "ONLINE" if online else "OFFLINE",
            "last_seen_at": _iso(seen),
            "simulated": device.simulated,
            "latest_weight_grams": latest.filtered_weight_grams if latest else None,
            "latest_measured_at": _iso(latest.measured_at) if latest else None,
            "latest_quality": latest.quality if latest else None,
            "latest_simulated": latest.simulated if latest else None,
        })
    return result


@router.get("/pet-measurements")
def pet_measurements(
    day: date | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    member: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Return weight samples assigned to the signed-in user's current pet."""
    ensure_pet_access(db, member, settings.default_pet_id)
    statement = select(SensorReading).where(SensorReading.pet_id == settings.default_pet_id)
    if day is not None:
        start = datetime.combine(day, time.min, tzinfo=settings.timezone).astimezone(timezone.utc)
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=settings.timezone).astimezone(timezone.utc)
        statement = statement.where(SensorReading.measured_at >= start, SensorReading.measured_at < end)
    rows = db.scalars(
        statement.order_by(SensorReading.measured_at.desc(), SensorReading.id.desc()).limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "device_id": row.device_id,
            "measured_at": _iso(row.measured_at),
            "filtered_weight_grams": row.filtered_weight_grams,
            "quality": row.quality,
            "simulated": row.simulated,
        }
        for row in rows
    ]
