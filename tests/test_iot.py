from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.database import get_db
from app.main import app


@pytest.fixture(autouse=True)
def isolated_test_service_key():
    """Use a non-secret test key only inside IoT tests, then restore configuration."""
    original = settings.service_key
    object.__setattr__(settings, "service_key", "test-iot-key")
    try:
        yield
    finally:
        object.__setattr__(settings, "service_key", original)


def _measurement(sequence: int, grams: float, seconds: int = 0) -> dict:
    return {
        "device_uid": "SIM-HX711-001",
        "sequence_no": sequence,
        "measured_at": (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(),
        "raw_value": int(grams * 1000),
        "raw_weight_grams": grams,
        "filtered_weight_grams": grams,
        "quality": "GOOD",
        "firmware_version": "pytest-simulator",
        "simulated": True,
    }


def test_measurement_auth_validation_and_deduplication():
    sequence = time.time_ns()
    payload = _measurement(sequence, 100.0)
    with TestClient(app) as client:
        assert client.post("/api/ingest/measurements", json=payload).status_code == 401
        assert client.post(
            "/api/ingest/measurements",
            json=payload,
            headers={"X-Service-Key": "wrong-key"},
        ).status_code == 401
        first = client.post(
            "/api/ingest/measurements",
            json=payload,
            headers={"X-Service-Key": "test-iot-key"},
        )
        assert first.status_code == 201
        assert first.json()["simulated"] is True
        duplicate = client.post(
            "/api/ingest/measurements",
            json=payload,
            headers={"X-Service-Key": "test-iot-key"},
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["duplicate"] is True
        invalid_weight = {**payload, "sequence_no": sequence + 1, "filtered_weight_grams": -501}
        assert client.post(
            "/api/ingest/measurements",
            json=invalid_weight,
            headers={"X-Service-Key": "test-iot-key"},
        ).status_code == 422
        invalid_time = {**payload, "sequence_no": sequence + 2, "measured_at": "not-a-time"}
        assert client.post(
            "/api/ingest/measurements",
            json=invalid_time,
            headers={"X-Service-Key": "test-iot-key"},
        ).status_code == 422
        future_time = {
            **payload,
            "sequence_no": sequence + 3,
            "measured_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        }
        assert client.post(
            "/api/ingest/measurements",
            json=future_time,
            headers={"X-Service-Key": "test-iot-key"},
        ).status_code == 422
        expired_time = {
            **payload,
            "sequence_no": sequence + 4,
            "measured_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
        }
        assert client.post(
            "/api/ingest/measurements",
            json=expired_time,
            headers={"X-Service-Key": "test-iot-key"},
        ).status_code == 422


def test_simulated_plateaus_create_traceable_feeding_candidate_and_persist():
    sequence = time.time_ns()
    values = (120.0, 120.2, 110.0, 110.1)
    with TestClient(app) as client:
        for index, grams in enumerate(values):
            response = client.post(
                "/api/ingest/measurements",
                json=_measurement(sequence + index, grams, index),
                headers={"X-Service-Key": "test-iot-key"},
            )
            assert response.status_code == 201
        client.post(
            "/login",
            data={"email": "owner@meow.local", "password": "Meow123!"},
        )
        events = client.get("/api/feeding/events").json()
        matching = [event for event in events if event["simulated"]]
        assert matching
        assert 9.0 <= matching[0]["estimated_consumed_grams"] <= 11.0
        assert matching[0]["status"] == "CANDIDATE"

    # A new app lifespan reads the same database instead of process memory.
    with TestClient(app) as restarted:
        restarted.post(
            "/login",
            data={"email": "owner@meow.local", "password": "Meow123!"},
        )
        assert any(event["simulated"] for event in restarted.get("/api/feeding/events").json())


def test_iot_queries_follow_existing_roles():
    with TestClient(app) as caregiver:
        caregiver.post(
            "/login",
            data={"email": "caregiver@meow.local", "password": "Meow123!"},
        )
        assert caregiver.get("/api/iot/devices").status_code == 200
        assert caregiver.get("/api/iot/measurements").status_code == 200
    with TestClient(app) as owner:
        owner.post(
            "/login",
            data={"email": "owner@meow.local", "password": "Meow123!"},
        )
        assert owner.get("/api/iot/devices").status_code == 403
        assert owner.get("/api/feeding/events").status_code == 200


def test_measurement_database_outage_returns_503():
    class BrokenSession:
        def scalar(self, *_args, **_kwargs):
            raise OperationalError("SELECT", {}, RuntimeError("offline"))

        def rollback(self):
            return None

        def close(self):
            return None

    def broken_db():
        yield BrokenSession()

    app.dependency_overrides[get_db] = broken_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/ingest/measurements",
                json=_measurement(time.time_ns(), 100.0),
                headers={"X-Service-Key": "test-iot-key"},
            )
            assert response.status_code == 503
    finally:
        app.dependency_overrides.pop(get_db, None)
