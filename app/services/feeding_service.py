"""Derive conservative feeding candidates from stable HX711 weight plateaus."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.iot import FeedingEvent, SensorReading


GOOD_QUALITY = "GOOD"


def detect_feeding_candidate(
    db: Session,
    reading: SensorReading,
    *,
    cat_house_id: int,
) -> FeedingEvent | None:
    """Create one candidate after a stable-before/drop/stable-after pattern.

    Four good samples are required. The rule deliberately favors explainability
    over sensitivity and never labels the result as confirmed consumption.
    """
    recent = db.scalars(
        select(SensorReading)
        .where(SensorReading.device_id == reading.device_id)
        .order_by(SensorReading.measured_at.desc(), SensorReading.id.desc())
        .limit(4)
    ).all()
    if len(recent) < 4 or any(item.quality != GOOD_QUALITY for item in recent):
        return None

    after_2, after_1, before_2, before_1 = recent
    tolerance = settings.feeding_stable_tolerance_grams
    if abs(before_1.filtered_weight_grams - before_2.filtered_weight_grams) > tolerance:
        return None
    if abs(after_1.filtered_weight_grams - after_2.filtered_weight_grams) > tolerance:
        return None

    before = (before_1.filtered_weight_grams + before_2.filtered_weight_grams) / 2
    after = (after_1.filtered_weight_grams + after_2.filtered_weight_grams) / 2
    consumed = before - after
    if not settings.feeding_min_drop_grams <= consumed <= settings.feeding_max_drop_grams:
        return None

    existing = db.scalar(
        select(FeedingEvent).where(
            FeedingEvent.device_id == reading.device_id,
            FeedingEvent.start_reading_id == before_2.id,
        )
    )
    if existing:
        return existing

    event = FeedingEvent(
        device_id=reading.device_id,
        cat_house_id=cat_house_id,
        pet_id=reading.pet_id,
        start_reading_id=before_2.id,
        end_reading_id=after_2.id,
        started_at=before_2.measured_at,
        ended_at=after_2.measured_at,
        weight_before_grams=round(before, 3),
        weight_after_grams=round(after, 3),
        estimated_consumed_grams=round(consumed, 3),
        confidence=0.75,
        status="CANDIDATE",
        source="WEIGHT_RULE",
        simulated=any(item.simulated for item in recent),
    )
    db.add(event)
    return event
