from datetime import datetime, timedelta, timezone

from app.ai.tracker import ZoneDebouncer


def test_requires_stable_candidate_before_switch():
    tracker = ZoneDebouncer(2.0)
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert tracker.update("REST", started) is None
    assert tracker.update("ACTIVITY", started + timedelta(seconds=1)) is None
    assert tracker.update("REST", started + timedelta(seconds=1.1)) is None
    transition = tracker.update("REST", started + timedelta(seconds=3.2))
    assert transition is not None
    assert transition.previous_zone is None
    assert transition.current_zone == "REST"


def test_single_frame_jitter_does_not_change_zone():
    tracker = ZoneDebouncer(1.0)
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    tracker.update("REST", started)
    tracker.update("REST", started + timedelta(seconds=1.1))
    tracker.update("WATER", started + timedelta(seconds=2))
    tracker.update("REST", started + timedelta(seconds=2.1))
    assert tracker.current_zone == "REST"


def test_reset_clears_last_known_zone_after_sustained_absence():
    tracker = ZoneDebouncer(0)
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    tracker.update("REST", started)
    assert tracker.reset() == "REST"
    assert tracker.current_zone is None
    assert tracker.candidate_zone is None
