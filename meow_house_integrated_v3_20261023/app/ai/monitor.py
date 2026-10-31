"""End-to-end camera/video monitoring loop with annotated demo output."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from app.ai.detector import CatDetector, DemoColorCatDetector, YoloCatDetector
from app.ai.tracker import ZoneDebouncer
from app.ai.zones import ROI_ZONES, ZONE_COLORS, ZONE_LABELS, ZoneMapper
from app.config import settings
from app.database import SessionLocal
from app.models import CameraDevice
from app.services.activity_service import ActivityService
from app.services.alert_service import create_alert_once
from app.services.governance_service import get_setting_float, touch_device


logger = logging.getLogger(__name__)


@dataclass
class MonitorStatus:
    running: bool = False
    source: str = ""
    detector: str = "yolo"
    pet_id: int = 1
    pet_name: str = "Momo"
    detected: bool = False
    missing_seconds: float = 0.0
    confidence: float | None = None
    inference_ms: float | None = None
    zone_point_mode: str = "center"
    current_zone: str | None = None
    current_zone_label: str = "等待偵測"
    candidate_zone: str | None = None
    last_seen_at: str | None = None
    frame_count: int = 0
    message: str = "監測尚未啟動"
    updated_at: str | None = None


class VideoClock:
    """Use media timestamps for files and wall time for live cameras."""

    def __init__(self, capture: cv2.VideoCapture, is_file: bool):
        self.capture = capture
        self.is_file = is_file
        self.started_at = datetime.now(timezone.utc)

    def now(self) -> datetime:
        if not self.is_file:
            return datetime.now(timezone.utc)
        milliseconds = max(0.0, self.capture.get(cv2.CAP_PROP_POS_MSEC))
        return self.started_at + timedelta(milliseconds=milliseconds)


class AIMonitor:
    """Coordinate capture, detection, ROI mapping, debouncing, and persistence."""

    def __init__(
        self,
        source: int | str,
        detector: CatDetector,
        pet_id: int = 1,
        threshold_seconds: float = 2.0,
        output_path: Path | None = None,
        status_callback: Callable[[MonitorStatus], None] | None = None,
        frame_callback: Callable[[bytes], None] | None = None,
    ):
        self.source = source
        self.detector = detector
        self.pet_id = pet_id
        self.zone_mapper = ZoneMapper.default()
        self.debouncer = ZoneDebouncer(threshold_seconds)
        self.output_path = output_path
        self.status_callback = status_callback
        self.frame_callback = frame_callback
        self.stop_event = threading.Event()
        self.status = MonitorStatus(
            source=str(source),
            pet_id=pet_id,
            zone_point_mode=settings.zone_point_mode,
        )

    def stop(self) -> None:
        self.stop_event.set()

    def run(self, display: bool = False, max_frames: int | None = None) -> MonitorStatus:
        """Run until EOF, stop request, Q, or an optional frame limit."""
        capture = cv2.VideoCapture(self.source)
        if not capture.isOpened():
            self.status.message = f"無法開啟攝影機或影片：{self.source}"
            self._publish()
            raise RuntimeError(self.status.message)
        is_file = isinstance(self.source, str) and Path(self.source).exists()
        clock = VideoClock(capture, is_file)
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not np.isfinite(fps) or fps <= 0:
            fps = settings.monitor_sample_fps
        publish_every = max(1, round(fps / max(settings.monitor_sample_fps, 0.1)))
        writer = None
        if self.output_path:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            writer = cv2.VideoWriter(
                str(self.output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
            )
            if not writer.isOpened():
                writer.release()
                capture.release()
                raise RuntimeError(f"無法建立標註影片：{self.output_path}")
        last_at = datetime.now(timezone.utc)
        last_annotated: np.ndarray | None = None
        missing_since: datetime | None = None
        stable_since: datetime | None = None
        missing_handled = False
        long_stay_handled = False
        self.status.running = True
        self.status.message = "AI 監測中"
        self._publish()
        db = SessionLocal()
        activity = ActivityService(db, self.pet_id)
        last_heartbeat = 0.0
        camera_device = db.query(CameraDevice).order_by(CameraDevice.id).first()
        long_stay_seconds = get_setting_float(
            db,
            "long_stay_minutes",
            settings.long_stay_alert_seconds / 60,
        ) * 60
        try:
            if camera_device:
                touch_device(db, camera_device.id, "LOCAL_MONITOR", "AI monitor started")
                db.commit()
            while not self.stop_event.is_set():
                ok, frame = capture.read()
                if not ok:
                    self.status.message = "影片播放完成" if is_file else "攝影機訊號中斷"
                    break
                observed_at = clock.now()
                last_at = observed_at
                inference_started = time.perf_counter()
                detection = self.detector.detect(frame)
                self.status.inference_ms = round(
                    (time.perf_counter() - inference_started) * 1000,
                    1,
                )
                observed_zone = None
                if detection:
                    zone_point = detection.anchor(settings.zone_point_mode)
                    observed_zone = self.zone_mapper.locate(
                        zone_point, frame.shape[1], frame.shape[0]
                    )
                    self.status.detected = True
                    self.status.confidence = round(detection.confidence, 3)
                    self.status.last_seen_at = observed_at.isoformat()
                    self.status.missing_seconds = 0.0
                    missing_since = None
                    missing_handled = False
                else:
                    self.status.detected = False
                    self.status.confidence = None
                    if missing_since is None:
                        missing_since = observed_at
                    self.status.missing_seconds = max(
                        0.0, (observed_at - missing_since).total_seconds()
                    )
                    if (
                        not missing_handled
                        and self.status.missing_seconds >= settings.missing_cat_alert_seconds
                    ):
                        activity.close_open(missing_since)
                        self.debouncer.reset()
                        stable_since = None
                        long_stay_handled = False
                        create_alert_once(db, self.pet_id, "NOT_DETECTED")
                        missing_handled = True
                transition = self.debouncer.update(observed_zone, observed_at)
                if transition:
                    activity.transition(
                        transition.previous_zone,
                        transition.current_zone if transition.current_zone in ROI_ZONES else None,
                        transition.changed_at,
                    )
                    stable_since = transition.changed_at
                    long_stay_handled = False
                if (
                    self.debouncer.current_zone in ROI_ZONES
                    and stable_since
                    and not long_stay_handled
                    and (observed_at - stable_since).total_seconds()
                    >= long_stay_seconds
                ):
                    zone_label = ZONE_LABELS[self.debouncer.current_zone]
                    create_alert_once(
                        db,
                        self.pet_id,
                        "LONG_STAY",
                        f"Momo 已在{zone_label}停留較長時間，建議照護人員確認。",
                    )
                    long_stay_handled = True
                self.status.current_zone = self.debouncer.current_zone
                self.status.current_zone_label = ZONE_LABELS.get(
                    self.debouncer.current_zone,
                    "目前未偵測到 Momo" if missing_handled else "一般活動範圍",
                )
                self.status.candidate_zone = self.debouncer.candidate_zone
                self.status.frame_count += 1
                if camera_device and time.monotonic() - last_heartbeat >= 10:
                    touch_device(db, camera_device.id, "LOCAL_MONITOR", self.status.current_zone_label)
                    db.commit()
                    last_heartbeat = time.monotonic()
                annotated = self._annotate(frame, detection)
                last_annotated = annotated
                if writer:
                    writer.write(annotated)
                if transition or self.status.frame_count % publish_every == 0:
                    self._save_live_frame(annotated)
                    self._publish()
                if display:
                    cv2.imshow("Meow House AI Monitor", annotated)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        self.status.message = "使用者停止監測"
                        break
                if max_frames and self.status.frame_count >= max_frames:
                    self.status.message = "已到達測試影格上限"
                    break
            if self.stop_event.is_set() and self.status.message == "AI 監測中":
                self.status.message = "已停止監測"
        finally:
            try:
                activity.close_open(last_at)
            except Exception:
                logger.exception("Could not close the active zone interval during shutdown")
            db.close()
            capture.release()
            if writer:
                writer.release()
            if display:
                cv2.destroyAllWindows()
            if last_annotated is not None:
                self._save_live_frame(last_annotated)
            self.status.running = False
            self._publish()
        return self.status

    def _annotate(self, frame: np.ndarray, detection) -> np.ndarray:
        canvas = frame.copy()
        height, width = canvas.shape[:2]
        overlay = canvas.copy()
        for zone, polygon in self.zone_mapper.pixel_polygons(width, height).items():
            points = np.array(polygon, dtype=np.int32)
            cv2.fillPoly(overlay, [points], ZONE_COLORS[zone])
            cv2.polylines(canvas, [points], True, ZONE_COLORS[zone], 2)
            x, y = polygon[0]
            cv2.putText(canvas, zone, (x + 12, y + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, ZONE_COLORS[zone], 2)
        cv2.addWeighted(overlay, 0.13, canvas, 0.87, 0, canvas)
        if detection:
            x1, y1, x2, y2 = detection.bbox
            cx, cy = detection.anchor(settings.zone_point_mode)
            cv2.rectangle(canvas, (x1, y1), (x2, y2), (74, 92, 230), 3)
            cv2.circle(canvas, (cx, cy), 7, (255, 255, 255), -1)
            cv2.circle(canvas, (cx, cy), 9, (74, 92, 230), 2)
            cv2.putText(
                canvas,
                f"Momo | cat {detection.confidence:.2f}",
                (x1, max(26, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                3,
            )
            cv2.putText(
                canvas,
                f"Momo | cat {detection.confidence:.2f}",
                (x1, max(26, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (74, 92, 230),
                1,
            )
        zone_text = self.status.current_zone or "STABILIZING"
        cv2.rectangle(canvas, (16, height - 64), (360, height - 16), (47, 41, 36), -1)
        cv2.putText(
            canvas,
            f"Current Zone: {zone_text}",
            (30, height - 33),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (255, 255, 255),
            2,
        )
        return canvas

    def _save_live_frame(self, frame: np.ndarray) -> None:
        encoded, buffer = cv2.imencode(".jpg", frame)
        if not encoded:
            logger.warning("Could not encode live monitor frame")
            return
        if self.frame_callback:
            self.frame_callback(buffer.tobytes())
            return
        path = settings.live_frame_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name("live.tmp.jpg")
        if cv2.imwrite(str(temp), frame):
            os.replace(temp, path)

    def _publish(self) -> None:
        self.status.updated_at = datetime.now(timezone.utc).isoformat()
        if self.status_callback:
            self.status_callback(self.status)
        else:
            persist_monitor_status(self.status)


def persist_monitor_status(status: MonitorStatus) -> None:
    """Atomically persist status for the web process or a standalone monitor."""
    if status.updated_at is None:
        status.updated_at = datetime.now(timezone.utc).isoformat()
    settings.state_path.parent.mkdir(parents=True, exist_ok=True)
    temp = settings.state_path.with_suffix(".tmp")
    temp.write_text(json.dumps(asdict(status), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, settings.state_path)


def build_detector(name: str) -> CatDetector:
    """Create the production YOLO detector or explicit deterministic demo detector."""
    if name == "demo-color":
        return DemoColorCatDetector()
    if name != "yolo":
        raise ValueError(f"Unknown detector: {name}")
    return YoloCatDetector(
        settings.yolo_model,
        settings.yolo_confidence,
        settings.yolo_image_size,
    )
