"""Environment-backed application and AI monitor settings."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Load a small KEY=VALUE .env file without adding a runtime dependency."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def _camera_source(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def _database_url(value: str | None) -> str:
    """Return a stable database URL, resolving relative SQLite paths from the project root."""
    raw = value or f"sqlite:///{(BASE_DIR / 'database' / 'app.db').as_posix()}"
    prefix = "sqlite:///"
    if not raw.startswith(prefix):
        return raw
    database = raw[len(prefix) :]
    if database == ":memory:":
        return raw
    path = Path(database).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return f"{prefix}{path.resolve().as_posix()}"


@dataclass(frozen=True)
class Settings:
    """Central configuration shared by web, database, and AI modules."""

    app_name: str = os.getenv("APP_NAME", "Meow一下")
    # Ephemeral fallback is safe for local development; shared deployments must
    # set APP_SECRET_KEY so sessions survive restarts and multiple workers.
    secret_key: str = os.getenv("APP_SECRET_KEY") or secrets.token_urlsafe(32)
    database_url: str = _database_url(os.getenv("DATABASE_URL"))
    app_timezone: str = os.getenv("APP_TIMEZONE", "Asia/Taipei")
    camera_source: int | str = _camera_source(os.getenv("CAMERA_SOURCE", "0"))
    yolo_model: str = os.getenv("YOLO_MODEL", "yolo11n.pt")
    yolo_confidence: float = float(os.getenv("YOLO_CONFIDENCE", "0.35"))
    yolo_image_size: int = int(os.getenv("YOLO_IMAGE_SIZE", "960"))
    zone_point_mode: str = os.getenv("ZONE_POINT_MODE", "center").strip().lower()
    zone_switch_seconds: float = float(os.getenv("ZONE_SWITCH_SECONDS", "2.0"))
    missing_cat_alert_seconds: float = float(os.getenv("MISSING_CAT_ALERT_SECONDS", "30"))
    long_stay_alert_seconds: float = float(os.getenv("LONG_STAY_ALERT_SECONDS", "3600"))
    monitor_sample_fps: float = float(os.getenv("MONITOR_SAMPLE_FPS", "8"))
    default_pet_id: int = int(os.getenv("DEFAULT_PET_ID", "1"))
    service_key: str | None = os.getenv("MEOW_SERVICE_KEY") or None
    roi_config_path: Path = BASE_DIR / os.getenv("ROI_CONFIG_PATH", "data/rois.json")
    state_path: Path = BASE_DIR / "database" / "monitor_state.json"
    live_frame_path: Path = BASE_DIR / "database" / "live.jpg"

    def __post_init__(self) -> None:
        if self.zone_point_mode not in {"center", "bottom_center"}:
            raise ValueError("ZONE_POINT_MODE must be center or bottom_center")
        if not 0 < self.yolo_confidence <= 1:
            raise ValueError("YOLO_CONFIDENCE must be greater than 0 and at most 1")
        if self.yolo_image_size < 320 or self.yolo_image_size > 1920:
            raise ValueError("YOLO_IMAGE_SIZE must be between 320 and 1920")
        if self.zone_switch_seconds < 0:
            raise ValueError("ZONE_SWITCH_SECONDS must be non-negative")

    @property
    def timezone(self) -> ZoneInfo:
        """Configured local timezone used for daily dashboard boundaries."""
        return ZoneInfo(self.app_timezone)


settings = Settings()
