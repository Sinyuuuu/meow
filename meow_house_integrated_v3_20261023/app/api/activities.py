"""Activity records and daily analytics API."""

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai.zones import ROI_ZONES, ZONE_LABELS
from app.api.dependencies import require_user
from app.config import settings
from app.database import get_db
from app.models.activity import ActivityRecord
from app.services.activity_service import today_summary
from app.services.governance_service import ensure_pet_access


router = APIRouter(prefix="/api/activities", tags=["activities"])


@router.get("/summary")
def summary(member: dict = Depends(require_user), db: Session = Depends(get_db)):
    ensure_pet_access(db, member, settings.default_pet_id)
    return {"pet_id": settings.default_pet_id, "zones": today_summary(db, settings.default_pet_id)}


@router.get("/recent")
def recent(
    limit: int = Query(8, ge=1, le=50),
    member: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    ensure_pet_access(db, member, settings.default_pet_id)
    records = db.scalars(
        select(ActivityRecord)
        .where(
            ActivityRecord.pet_id == settings.default_pet_id,
            ActivityRecord.zone.in_(ROI_ZONES),
        )
        .order_by(ActivityRecord.entered_at.desc())
        .limit(limit)
    ).all()
    return [serialize_activity(record) for record in records]


@router.get("")
def list_by_date(
    day: date | None = None,
    member: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    ensure_pet_access(db, member, settings.default_pet_id)
    selected = day or datetime.now(settings.timezone).date()
    start = datetime.combine(selected, time.min, tzinfo=settings.timezone).astimezone(timezone.utc)
    end = datetime.combine(
        selected + timedelta(days=1),
        time.min,
        tzinfo=settings.timezone,
    ).astimezone(timezone.utc)
    records = db.scalars(
        select(ActivityRecord)
        .where(
            ActivityRecord.pet_id == settings.default_pet_id,
            ActivityRecord.zone.in_(ROI_ZONES),
            ActivityRecord.entered_at < end,
            or_(ActivityRecord.left_at.is_(None), ActivityRecord.left_at > start),
        )
        .order_by(ActivityRecord.entered_at.desc())
    ).all()
    return [serialize_activity(record) for record in records]


def serialize_activity(record: ActivityRecord) -> dict:
    return {
        "id": record.id,
        "pet_id": record.pet_id,
        "zone": record.zone,
        "zone_label": ZONE_LABELS.get(record.zone, record.zone),
        "entered_at": _utc_iso(record.entered_at),
        "left_at": _utc_iso(record.left_at) if record.left_at else None,
        "duration_seconds": record.duration_seconds,
    }


def _utc_iso(value: datetime) -> str:
    """Serialize SQLite's naive UTC datetimes with an explicit UTC offset."""
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat()
