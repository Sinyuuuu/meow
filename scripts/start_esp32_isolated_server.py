"""Start a LAN-visible FastAPI server backed only by an isolated SQLite DB."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "tests" / ".tmp" / "esp32_hardware_test.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Start isolated CatSense ESP32 test server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()

    device_key = os.getenv("MEOW_DEVICE_KEY", "").strip()
    if not device_key:
        raise SystemExit("MEOW_DEVICE_KEY is required and is never printed.")
    device_uid = os.getenv("MEOW_DEVICE_UID", "ESP32-SIM-A01").strip()
    if len(device_uid) < 3:
        raise SystemExit("MEOW_DEVICE_UID must contain at least 3 characters")

    database_path = args.database.expanduser().resolve()
    production_sqlite = (PROJECT_ROOT / "database" / "app.db").resolve()
    if database_path == production_sqlite:
        raise SystemExit("Refusing to use the production SQLite path")
    database_path.parent.mkdir(parents=True, exist_ok=True)

    # These values are set before importing application modules. The project's
    # production .env remains untouched and Supabase can never be selected.
    os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    os.environ["AUTO_CREATE_SCHEMA"] = "true"
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    import uvicorn
    from sqlalchemy import select

    from app.database import SessionLocal, engine, init_db
    from app.models import CatHouse, IotDevice
    from app.services.auth_service import hash_password, verify_password

    if engine.dialect.name != "sqlite":
        raise SystemExit("Isolation guard failed: database dialect is not SQLite")

    init_db()
    with SessionLocal() as db:
        house = db.scalar(select(CatHouse).order_by(CatHouse.id))
        if house is None:
            raise SystemExit("Isolated seed did not create a cat house")
        device = db.scalar(select(IotDevice).where(IotDevice.device_uid == device_uid))
        if device is None:
            device = IotDevice(
                cat_house_id=house.id,
                device_uid=device_uid,
                name="ESP32 實體傳輸隔離測試",
                device_type="WEIGHT_SCALE",
                status="READY",
                auth_key_hash=hash_password(device_key),
                simulated=True,
            )
            db.add(device)
        else:
            device.cat_house_id = house.id
            device.status = "READY"
            device.simulated = True
            if not device.auth_key_hash or not verify_password(device_key, device.auth_key_hash):
                device.auth_key_hash = hash_password(device_key)
        db.commit()

    print("=" * 62)
    print(" CatSense ESP32 isolated test server")
    print(f" Database: isolated SQLite ({database_path})")
    print(f" Device UID: {device_uid}")
    print(f" URL: http://{args.host}:{args.port}")
    print(" Production Supabase: not selected")
    print(" Device key: configured but never printed")
    print(" Press Ctrl+C to stop")
    print("=" * 62)
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

