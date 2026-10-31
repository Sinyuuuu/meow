"""SQLAlchemy engine, sessions, and schema initialization."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all database models."""


# A source ZIP cannot preserve an empty database directory. Create SQLite's
# parent directory before SQLAlchemy attempts its first connection so a fresh
# checkout or extracted archive starts without manual setup.
if settings.database_url.startswith("sqlite"):
    sqlite_database = make_url(settings.database_url).database
    if sqlite_database and sqlite_database != ":memory:":
        Path(sqlite_database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def get_db():
    """Yield a request-scoped database session."""
    session = SessionLocal()
    try:
        yield session
    except SQLAlchemyError:
        logger.exception("Database request failed")
        session.rollback()
        raise
    except Exception:
        # Authorization and validation errors are application responses, not
        # database failures; roll back quietly and preserve their HTTP status.
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create tables and seed the small, coherent Momo demo dataset."""
    from app.models import (
        Alert,
        AuditLog,
        BoardingOrder,
        CameraDevice,
        CareTask,
        CatHouse,
        Pet,
        PetAccess,
        SystemSetting,
        SystemTask,
        User,
        UserState,
    )
    from app.services.auth_service import hash_password

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.query(User).count() == 0:
            owner = User(
                name="小花",
                email="owner@meow.local",
                password_hash=hash_password("Meow123!"),
                role="OWNER",
            )
            caregiver = User(
                name="小安",
                email="caregiver@meow.local",
                password_hash=hash_password("Meow123!"),
                role="CAREGIVER",
            )
            admin = User(
                name="系統管理員",
                email="admin@meow.local",
                password_hash=hash_password("Meow123!"),
                role="ADMIN",
            )
            db.add_all([owner, caregiver, admin])
            db.flush()
            pet = Pet(
                owner_id=owner.id,
                name="Momo",
                gender="母",
                age=3,
                breed="米克斯",
                weight=4.2,
                personality="慢熟、喜歡待在高處",
                food_notes="早晚各一餐",
                care_notes="先讓 Momo 聞手再輕摸",
                medical_notes="飼主提供：無特殊用藥",
            )
            db.add(pet)
            db.flush()
            house = CatHouse(room_number="A01", status="OCCUPIED", current_pet_id=pet.id)
            db.add(house)
            db.flush()
            db.add(
                BoardingOrder(
                    pet_id=pet.id,
                    cat_house_id=house.id,
                    status="CHECKED_IN",
                )
            )
            db.add(CameraDevice(cat_house_id=house.id, name="A01 主攝影機", source="0", status="READY"))
            db.add_all(
                [
                    CareTask(pet_id=pet.id, task_type="早餐", scheduled_time="08:00", completed=True),
                    CareTask(pet_id=pet.id, task_type="換水", scheduled_time="09:00", completed=True),
                    CareTask(pet_id=pet.id, task_type="清理貓砂", scheduled_time="10:00", completed=True),
                    CareTask(pet_id=pet.id, task_type="下午陪玩", scheduled_time="15:00", completed=False),
                    CareTask(pet_id=pet.id, task_type="晚餐", scheduled_time="18:00", completed=False),
                ]
            )
            db.add(
                Alert(
                    pet_id=pet.id,
                    type="SYSTEM_READY",
                    message="AI 監測已就緒，等待攝影機或測試影片。",
                    resolved=True,
                )
            )
            db.flush()

        # Governance data is idempotently added for both fresh databases and
        # databases created by an earlier prototype release.
        users = db.query(User).all()
        for user in users:
            if db.get(UserState, user.id) is None:
                db.add(UserState(user_id=user.id, status="ACTIVE"))
        pet = db.get(Pet, settings.default_pet_id)
        caregiver = db.query(User).filter(User.email == "caregiver@meow.local").one_or_none()
        if pet and caregiver:
            access = db.query(PetAccess).filter_by(user_id=caregiver.id, pet_id=pet.id).one_or_none()
            if access is None:
                db.add(PetAccess(user_id=caregiver.id, pet_id=pet.id, active=True))
        defaults = {
            "water_zone_hours": "8",
            "long_stay_minutes": "60",
        }
        for key, value in defaults.items():
            if db.get(SystemSetting, key) is None:
                db.add(SystemSetting(key=key, value=value))
        if db.query(SystemTask).count() == 0:
            db.add_all(
                [
                    SystemTask(title="確認 A01 攝影機畫面與 ROI 對位"),
                    SystemTask(title="執行今日 AI Monitor 測試"),
                    SystemTask(title="檢查未處理的活動異常提醒"),
                ]
            )
        if db.query(AuditLog).count() == 0:
            db.add(AuditLog(action="SYSTEM_INITIALIZED", detail="治理功能與權限資料已就緒"))
        db.commit()
        if settings.database_url.startswith("sqlite"):
            db.execute(text("PRAGMA optimize"))
