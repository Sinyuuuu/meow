"""Authenticated machine-to-machine ingest for future camera edge devices."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.zones import ROI_ZONES
from app.config import settings
from app.database import get_db
from app.models import ActivityRecord, CameraDevice, CatHouse, IotDevice, Pet, SensorReading
from app.services.auth_service import verify_password
from app.services.feeding_service import detect_feeding_candidate
from app.services.governance_service import audit, touch_device


router = APIRouter(prefix="/api/ingest", tags=["device ingest"])
logger = logging.getLogger(__name__)


def require_service_key(x_service_key: str | None = Header(default=None)) -> None:
    """Reject device ingest unless the operator has configured a secret key."""
    if not settings.service_key:
        raise HTTPException(503, "Device ingest is disabled until MEOW_SERVICE_KEY is configured")
    if not x_service_key or not secrets.compare_digest(x_service_key, settings.service_key):
        raise HTTPException(401, "Invalid service key")


class HeartbeatIn(BaseModel):
    camera_device_id: int = Field(gt=0)
    detail: str | None = Field(default=None, max_length=255)


class ActivityIn(BaseModel):
    pet_id: int = Field(gt=0)
    zone: str
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_seconds: int = Field(ge=0, le=86400)

    @field_validator("zone")
    @classmethod
    def valid_zone(cls, value: str) -> str:
        value = value.upper()
        if value not in ROI_ZONES:
            raise ValueError("unknown zone")
        return value


class MeasurementIn(BaseModel):
    """One calibrated HX711 sample; simulated data must remain explicitly marked."""

    model_config = ConfigDict(allow_inf_nan=False)

    device_uid: str = Field(min_length=3, max_length=120)
    sequence_no: int = Field(ge=0, le=9_223_372_036_854_775_807)
    measured_at: datetime
    raw_value: int = Field(ge=-8_388_608, le=8_388_607)
    raw_weight_grams: float = Field(ge=-500, le=20_000)
    filtered_weight_grams: float = Field(ge=-500, le=20_000)
    quality: Literal["GOOD", "UNSTABLE", "OUT_OF_RANGE", "CALIBRATING", "ERROR"]
    firmware_version: str | None = Field(default=None, max_length=80)
    simulated: bool = False

    @field_validator("device_uid")
    @classmethod
    def normalize_device_uid(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("device_uid must not be blank")
        return value

    @field_validator("measured_at")
    @classmethod
    def valid_device_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("measured_at must include a timezone offset")
        value = value.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if value > now + timedelta(minutes=5):
            raise ValueError("measured_at is too far in the future")
        if value < now - timedelta(days=7):
            raise ValueError("measured_at is older than the offline buffer window")
        return value


def _authenticate_iot_device(
    device: IotDevice,
    x_device_key: str | None,
    x_service_key: str | None,
) -> None:
    """Prefer a per-device credential and retain the existing service-key fallback."""
    if device.auth_key_hash:
        if not x_device_key or not verify_password(x_device_key, device.auth_key_hash):
            raise HTTPException(401, "Invalid device credential")
        return
    require_service_key(x_service_key)


def _measurement_dict(reading: SensorReading, *, duplicate: bool) -> dict:
    return {
        "accepted": True,
        "duplicate": duplicate,
        "measurement_id": reading.id,
        "device_id": reading.device_id,
        "sequence_no": reading.sequence_no,
        "simulated": reading.simulated,
    }


@router.post("/heartbeat", dependencies=[Depends(require_service_key)])
def heartbeat(payload: HeartbeatIn, db: Session = Depends(get_db)):
    if db.get(CameraDevice, payload.camera_device_id) is None:
        raise HTTPException(404, "Camera device not found")
    touch_device(db, payload.camera_device_id, "REMOTE_DEVICE", payload.detail)
    db.commit()
    return {"accepted": True, "camera_device_id": payload.camera_device_id}


@router.post("/activity", status_code=201, dependencies=[Depends(require_service_key)])
def ingest_activity(payload: ActivityIn, db: Session = Depends(get_db)):
    if db.get(Pet, payload.pet_id) is None:
        raise HTTPException(404, "Pet not found")
    observed_at = payload.observed_at
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    observed_at = observed_at.astimezone(timezone.utc)
    record = ActivityRecord(
        pet_id=payload.pet_id,
        zone=payload.zone,
        entered_at=observed_at - timedelta(seconds=payload.duration_seconds),
        left_at=observed_at,
        duration_seconds=payload.duration_seconds,
    )
    db.add(record)
    db.flush()
    audit(db, None, "DEVICE_ACTIVITY_INGESTED", f"record_id={record.id}; pet_id={payload.pet_id}; zone={payload.zone}")
    db.commit()
    return {"accepted": True, "activity_record_id": record.id}


@router.post("/measurements", status_code=201)
def ingest_measurement(
    payload: MeasurementIn,
    response: Response,
    x_device_key: str | None = Header(default=None),
    x_service_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Authenticate, deduplicate, persist, and evaluate one weight sample."""
    try:
        device = db.scalar(select(IotDevice).where(IotDevice.device_uid == payload.device_uid))
        if device is None:
            raise HTTPException(404, "IoT device not found")
        if device.status == "DISABLED":
            raise HTTPException(403, "IoT device is disabled")
        _authenticate_iot_device(device, x_device_key, x_service_key)

        existing = db.scalar(
            select(SensorReading).where(
                SensorReading.device_id == device.id,
                SensorReading.sequence_no == payload.sequence_no,
            )
        )
        if existing:
            response.status_code = 200
            return _measurement_dict(existing, duplicate=True)

        house = db.get(CatHouse, device.cat_house_id)
        if house is None:
            raise HTTPException(409, "IoT device is not assigned to a valid cat house")
        reading = SensorReading(
            device_id=device.id,
            pet_id=house.current_pet_id,
            sequence_no=payload.sequence_no,
            measured_at=payload.measured_at,
            raw_value=payload.raw_value,
            raw_weight_grams=payload.raw_weight_grams,
            filtered_weight_grams=payload.filtered_weight_grams,
            quality=payload.quality,
            source="SIMULATOR" if payload.simulated else "HX711",
            simulated=bool(payload.simulated or device.simulated),
        )
        db.add(reading)
        db.flush()
        device.last_seen_at = datetime.now(timezone.utc)
        if payload.firmware_version:
            device.firmware_version = payload.firmware_version
        detect_feeding_candidate(db, reading, cat_house_id=house.id)
        audit(
            db,
            None,
            "SENSOR_MEASUREMENT_INGESTED",
            f"reading_id={reading.id}; device_id={device.id}; simulated={reading.simulated}",
        )
        db.commit()
        db.refresh(reading)
        return _measurement_dict(reading, duplicate=False)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(SensorReading)
            .join(IotDevice, SensorReading.device_id == IotDevice.id)
            .where(
                IotDevice.device_uid == payload.device_uid,
                SensorReading.sequence_no == payload.sequence_no,
            )
        )
        if existing:
            response.status_code = 200
            return _measurement_dict(existing, duplicate=True)
        raise HTTPException(409, "Measurement conflicts with an existing record")
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Sensor measurement database operation failed")
        raise HTTPException(503, "Database temporarily unavailable") from exc
