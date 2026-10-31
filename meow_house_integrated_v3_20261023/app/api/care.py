"""Human care tasks and caregiver notes for the active boarding stay."""

from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles, require_user
from app.config import settings
from app.database import get_db
from app.models.boarding import CareLog, CareTask
from app.services.governance_service import audit, ensure_pet_access


router = APIRouter(prefix="/api/care", tags=["care"])


class TaskUpdate(BaseModel):
    completed: bool


class CareLogCreate(BaseModel):
    type: str = Field(min_length=1, max_length=80)
    note: str = Field(min_length=1, max_length=1000)

    @field_validator("type", "note")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


def _utc_iso(value) -> str:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat()


@router.get("/tasks")
def list_tasks(member: dict = Depends(require_user), db: Session = Depends(get_db)):
    """Return the active pet's care checklist in scheduled order."""
    ensure_pet_access(db, member, settings.default_pet_id)
    tasks = db.scalars(
        select(CareTask)
        .where(CareTask.pet_id == settings.default_pet_id)
        .order_by(CareTask.scheduled_time, CareTask.id)
    ).all()
    return [
        {
            "id": task.id,
            "task_type": task.task_type,
            "scheduled_time": task.scheduled_time,
            "completed": task.completed,
        }
        for task in tasks
    ]


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: int,
    payload: TaskUpdate,
    member: dict = Depends(require_roles("CAREGIVER")),
    db: Session = Depends(get_db),
):
    """Complete or reopen a care task; owners have read-only access."""
    ensure_pet_access(db, member, settings.default_pet_id)
    task = db.get(CareTask, task_id)
    if not task or task.pet_id != settings.default_pet_id:
        raise HTTPException(404, "Care task not found")
    task.completed = payload.completed
    audit(db, int(member["user_id"]), "CARE_TASK_UPDATED", f"task_id={task.id}; completed={payload.completed}")
    db.commit()
    return {"id": task.id, "completed": task.completed}


@router.get("/logs")
def list_logs(
    limit: int = 12,
    member: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Return recent human-written care records."""
    ensure_pet_access(db, member, settings.default_pet_id)
    limit = min(max(limit, 1), 50)
    logs = db.scalars(
        select(CareLog)
        .where(CareLog.pet_id == settings.default_pet_id)
        .order_by(CareLog.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": log.id,
            "type": log.type,
            "note": log.note,
            "caregiver_id": log.caregiver_id,
            "created_at": _utc_iso(log.created_at),
        }
        for log in logs
    ]


@router.post("/logs", status_code=201)
def create_log(
    payload: CareLogCreate,
    member: dict = Depends(require_roles("CAREGIVER")),
    db: Session = Depends(get_db),
):
    """Add a human care note kept separate from AI-derived activity data."""
    ensure_pet_access(db, member, settings.default_pet_id)
    log = CareLog(
        pet_id=settings.default_pet_id,
        caregiver_id=int(member["user_id"]),
        type=payload.type.strip(),
        note=payload.note.strip(),
    )
    db.add(log)
    db.flush()
    audit(db, int(member["user_id"]), "CARE_LOG_CREATED", f"care_log_id={log.id}; type={log.type}")
    db.commit()
    db.refresh(log)
    return {
        "id": log.id,
        "type": log.type,
        "note": log.note,
        "created_at": _utc_iso(log.created_at),
    }
