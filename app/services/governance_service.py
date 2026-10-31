"""Shared authorization, auditing, and device health helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.governance import AuditLog, DeviceHeartbeat, PetAccess, SystemSetting, UserState
from app.models.pet import Pet


def audit(db: Session, actor_id: int | None, action: str, detail: str = "") -> None:
    """Append an audit entry to the caller's current transaction."""
    db.add(AuditLog(actor_id=actor_id, action=action, detail=detail))


def is_user_active(db: Session, user_id: int) -> bool:
    state = db.get(UserState, user_id)
    return state is None or state.status == "ACTIVE"


def ensure_pet_access(db: Session, member: dict, pet_id: int) -> Pet:
    """Enforce owner ownership, caregiver assignment, or administrator access."""
    pet = db.get(Pet, pet_id)
    if not pet:
        raise HTTPException(404, "Pet not found")
    role = member.get("role")
    user_id = int(member["user_id"])
    if role == "ADMIN":
        return pet
    if role == "OWNER" and pet.owner_id == user_id:
        return pet
    if role == "CAREGIVER":
        allowed = db.scalar(
            select(PetAccess.id).where(
                PetAccess.user_id == user_id,
                PetAccess.pet_id == pet_id,
                PetAccess.active.is_(True),
            )
        )
        if allowed:
            return pet
    raise HTTPException(403, "You do not have access to this pet")


def touch_device(
    db: Session,
    camera_device_id: int,
    source: str = "LOCAL_MONITOR",
    detail: str | None = None,
) -> None:
    heartbeat = db.get(DeviceHeartbeat, camera_device_id)
    if heartbeat is None:
        heartbeat = DeviceHeartbeat(camera_device_id=camera_device_id)
        db.add(heartbeat)
    heartbeat.last_seen_at = datetime.now(timezone.utc)
    heartbeat.source = source
    heartbeat.detail = detail


def get_setting_float(db: Session, key: str, fallback: float) -> float:
    """Read a validated numeric operational setting with a safe fallback."""
    setting = db.get(SystemSetting, key)
    try:
        return float(setting.value) if setting else fallback
    except (TypeError, ValueError):
        return fallback
