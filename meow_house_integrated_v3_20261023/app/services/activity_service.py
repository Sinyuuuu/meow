"""Create and query debounced cat-zone activity intervals."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.activity import ActivityRecord


logger = logging.getLogger(__name__)


class ActivityService:
    """Persist one open interval per pet and close it on zone changes."""

    def __init__(self, db: Session, pet_id: int):
        self.db = db
        self.pet_id = pet_id

    def transition(
        self, old_zone: str | None, new_zone: str | None, at: datetime
    ) -> ActivityRecord | None:
        """Close the current interval and optionally start a functional-zone interval."""
        try:
            # Always close stale open intervals. A prior camera or process crash must
            # not allow multiple simultaneous activities for the same cat.
            open_records = self.db.scalars(
                select(ActivityRecord).where(
                    ActivityRecord.pet_id == self.pet_id,
                    ActivityRecord.left_at.is_(None),
                )
            ).all()
            for open_record in open_records:
                open_record.left_at = at
                open_record.duration_seconds = max(
                    0, int((at - _aware(open_record.entered_at)).total_seconds())
                )
            if new_zone is None:
                self.db.commit()
                return None
            record = ActivityRecord(pet_id=self.pet_id, zone=new_zone, entered_at=at)
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            return record
        except Exception:
            self.db.rollback()
            logger.exception("Could not persist activity transition")
            raise

    def close_open(self, at: datetime) -> None:
        """Close an open record when monitoring stops cleanly."""
        records = self.db.scalars(
            select(ActivityRecord)
            .where(ActivityRecord.pet_id == self.pet_id, ActivityRecord.left_at.is_(None))
            .order_by(ActivityRecord.entered_at.desc())
        ).all()
        if not records:
            return
        for record in records:
            record.left_at = at
            record.duration_seconds = max(
                0, int((at - _aware(record.entered_at)).total_seconds())
            )
        self.db.commit()


def today_summary(db: Session, pet_id: int) -> dict[str, dict[str, int]]:
    """Return local-day entry counts and clipped dwell seconds by zone."""
    now_local = datetime.now(settings.timezone)
    start = datetime.combine(now_local.date(), time.min, tzinfo=settings.timezone).astimezone(timezone.utc)
    end = datetime.combine(
        now_local.date() + timedelta(days=1),
        time.min,
        tzinfo=settings.timezone,
    ).astimezone(timezone.utc)
    count_rows = db.execute(
        select(ActivityRecord.zone, func.count(ActivityRecord.id))
        .where(
            ActivityRecord.pet_id == pet_id,
            ActivityRecord.entered_at >= start,
            ActivityRecord.entered_at < end,
        )
        .group_by(ActivityRecord.zone)
    ).all()
    result = {
        zone: {"count": 0, "duration_seconds": 0}
        for zone in ("FOOD", "WATER", "LITTER")
    }
    for zone, count in count_rows:
        if zone in result:
            result[zone]["count"] = int(count)

    overlapping = db.scalars(
        select(ActivityRecord).where(
            ActivityRecord.pet_id == pet_id,
            ActivityRecord.entered_at < end,
            or_(ActivityRecord.left_at.is_(None), ActivityRecord.left_at > start),
        )
    ).all()
    now_utc = now_local.astimezone(timezone.utc)
    for record in overlapping:
        entered = max(_aware(record.entered_at), start)
        left = min(_aware(record.left_at) if record.left_at else now_utc, end, now_utc)
        if record.zone in result:
            result[record.zone]["duration_seconds"] += max(
                0, int((left - entered).total_seconds())
            )
    return result


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
