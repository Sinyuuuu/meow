"""Activity records and daily analytics API."""

from datetime import date, datetime, time, timedelta, timezone

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
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


@router.get("/analytics/range")
def range_analytics(
    days: int = Query(default=7, ge=1, le=90),
    start: date | None = None,
    end: date | None = None,
    member: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Build explainable cross-day analytics from completed ROI intervals."""
    ensure_pet_access(db, member, settings.default_pet_id)
    today = datetime.now(settings.timezone).date()
    end_day = end or today
    start_day = start or (end_day - timedelta(days=days - 1))
    if end_day < start_day or (end_day - start_day).days > 89:
        raise HTTPException(400, "Date range must be between 1 and 90 days")
    start_utc = datetime.combine(start_day, time.min, tzinfo=settings.timezone).astimezone(timezone.utc)
    end_utc = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=settings.timezone).astimezone(timezone.utc)
    records = db.scalars(
        select(ActivityRecord)
        .where(
            ActivityRecord.pet_id == settings.default_pet_id,
            ActivityRecord.zone.in_(ROI_ZONES),
            ActivityRecord.entered_at < end_utc,
            or_(ActivityRecord.left_at.is_(None), ActivityRecord.left_at > start_utc),
        )
        .order_by(ActivityRecord.entered_at, ActivityRecord.id)
    ).all()

    zone_seconds = Counter({zone: 0 for zone in ROI_ZONES})
    zone_events = Counter({zone: 0 for zone in ROI_ZONES})
    daily: dict[str, Counter] = defaultdict(Counter)
    heatmap: dict[str, Counter] = defaultdict(Counter)
    transitions: Counter[tuple[str, str]] = Counter()
    previous_zone: str | None = None
    completed_intervals = 0
    for record in records:
        entered = record.entered_at if record.entered_at.tzinfo else record.entered_at.replace(tzinfo=timezone.utc)
        local_entered = entered.astimezone(settings.timezone)
        day_key = local_entered.date().isoformat()
        zone_events[record.zone] += 1
        daily[day_key][f"{record.zone}_events"] += 1
        heatmap[day_key][local_entered.hour] += 1
        if previous_zone and previous_zone != record.zone:
            transitions[(previous_zone, record.zone)] += 1
        previous_zone = record.zone
        if record.left_at is None:
            continue
        left = record.left_at if record.left_at.tzinfo else record.left_at.replace(tzinfo=timezone.utc)
        clipped_start = max(entered.astimezone(timezone.utc), start_utc)
        clipped_end = min(left.astimezone(timezone.utc), end_utc)
        seconds = max(0, int((clipped_end - clipped_start).total_seconds()))
        if seconds:
            zone_seconds[record.zone] += seconds
            daily[day_key][f"{record.zone}_seconds"] += seconds
            completed_intervals += 1

    day_count = (end_day - start_day).days + 1
    daily_rows = []
    for offset in range(day_count):
        day_value = start_day + timedelta(days=offset)
        key = day_value.isoformat()
        daily_rows.append({
            "date": key,
            "zones": {
                zone: {"duration_seconds": daily[key][f"{zone}_seconds"], "event_count": daily[key][f"{zone}_events"]}
                for zone in ROI_ZONES
            },
        })
    heatmap_rows = [
        {"date": row["date"], "hours": [heatmap[row["date"]][hour] for hour in range(24)]}
        for row in daily_rows
    ]
    total_seconds = sum(zone_seconds.values())
    total_events = sum(zone_events.values())
    return {
        "range": {"start": start_day.isoformat(), "end": end_day.isoformat(), "days": day_count},
        "basis": "duration" if total_seconds else "events",
        "completed_interval_count": completed_intervals,
        "total_duration_seconds": total_seconds,
        "total_event_count": total_events,
        "zones": {
            zone: {
                "label": ZONE_LABELS.get(zone, zone),
                "duration_seconds": zone_seconds[zone],
                "event_count": zone_events[zone],
                "ratio": round((zone_seconds[zone] / total_seconds if total_seconds else zone_events[zone] / total_events) * 100, 1)
                if (total_seconds or total_events) else 0,
            }
            for zone in ROI_ZONES
        },
        "daily": daily_rows,
        "heatmap": heatmap_rows,
        "transitions": [
            {"from": source, "to": target, "count": count}
            for (source, target), count in transitions.most_common(5)
        ],
        "limitations": [
            "僅使用已記錄的 ROI 區域事件。",
            "進入進食區或飲水區不等同已確認進食或飲水。",
            "未偵測資料不會被推定為休息。",
        ],
    }


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
