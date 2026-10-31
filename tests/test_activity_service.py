from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ActivityRecord
from app.services.activity_service import ActivityService, today_summary


def test_transition_closes_previous_interval():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with Session() as db:
        service = ActivityService(db, pet_id=1)
        service.transition(None, "FOOD", started)
        # Simulate a fresh process that does not remember the stale open zone.
        service.transition(None, "WATER", started + timedelta(seconds=25))
        records = db.scalars(select(ActivityRecord).order_by(ActivityRecord.id)).all()
        assert len(records) == 2
        assert records[0].duration_seconds == 25
        assert records[0].left_at is not None
        assert records[1].zone == "WATER"
        assert records[1].left_at is None


def test_today_summary_includes_open_interval_duration():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with Session() as db:
        db.add(
            ActivityRecord(
                pet_id=1,
                zone="FOOD",
                entered_at=now - timedelta(seconds=120),
            )
        )
        db.commit()
        summary = today_summary(db, 1)
        assert summary["FOOD"]["count"] == 1
        assert summary["FOOD"]["duration_seconds"] >= 119


def test_transition_to_general_closes_without_creating_a_record():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with Session() as db:
        service = ActivityService(db, pet_id=1)
        service.transition(None, "FOOD", started)
        result = service.transition("FOOD", None, started + timedelta(seconds=10))
        records = db.scalars(select(ActivityRecord)).all()
        assert result is None
        assert len(records) == 1
        assert records[0].duration_seconds == 10
