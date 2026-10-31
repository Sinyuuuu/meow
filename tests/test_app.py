from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import ActivityRecord


def test_login_and_dashboard():
    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert client.get("/api/activities/summary").status_code == 401
        assert client.get("/api/monitor/frame").status_code == 401
        assert client.get("/static/images/live.jpg").status_code == 404
        response = client.post(
            "/login",
            data={"email": "owner@meow.local", "password": "Meow123!"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert client.get("/").status_code == 200
        assert client.get("/api/activities/summary").status_code == 200
        assert client.get("/api/monitor/frame").status_code == 200
        assert client.post(
            "/api/monitor/start",
            json={"source": "data/demo.mp4", "detector": "demo-color"},
        ).status_code == 403
        assert client.get("/health").json()["status"] == "ok"


def test_activity_timestamps_include_utc_offset():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(
                ActivityRecord(
                    pet_id=1,
                    zone="FOOD",
                    entered_at=datetime.now(timezone.utc),
                    left_at=datetime.now(timezone.utc),
                    duration_seconds=0,
                )
            )
            db.commit()
        client.post(
            "/login",
            data={"email": "owner@meow.local", "password": "Meow123!"},
        )
        records = client.get("/api/activities/recent").json()
        assert records
        assert records[0]["entered_at"].endswith("+00:00")


def test_monitor_controls_validate_role_and_source():
    with TestClient(app) as client:
        client.post(
            "/login",
            data={"email": "caregiver@meow.local", "password": "Meow123!"},
        )
        assert client.post(
            "/api/monitor/start",
            json={"source": -1, "detector": "demo-color"},
        ).status_code == 400
        assert client.post(
            "/api/monitor/start",
            json={"source": ".", "detector": "demo-color"},
        ).status_code == 404
        assert client.post(
            "/api/monitor/start",
            json={"source": "C:/Windows/win.ini", "detector": "demo-color"},
        ).status_code == 404


def test_alert_rule_evaluation_uses_post():
    with TestClient(app) as client:
        client.post(
            "/login",
            data={"email": "caregiver@meow.local", "password": "Meow123!"},
        )
        response = client.post("/api/alerts/evaluate")
        assert response.status_code == 202
        assert response.json()["evaluated"] is True


def test_role_specific_dashboards_and_care_permissions():
    with TestClient(app) as owner:
        owner.post(
            "/login",
            data={"email": "owner@meow.local", "password": "Meow123!"},
        )
        assert "Momo 的今日照護" in owner.get("/").text
        tasks = owner.get("/api/care/tasks").json()
        assert tasks
        assert owner.patch(
            f"/api/care/tasks/{tasks[0]['id']}",
            json={"completed": False},
        ).status_code == 403

    with TestClient(app) as caregiver:
        caregiver.post(
            "/login",
            data={"email": "caregiver@meow.local", "password": "Meow123!"},
        )
        assert "今日照護工作台" in caregiver.get("/").text
        task = caregiver.get("/api/care/tasks").json()[0]
        response = caregiver.patch(
            f"/api/care/tasks/{task['id']}",
            json={"completed": task["completed"]},
        )
        assert response.status_code == 200
        assert caregiver.post(
            "/api/care/logs",
            json={"type": "測試", "note": "自動測試照護紀錄"},
        ).status_code == 201

    with TestClient(app) as admin:
        admin.post(
            "/login",
            data={"email": "admin@meow.local", "password": "Meow123!"},
        )
        assert "智慧照護系統營運中心" in admin.get("/").text
        overview = admin.get("/api/admin/overview")
        assert overview.status_code == 200
        assert overview.json()["users"] >= 3
        assert admin.get("/caregiver").status_code == 403
        assert admin.post(
            "/api/care/logs",
            json={"type": "測試", "note": "管理員不可冒充照護員"},
        ).status_code == 403
        for path in (
            "/api/admin/users",
            "/api/admin/assignments",
            "/api/admin/devices",
            "/api/admin/rois",
            "/api/admin/settings",
            "/api/admin/tasks",
            "/api/admin/audit",
        ):
            assert admin.get(path).status_code == 200


def test_owner_cannot_trigger_or_use_administrator_operations():
    with TestClient(app) as owner:
        owner.post(
            "/login",
            data={"email": "owner@meow.local", "password": "Meow123!"},
        )
        assert owner.post("/api/alerts/evaluate").status_code == 403
        assert owner.get("/api/admin/users").status_code == 403


def test_device_ingest_is_closed_when_service_key_is_not_configured():
    with TestClient(app) as client:
        response = client.post("/api/ingest/heartbeat", json={"camera_device_id": 1})
        assert response.status_code == 503


def test_owner_ui_upgrade_pages_and_read_models():
    with TestClient(app) as client:
        client.post(
            "/login",
            data={"email": "owner@meow.local", "password": "Meow123!"},
        )
        for path, marker in (
            ("/", "智慧貓屋區域地圖"),
            ("/pet", "今日區域摘要"),
            ("/healthcare", "照護行事曆"),
            ("/analysis", "24 小時活動熱度"),
        ):
            response = client.get(path)
            assert response.status_code == 200
            assert marker in response.text
        assert client.get("/api/iot/pet-status").status_code == 200
        analytics = client.get("/api/activities/analytics/range?days=7")
        assert analytics.status_code == 200
        assert analytics.json()["range"]["days"] == 7


def test_owner_care_reminder_crud_is_persistent_in_isolated_database():
    with TestClient(app) as client:
        client.post(
            "/login",
            data={"email": "owner@meow.local", "password": "Meow123!"},
        )
        created = client.post(
            "/api/healthcare/reminders",
            json={
                "pet_id": 1,
                "category": "CHECKUP",
                "title": "隔離測試健康檢查",
                "scheduled_at": "2026-12-01T09:00:00+08:00",
                "recurrence": "NONE",
                "advance_minutes": 1440,
                "note": "pytest isolated database",
            },
        )
        assert created.status_code == 201
        reminder_id = created.json()["id"]
        listed = client.get("/api/healthcare/reminders")
        assert any(row["id"] == reminder_id for row in listed.json())
        completed = client.patch(
            f"/api/healthcare/reminders/{reminder_id}",
            json={"completed": True},
        )
        assert completed.status_code == 200
        assert completed.json()["completed"] is True
        assert client.delete(f"/api/healthcare/reminders/{reminder_id}").status_code == 204
