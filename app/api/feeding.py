"""Read-only feeding candidate API for authorized members."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_user
from app.config import settings
from app.database import get_db
from app.models.iot import FeedingEvent
from app.services.governance_service import ensure_pet_access


router = APIRouter(prefix="/api/feeding", tags=["feeding"])


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).isoformat()


@router.get("/events")
def list_feeding_events(
    limit: int = Query(default=50, ge=1, le=200),
    member: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    ensure_pet_access(db, member, settings.default_pet_id)
    rows = db.scalars(
        select(FeedingEvent)
        .where(FeedingEvent.pet_id == settings.default_pet_id)
        .order_by(FeedingEvent.started_at.desc(), FeedingEvent.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "device_id": row.device_id,
            "cat_house_id": row.cat_house_id,
            "pet_id": row.pet_id,
            "started_at": _iso(row.started_at),
            "ended_at": _iso(row.ended_at),
            "weight_before_grams": row.weight_before_grams,
            "weight_after_grams": row.weight_after_grams,
            "estimated_consumed_grams": row.estimated_consumed_grams,
            "confidence": row.confidence,
            "status": row.status,
            "source": row.source,
            "simulated": row.simulated,
        }
        for row in rows
    ]
