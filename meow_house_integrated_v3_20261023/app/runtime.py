"""Thread-safe lifecycle manager for one local AI monitor."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from app.ai.monitor import AIMonitor, MonitorStatus, build_detector
from app.config import settings


logger = logging.getLogger(__name__)


class MonitorManager:
    """Run at most one monitor thread and expose its last published state."""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._monitor: AIMonitor | None = None
        self._status = MonitorStatus(pet_id=settings.default_pet_id)
        self._frame: bytes | None = None
        self._lock = threading.Lock()
        self._cancel_requested = threading.Event()

    def start(
        self,
        source: int | str | None = None,
        detector_name: str = "yolo",
        output_path: Path | None = None,
    ) -> MonitorStatus:
        """Start monitoring in the background; detector loading occurs in its thread."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self._status
            resolved_source = settings.camera_source if source is None else source
            self._cancel_requested.clear()
            self._frame = None
            self._status = MonitorStatus(
                running=True,
                source=str(resolved_source),
                detector=detector_name,
                pet_id=settings.default_pet_id,
                zone_point_mode=settings.zone_point_mode,
                message="正在載入 AI 模型…",
            )
            def worker() -> None:
                try:
                    detector = build_detector(detector_name)
                    if self._cancel_requested.is_set():
                        self._set_status(
                            MonitorStatus(
                                running=False,
                                source=str(resolved_source),
                                detector=detector_name,
                                pet_id=settings.default_pet_id,
                                zone_point_mode=settings.zone_point_mode,
                                message="已停止監測",
                            ),
                        )
                        return
                    monitor = AIMonitor(
                        resolved_source,
                        detector,
                        pet_id=settings.default_pet_id,
                        threshold_seconds=settings.zone_switch_seconds,
                        output_path=output_path,
                        status_callback=self._set_status,
                        frame_callback=self._set_frame,
                    )
                    monitor.status.detector = detector_name
                    with self._lock:
                        self._monitor = monitor
                        cancelled = self._cancel_requested.is_set()
                    if cancelled:
                        monitor.stop()
                    monitor.run()
                except Exception as exc:
                    logger.exception("AI monitor stopped unexpectedly")
                    self._set_status(
                        MonitorStatus(
                            running=False,
                            source=str(resolved_source),
                            detector=detector_name,
                            pet_id=settings.default_pet_id,
                            zone_point_mode=settings.zone_point_mode,
                            message=f"監測啟動失敗：{exc}",
                        ),
                    )
                finally:
                    with self._lock:
                        self._monitor = None

            self._thread = threading.Thread(target=worker, name="ai-monitor", daemon=True)
            self._thread.start()
            return self._status

    def stop(self) -> MonitorStatus:
        """Request a clean monitor shutdown without blocking the web request."""
        self._cancel_requested.set()
        with self._lock:
            monitor = self._monitor
            if self._status.running:
                self._status.message = "正在停止監測…"
            status = self._status
        if monitor:
            monitor.stop()
        return status

    def get_status(self) -> MonitorStatus:
        """Return the current in-memory state without filesystem lock contention."""
        with self._lock:
            return self._status

    def get_frame(self) -> bytes | None:
        """Return a copy of the latest encoded JPEG without touching the filesystem."""
        with self._lock:
            return self._frame

    def _set_frame(self, frame: bytes) -> None:
        with self._lock:
            self._frame = frame

    def _set_status(self, status: MonitorStatus) -> None:
        with self._lock:
            self._status = status


monitor_manager = MonitorManager()
