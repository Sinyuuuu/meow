"""Persistent owner care-calendar APIs.

The production table is introduced by an Alembic migration. Until that
migration is explicitly approved and applied, endpoints fail closed with a
clear 503 instead of implicitly creating schema in Supabase.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles, require_user
from app.config import settings
from app.database import get_db
from app.models.healthcare import CareReminder
from app.services.governance_service import audit, ensure_pet_access


router = APIRouter(prefix="/api/healthcare", tags=["healthcare"])
CATEGORIES = {"DEWORMING", "BATH", "VACCINE", "FOLLOW_UP", "CHECKUP", "WEIGHT", "OTHER"}


class ReminderCreate(BaseModel):
    pet_id: int = Field(gt=0)
    category: str
    title: str = Field(min_length=1, max_length=120)
    scheduled_at: datetime
    recurrence: Literal["NONE", "WEEKLY", "MONTHLY"] = "NONE"
    advance_minutes: int | None = Field(default=None, ge=0, le=525600)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in CATEGORIES:
            raise ValueError("unsupported care category")
        return normalized

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("scheduled_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduled_at must include a timezone offset")
        return value.astimezone(timezone.utc)


class ReminderUpdate(BaseModel):
    category: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)
    scheduled_at: datetime | None = None
    recurrence: Literal["NONE", "WEEKLY", "MONTHLY"] | None = None
    advance_minutes: int | None = Field(default=None, ge=0, le=525600)
    note: str | None = Field(default=None, max_length=2000)
    completed: bool | None = None

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if normalized not in CATEGORIES:
            raise ValueError("unsupported care category")
        return normalized

    @field_validator("scheduled_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduled_at must include a timezone offset")
        return value.astimezone(timezone.utc)


def _feature_ready(db: Session) -> None:
    if not inspect(db.get_bind()).has_table(CareReminder.__tablename__):
        raise HTTPException(
            503,
            detail={
                "code": "CARE_REMINDER_MIGRATION_REQUIRED",
                "message": "照護提醒資料表尚未啟用，請先核准並套用 migration。",
            },
        )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat()


def _serialize(row: CareReminder) -> dict:
    return {
        "id": row.id,
        "pet_id": row.pet_id,
        "category": row.category,
        "title": row.title,
        "scheduled_at": _iso(row.scheduled_at),
        "recurrence": row.recurrence,
        "advance_minutes": row.advance_minutes,
        "note": row.note,
        "completed": row.completed,
        "completed_at": _iso(row.completed_at),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


@router.get("/reminders")
def list_reminders(
    start: datetime | None = None,
    end: datetime | None = None,
    member: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    _feature_ready(db)
    ensure_pet_access(db, member, settings.default_pet_id)
    statement = select(CareReminder).where(CareReminder.pet_id == settings.default_pet_id)
    if start is not None:
        statement = statement.where(CareReminder.scheduled_at >= start)
    if end is not None:
        statement = statement.where(CareReminder.scheduled_at < end)
    rows = db.scalars(statement.order_by(CareReminder.scheduled_at, CareReminder.id)).all()
    return [_serialize(row) for row in rows]


@router.post("/reminders", status_code=201)
def create_reminder(
    payload: ReminderCreate,
    member: dict = Depends(require_roles("OWNER")),
    db: Session = Depends(get_db),
):
    _feature_ready(db)
    if payload.pet_id != settings.default_pet_id:
        raise HTTPException(404, "Pet not found")
    ensure_pet_access(db, member, payload.pet_id)
    row = CareReminder(
        pet_id=payload.pet_id,
        owner_id=int(member["user_id"]),
        category=payload.category,
        title=payload.title.strip(),
        scheduled_at=payload.scheduled_at,
        recurrence=payload.recurrence,
        advance_minutes=payload.advance_minutes,
        note=payload.note.strip() if payload.note else None,
    )
    db.add(row)
    db.flush()
    audit(db, int(member["user_id"]), "CARE_REMINDER_CREATED", f"reminder_id={row.id}; pet_id={row.pet_id}")
    db.commit()
    db.refresh(row)
    return _serialize(row)


def _owned_reminder(db: Session, member: dict, reminder_id: int) -> CareReminder:
    row = db.get(CareReminder, reminder_id)
    if row is None:
        raise HTTPException(404, "Care reminder not found")
    ensure_pet_access(db, member, row.pet_id)
    if member["role"] == "OWNER" and row.owner_id != int(member["user_id"]):
        raise HTTPException(403, "You cannot modify another owner's reminder")
    return row


@router.patch("/reminders/{reminder_id}")
def update_reminder(
    reminder_id: int,
    payload: ReminderUpdate,
    member: dict = Depends(require_roles("OWNER")),
    db: Session = Depends(get_db),
):
    _feature_ready(db)
    row = _owned_reminder(db, member, reminder_id)
    values = payload.model_dump(exclude_unset=True)
    for key in ("category", "title", "scheduled_at", "recurrence", "advance_minutes", "note"):
        if key in values:
            value = values[key]
            if isinstance(value, str):
                value = value.strip() or None
            setattr(row, key, value)
    if "completed" in values:
        row.completed = bool(values["completed"])
        row.completed_at = datetime.now(timezone.utc) if row.completed else None
    row.updated_at = datetime.now(timezone.utc)
    audit(db, int(member["user_id"]), "CARE_REMINDER_UPDATED", f"reminder_id={row.id}")
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.delete("/reminders/{reminder_id}", status_code=204)
def delete_reminder(
    reminder_id: int,
    member: dict = Depends(require_roles("OWNER")),
    db: Session = Depends(get_db),
):
    _feature_ready(db)
    row = _owned_reminder(db, member, reminder_id)
    audit(db, int(member["user_id"]), "CARE_REMINDER_DELETED", f"reminder_id={row.id}")
    db.delete(row)
    db.commit()
    return Response(status_code=204)
