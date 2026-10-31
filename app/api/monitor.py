"""AI monitor lifecycle and live status API."""

from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.api.dependencies import require_roles
from app.config import BASE_DIR, settings
from app.runtime import monitor_manager


router = APIRouter(prefix="/api/monitor", tags=["monitor"])


class MonitorStart(BaseModel):
    source: int | str | None = None
    detector: str = "yolo"
    save_annotated_video: bool = False


@router.get("/status")
def status():
    return asdict(monitor_manager.get_status())


@router.get("/frame")
def frame():
    """Serve the current camera frame only through the authenticated API."""
    live_frame = monitor_manager.get_frame()
    if live_frame is not None:
        return Response(
            content=live_frame,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store, max-age=0"},
        )
    if not settings.live_frame_path.exists():
        raise HTTPException(404, "Live frame is not available yet")
    return FileResponse(
        settings.live_frame_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.post("/start", status_code=202)
def start(
    payload: MonitorStart,
    _member: dict = Depends(require_roles("CAREGIVER", "ADMIN")),
):
    if payload.detector not in {"yolo", "demo-color"}:
        raise HTTPException(400, "detector must be yolo or demo-color")
    source = payload.source
    if isinstance(source, str) and not source.isdigit():
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = BASE_DIR / source_path
        try:
            source_path = source_path.resolve(strict=True)
            source_path.relative_to(BASE_DIR.resolve())
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, f"Video not found: {source}")
        if not source_path.is_file() or source_path.suffix.lower() not in {
            ".mp4",
            ".avi",
            ".mov",
            ".mkv",
            ".webm",
        }:
            raise HTTPException(404, f"Video not found: {source}")
        source = str(source_path)
    elif isinstance(source, str) and source.isdigit():
        source = int(source)
    if isinstance(source, int) and source < 0:
        raise HTTPException(400, "Camera index must be zero or greater")
    output = (
        BASE_DIR / "outputs" / f"annotated_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.mp4"
        if payload.save_annotated_video
        else None
    )
    return asdict(monitor_manager.start(source, payload.detector, output))


@router.post("/stop")
def stop(_member: dict = Depends(require_roles("CAREGIVER", "ADMIN"))):
    return asdict(monitor_manager.stop())
