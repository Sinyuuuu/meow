"""Small rule-based activity alerts; deliberately not medical diagnosis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.activity import ActivityRecord
from app.models.alert import Alert
from app.services.governance_service import get_setting_float


RULE_MESSAGES = {
    "NO_WATER_ZONE": "Momo 已較長時間未進入飲水區，建議照護人員確認。",
    "NO_FOOD_ZONE": "Momo 今日進食區活動較少，建議照護人員確認。",
    "LONG_STAY": "Momo 已在同一區域停留較長時間，建議照護人員確認。",
    "NOT_DETECTED": "目前較長時間未在畫面中偵測到 Momo，建議照護人員確認。",
}


def create_alert_once(db: Session, pet_id: int, alert_type: str, message: str | None = None) -> Alert:
    """Create at most one unresolved alert of a given type for a pet."""
    existing = db.scalar(
        select(Alert).where(
            Alert.pet_id == pet_id,
            Alert.type == alert_type,
            Alert.resolved.is_(False),
        )
    )
    if existing:
        return existing
    alert = Alert(
        pet_id=pet_id,
        type=alert_type,
        message=message or RULE_MESSAGES[alert_type],
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def evaluate_daily_rules(db: Session, pet_id: int) -> list[Alert]:
    """Evaluate conservative zone-visit reminders for the current day."""
    now = datetime.now(timezone.utc)
    local_now = now.astimezone(settings.timezone)
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    created: list[Alert] = []
    water_hours = get_setting_float(db, "water_zone_hours", 8)
    for zone, alert_type, hours in (
        ("WATER", "NO_WATER_ZONE", water_hours),
        ("FOOD", "NO_FOOD_ZONE", 12),
    ):
        latest = db.scalar(
            select(ActivityRecord.entered_at)
            .where(
                ActivityRecord.pet_id == pet_id,
                ActivityRecord.zone == zone,
                ActivityRecord.entered_at >= start,
            )
            .order_by(ActivityRecord.entered_at.desc())
        )
        latest_aware = latest if latest is None or latest.tzinfo else latest.replace(tzinfo=timezone.utc)
        if now - (latest_aware or start) >= timedelta(hours=hours):
            created.append(create_alert_once(db, pet_id, alert_type))
    return created
