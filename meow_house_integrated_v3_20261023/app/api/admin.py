"""Administrator APIs for accounts, assignments, devices, ROIs, and audit data."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.zones import ROI_ZONES, ZONE_LABELS
from app.api.dependencies import require_roles
from app.config import settings
from app.database import get_db
from app.models import (
    ActivityRecord, Alert, AuditLog, BoardingOrder, CameraDevice, CatHouse,
    DeviceHeartbeat, Pet, PetAccess, SystemSetting, SystemTask, User, UserState,
)
from app.services.auth_service import hash_password
from app.services.governance_service import audit


router = APIRouter(prefix="/api/admin", tags=["admin"])
VALID_ZONES = set(ROI_ZONES)


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["OWNER", "CAREGIVER", "ADMIN"]

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("email")
    @classmethod
    def basic_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("invalid email")
        return value


class UserStatusUpdate(BaseModel):
    status: Literal["ACTIVE", "DISABLED"]


class AssignmentCreate(BaseModel):
    caregiver_id: int = Field(gt=0)
    pet_id: int = Field(gt=0)
    active: bool = True


class RoiUpdate(BaseModel):
    points: list[tuple[float, float]] = Field(min_length=3, max_length=20)

    @field_validator("points")
    @classmethod
    def normalized_points(cls, points: list[tuple[float, float]]):
        if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in points):
            raise ValueError("ROI coordinates must be normalized from 0 to 1")
        return points


class SettingUpdate(BaseModel):
    value: float = Field(gt=0, le=10080)


class SystemTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)


class SystemTaskUpdate(BaseModel):
    status: Literal["TODO", "DONE"]


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat()


@router.get("/overview")
def overview(_member: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    """Return a compact system inventory without exposing credentials."""
    count = lambda model: db.scalar(select(func.count()).select_from(model)) or 0
    active_alerts = db.scalar(select(func.count()).select_from(Alert).where(Alert.resolved.is_(False))) or 0
    occupied_houses = db.scalar(select(func.count()).select_from(CatHouse).where(CatHouse.status == "OCCUPIED")) or 0
    active_boarding = db.scalar(select(func.count()).select_from(BoardingOrder).where(BoardingOrder.status == "CHECKED_IN")) or 0
    return {
        "users": count(User), "pets": count(Pet), "houses": count(CatHouse),
        "occupied_houses": occupied_houses, "active_boarding": active_boarding,
        "activity_records": count(ActivityRecord), "active_alerts": active_alerts,
        "cameras": _device_rows(db),
    }


@router.get("/users")
def list_users(_member: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.role, User.id)).all()
    result = []
    for user in users:
        state = db.get(UserState, user.id)
        result.append({"id": user.id, "name": user.name, "email": user.email, "role": user.role, "status": state.status if state else "ACTIVE"})
    return result


@router.post("/users", status_code=201)
def create_user(payload: UserCreate, member: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    user = User(name=payload.name, email=str(payload.email).strip().lower(), password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    try:
        db.flush()
        db.add(UserState(user_id=user.id, status="ACTIVE"))
        audit(db, int(member["user_id"]), "USER_CREATED", f"user_id={user.id}; role={user.role}")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Email already exists") from exc
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role, "status": "ACTIVE"}


@router.patch("/users/{user_id}/status")
def update_user_status(user_id: int, payload: UserStatusUpdate, member: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.id == int(member["user_id"]) and payload.status == "DISABLED":
        raise HTTPException(400, "You cannot disable your own account")
    if user.role == "ADMIN" and payload.status == "DISABLED":
        active_admins = db.scalar(
            select(func.count()).select_from(User).outerjoin(UserState, UserState.user_id == User.id)
            .where(User.role == "ADMIN", (UserState.status == "ACTIVE") | (UserState.status.is_(None)))
        ) or 0
        if active_admins <= 1:
            raise HTTPException(400, "At least one active administrator is required")
    state = db.get(UserState, user.id) or UserState(user_id=user.id)
    db.add(state)
    state.status = payload.status
    state.updated_at = datetime.now(timezone.utc)
    audit(db, int(member["user_id"]), "USER_STATUS_CHANGED", f"user_id={user.id}; status={payload.status}")
    db.commit()
    return {"id": user.id, "status": state.status}


@router.get("/assignments")
def list_assignments(_member: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    rows = db.execute(
        select(PetAccess, User, Pet).join(User, PetAccess.user_id == User.id).join(Pet, PetAccess.pet_id == Pet.id).order_by(PetAccess.id)
    ).all()
    return [{"id": item.id, "caregiver_id": user.id, "caregiver_name": user.name, "pet_id": pet.id, "pet_name": pet.name, "active": item.active} for item, user, pet in rows]


@router.post("/assignments")
def save_assignment(payload: AssignmentCreate, member: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    caregiver = db.get(User, payload.caregiver_id)
    pet = db.get(Pet, payload.pet_id)
    if caregiver is None or caregiver.role != "CAREGIVER":
        raise HTTPException(400, "A caregiver account is required")
    if pet is None:
        raise HTTPException(404, "Pet not found")
    access = db.scalar(select(PetAccess).where(PetAccess.user_id == caregiver.id, PetAccess.pet_id == pet.id))
    if access is None:
        access = PetAccess(user_id=caregiver.id, pet_id=pet.id)
        db.add(access)
    access.active = payload.active
    audit(db, int(member["user_id"]), "PET_ACCESS_CHANGED", f"caregiver_id={caregiver.id}; pet_id={pet.id}; active={payload.active}")
    db.commit()
    return {"caregiver_id": caregiver.id, "pet_id": pet.id, "active": access.active}


@router.get("/devices")
def list_devices(_member: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    return _device_rows(db)


def _device_rows(db: Session) -> list[dict]:
    rows = db.execute(
        select(CameraDevice, DeviceHeartbeat).outerjoin(DeviceHeartbeat, DeviceHeartbeat.camera_device_id == CameraDevice.id).order_by(CameraDevice.id)
    ).all()
    now = datetime.now(timezone.utc)
    result = []
    for camera, heartbeat in rows:
        seen = heartbeat.last_seen_at if heartbeat else None
        if seen and seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        online = bool(seen and now - seen <= timedelta(seconds=30))
        result.append({"id": camera.id, "name": camera.name, "source": camera.source, "status": "ONLINE" if online else camera.status, "online": online, "last_seen_at": _iso(seen), "detail": heartbeat.detail if heartbeat else None})
    return result


@router.get("/rois")
def list_rois(_member: dict = Depends(require_roles("ADMIN"))):
    return json.loads(settings.roi_config_path.read_text(encoding="utf-8"))


@router.put("/rois/{zone}")
def update_roi(zone: str, payload: RoiUpdate, member: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    zone = zone.upper()
    if zone not in VALID_ZONES:
        raise HTTPException(404, "Unknown zone")
    rois = json.loads(settings.roi_config_path.read_text(encoding="utf-8"))
    rois[zone] = [[x, y] for x, y in payload.points]
    temp = settings.roi_config_path.with_suffix(".tmp")
    temp.write_text(json.dumps(rois, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, settings.roi_config_path)
    audit(db, int(member["user_id"]), "ROI_UPDATED", f"zone={zone}; points={len(payload.points)}")
    db.commit()
    return {"zone": zone, "label": ZONE_LABELS[zone], "points": rois[zone]}


@router.get("/settings")
def list_settings(_member: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    return [{"key": row.key, "value": row.value, "updated_at": _iso(row.updated_at)} for row in db.scalars(select(SystemSetting).order_by(SystemSetting.key)).all()]


@router.patch("/settings/{key}")
def update_setting(key: Literal["water_zone_hours", "long_stay_minutes"], payload: SettingUpdate, member: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    setting = db.get(SystemSetting, key)
    if setting is None:
        setting = SystemSetting(key=key, value=str(payload.value))
        db.add(setting)
    else:
        setting.value = str(payload.value)
        setting.updated_at = datetime.now(timezone.utc)
    audit(db, int(member["user_id"]), "SETTING_UPDATED", f"key={key}; value={payload.value}")
    db.commit()
    return {"key": setting.key, "value": setting.value}


@router.get("/tasks")
def list_system_tasks(_member: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    return [_task_dict(row) for row in db.scalars(select(SystemTask).order_by(SystemTask.status, SystemTask.id.desc())).all()]


@router.post("/tasks", status_code=201)
def create_system_task(payload: SystemTaskCreate, member: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    task = SystemTask(title=payload.title.strip())
    db.add(task)
    db.flush()
    audit(db, int(member["user_id"]), "SYSTEM_TASK_CREATED", f"task_id={task.id}")
    db.commit()
    return _task_dict(task)


@router.patch("/tasks/{task_id}")
def update_system_task(task_id: int, payload: SystemTaskUpdate, member: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    task = db.get(SystemTask, task_id)
    if task is None:
        raise HTTPException(404, "System task not found")
    task.status = payload.status
    task.done_at = datetime.now(timezone.utc) if payload.status == "DONE" else None
    audit(db, int(member["user_id"]), "SYSTEM_TASK_UPDATED", f"task_id={task.id}; status={task.status}")
    db.commit()
    return _task_dict(task)


def _task_dict(task: SystemTask) -> dict:
    return {"id": task.id, "title": task.title, "status": task.status, "created_at": _iso(task.created_at), "done_at": _iso(task.done_at)}


@router.get("/audit")
def list_audit(limit: int = 50, _member: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    limit = min(max(limit, 1), 200)
    rows = db.execute(select(AuditLog, User).outerjoin(User, AuditLog.actor_id == User.id).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)).all()
    return [{"id": item.id, "actor_id": item.actor_id, "actor_name": user.name if user else "System", "action": item.action, "detail": item.detail, "created_at": _iso(item.created_at)} for item, user in rows]
