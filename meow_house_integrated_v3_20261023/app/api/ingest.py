"""Authenticated machine-to-machine ingest for future camera edge devices."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.ai.zones import ROI_ZONES
from app.config import settings
from app.database import get_db
from app.models import ActivityRecord, CameraDevice, Pet
from app.services.governance_service import audit, touch_device


router = APIRouter(prefix="/api/ingest", tags=["device ingest"])


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
